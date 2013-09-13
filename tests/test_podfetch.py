#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_podfetch
----------------------------------

Tests for `podfetch` module.
"""
import pytest
import os

from podfetch import application


class DummyEntry(object):

    def __init__(self, **kwargs):
        self.guid = kwargs.get('guid')
        self.published_parsed = kwargs.get(
            'published_parsed', (2013,9,10,11,12,13,0))
        self.enclosures = kwargs.get('enclosures', [])
        self._data = kwargs

    def get(self, key, fallback=None):
        return self._data.get(key, fallback)

from collections import namedtuple
DummyEnclosure = namedtuple('DummyEnclosure', 'type href')


@pytest.fixture
def app(tmpdir):
    subsdir = tmpdir.mkdir('subscriptions')
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    app = application.Podfetch(str(subsdir), str(content_dir), str(cache_dir))
    return app


def _write_subscription_config(path, url=None, max_episodes=-1):
    url = url or 'http://example.com/feed'
    with open(path, 'w') as f:
        f.write('\n'.join([
            '[subscription]',
            'url = {}'.format(url),
            'max_episodes = {}'.format(max_episodes),
        ]))


def test_iter_subscriptions(app):
    for index in range(3):
        filename = os.path.join(app.subscriptions_dir, 'feed-{}'.format(index))
        _write_subscription_config(filename)

    subs = [x for x in app.iter_subscriptions()]
    assert len(subs) == 3
    assert 'feed-1' in [s.name for s in subs]


def test_generate_enclosure_filename():
    enclosure = DummyEnclosure(type='audio/mpeg', href='does-not-matter')
    entry = DummyEntry(
        guid='guid',
        published_parsed=(2013,9,10,11,12,13,0),
        enclosures=[enclosure,],
    )

    filename = application.generate_filename_for_enclosure(entry, 0, enclosure)
    assert filename == '2013-09-10_11-12-13_guid_0.mp3'


def test_safe_filename():
    cases = [
        ('already-safe', 'already-safe'),
        ('with witespace', 'with witespace'),
        ('path/separator', 'path_separator'),
        ('a\\b', 'a_b'),
        ('a:b', 'a_b'),
    ]
    for unsafe, expected in cases:
        assert application.safe_filename(unsafe) == expected


def test_file_extension_for_mime():
    supported_cases = [
        ('audio/mpeg', 'mp3'),
        ('audio/ogg', 'ogg'),
        ('audio/flac', 'flac'),
        ('audio/MPEG', 'mp3'),
        ('AUDIO/ogg', 'ogg'),
        ('AUDIO/FLAC', 'flac'),
    ]
    for mime, expected in supported_cases:
        assert application.file_extension_for_mime(mime) == expected

    unsupported = [
        'image/jpeg',
        'bogus',
        1,
        None,
    ]
    for mime in unsupported:
        with pytest.raises(ValueError):
            application.file_extension_for_mime(mime)


def test_unique_name(app):
    '''Make sure the application finds unique names for new subscriptions.'''
    path = os.path.join(app.subscriptions_dir, 'existing')
    _write_subscription_config(path)
    unique_name = app._make_unique_name('existing')
    assert unique_name != 'existing'


def test_add_subscription(app):
    first = app.add_subscription('http://example.com/feed', name='the-name')
    second = app.add_subscription('http://example.com/feed', name='the-name')
    assert 'the-name' in [s.name for s in app.iter_subscriptions()]
    assert second.name != first.name
    assert len([s for s in app.iter_subscriptions()]) == 2


def test_remove_subscription(app):
    sub = app.add_subscription('some-url', 'the-name')
    assert sub.name in [s.name for s in app.iter_subscriptions()]
    app.remove_subscription('the-name')
    assert sub.name not in [s.name for s in app.iter_subscriptions()]


def test_remove_subscription_content(app):
    sub = app.add_subscription('some-url', 'the-name')
    content_dir = os.path.join(app.content_dir, 'the-name')
    os.mkdir(content_dir)
    content_file = os.path.join(content_dir, 'somefile')
    with open(content_file, 'w') as f:
        f.write('some content')
    app.remove_subscription('the-name', delete_content=True)
    assert not os.path.exists(content_file)
    assert not os.path.exists(content_dir)


def test_keep_subscription_content(app):
    sub = app.add_subscription('some-url', 'the-name')
    content_dir = os.path.join(app.content_dir, 'the-name')
    os.mkdir(content_dir)
    content_file = os.path.join(content_dir, 'somefile')
    with open(content_file, 'w') as f:
        f.write('some content')
    app.remove_subscription('the-name', delete_content=False)
    # subscription is gone
    assert sub.name not in [s.name for s in app.iter_subscriptions()]
    # content is left
    assert os.path.exists(content_file)


def test_name_from_url():
    cases = [
        ('http://example.com','example.com'),
        ('http://example.com/something','example.com'),
        ('http://example.com?query','example.com'),
#        ('example.com','example.com'),
        ('http://www.example.com','example.com'),
        ('http://sub.example.com','sub.example.com'),
    ]
    for url, expected in cases:
        assert application.name_from_url(url) == expected


def _create_subscription(app, name,
    url=None, max_episodes=-1, create_episodes=0):
    _write_subscription_config(
        os.path.join(app.subscriptions_dir, name),
        url=url,
        max_episodes=max_episodes,
    )

    content_dir = os.path.join(app.content_dir, name)
    os.mkdir(content_dir)
    for index in range(create_episodes):
        filename = 'episode-{}'.format(index)
        path = os.path.join(content_dir, filename)
        with open(path, 'w') as f:
            f.write('some content')


def test_purge(app):
    name = 'my-subscription'
    num_episodes = 10
    max_episodes = 5
    _create_subscription(
        app, name, max_episodes=max_episodes, create_episodes=num_episodes
    )
    content_dir = os.path.join(app.content_dir, name)
    assert len(os.listdir(content_dir)) == num_episodes

    app.purge_one(name)
    remaining = os.listdir(content_dir)
    assert len(remaining) == max_episodes
    assert 'episode-9' in remaining
    assert 'episode-5' in remaining
    assert 'episode-0' not in remaining
    assert 'episode-4' not in remaining


def test_purge_keep_all(app):
    name = 'my-subscription'
    num_episodes = 10
    max_episodes = -1
    _create_subscription(
        app, name, max_episodes=max_episodes, create_episodes=num_episodes
    )
    content_dir = os.path.join(app.content_dir, name)
    assert len(os.listdir(content_dir)) == num_episodes

    app.purge_one(name)
    remaining = os.listdir(content_dir)
    assert len(remaining) == num_episodes


if __name__ == '__main__':
    pytest.main(__file__)
