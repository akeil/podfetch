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


from collections import namedtuple

class DummyEntry(object):

    def __init__(self, **kwargs):
        self.guid = kwargs.get('guid')
        self.published_parsed = kwargs.get(
            'published_parsed', (2013,9,10,11,12,13,0))
        self.enclosures = kwargs.get('enclosures', [])
        self._data = kwargs

    def get(self, key, fallback=None):
        return self._data.get(key, fallback)

DummyEnclosure = namedtuple('DummyEnclosure', 'type href')

import logging
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def app(tmpdir):
    subsdir = str(tmpdir.join('subscriptions'))
    os.mkdir(subsdir)
    content_dir = str(tmpdir.join('content'))
    os.mkdir(content_dir)
    app = application.Podfetch(subsdir, content_dir)
    return app


def _write_subscription_config(path, url=None):
    url = url or 'http://example.com/feed'
    with open(path, 'w') as f:
        f.write('\n'.join([
            '[subscription]',
            'url = {}'.format(url),
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


def test_process_entry(tmpdir, monkeypatch, app):
    enclosures = [
        DummyEnclosure(type='audio/mpeg', href='does-not-matter'),
        DummyEnclosure(type='audio/mpeg', href='does-not-matter'),
    ]
    entry = DummyEntry(
        guid='guid',
        published_parsed=(2013,9,10,20,21,22,0),
        enclosures=enclosures
    )

    def mock_download(url, dst_path):
        with open(dst_path, 'w') as f:
            f.write('something')

    monkeypatch.setattr(application, 'download', mock_download)

    app._process_entry('feed_name', entry)

    feed_dir = os.path.join(app.content_dir, 'feed_name')
    assert len(os.listdir(feed_dir)) == 2


def test_unique_name(app):
    path = os.path.join(app.subscriptions_dir, 'existing')
    _write_subscription_config(path)
    unique_name = app.make_unique_name('existing')
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

if __name__ == '__main__':
    pytest.main(__file__)
