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
from podfetch.application import WildcardFilter
from podfetch.exceptions import NoSubscriptionError


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
    config_dir = tmpdir.mkdir('config')
    index_dir = tmpdir.mkdir('index')
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    app = application.Podfetch(
        str(config_dir), str(index_dir), str(content_dir), str(cache_dir)
    )
    os.mkdir(app.subscriptions_dir)
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
    num_subscriptions = 3
    for index in range(num_subscriptions):
        filename = os.path.join(app.subscriptions_dir, 'feed-{}'.format(index))
        _write_subscription_config(filename)

    # filename starts with a "." ("hidden" file)
    hidden = os.path.join(app.subscriptions_dir, '.hidden')
    _write_subscription_config(hidden)

    bak = os.path.join(app.subscriptions_dir, 'something.bak')
    _write_subscription_config(bak)


    # default: list the hidden file
    names = [s.name for s in app.iter_subscriptions()]
    assert len(names) == num_subscriptions + 2
    assert 'feed-1' in names
    assert '.hidden' in names
    assert 'something.bak' in names

    # ignore option:
    app.ignore = ['.* *.bak']
    predicate = WildcardFilter('*-1')
    names = [s.name for s in app.iter_subscriptions(predicate=predicate)]
    assert '.hidden' not in names
    assert 'something.bak' not in names

    # wildcards
    names = [s.name for s in app.iter_subscriptions(predicate=predicate)]
    assert len(names) == 1
    assert names[0] == 'feed-1'


def test_unique_name(app):
    '''Make sure the application finds unique names for new subscriptions.'''
    path = os.path.join(app.subscriptions_dir, 'existing')
    _write_subscription_config(path)
    unique_name = app._make_unique_name('existing')
    assert unique_name != 'existing'


def test_subscription_for_name(app):
    # error case
    with pytest.raises(NoSubscriptionError):
        app.subscription_for_name('does-not-exist')

    # success case
    name='somename'
    app.add_subscription('http://www.example.com/feed', name=name)
    assert app.subscription_for_name(name).name == name


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


def test_keep_subscription_content(app):
    sub = app.add_subscription('some-url', 'the-name')
    content_dir = sub.content_dir
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


if __name__ == '__main__':
    pytest.main(__file__)
