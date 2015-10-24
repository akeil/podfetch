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
from podfetch.model import Episode, require_directory


SUPPORTED_CONTENT = {
    'audio/mpeg': 'mp3',
    'audio/x-mpeg': 'mp3',
    'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/ogg': 'ogg',
    'audio/flac': 'flac',
    'video/mpeg': 'mp4',
}


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
        str(config_dir), str(index_dir), str(content_dir), str(cache_dir),
        supported_content=SUPPORTED_CONTENT
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


def test_edit_simple(app):
    '''Assert that editing of simple subscription properties works.'''
    name = 'the-name'
    sub = app.add_subscription('some-url', name)

    app.edit(name,
        url='new-url',
        title='New Title',
        enabled=False,
        filename_template='newtemplate',
        max_episodes=10
    )

    reloaded = app.subscription_for_name(name)
    assert reloaded.feed_url == 'new-url'
    assert reloaded.title == 'New Title'
    assert reloaded.enabled == False
    assert reloaded.filename_template == 'newtemplate'
    assert reloaded.max_episodes == 10


def test_edit_rename_files(app):
    sub = app.add_subscription('some-url', 'name',
        filename_template='{}.{ext}')
    content_dir = sub.content_dir
    episodefile = os.path.join(content_dir, 'file.mp3')
    require_directory(content_dir)
    with open(episodefile, 'w') as f:
        f.write('content')

    sub.episodes.append(Episode(sub, 'id', SUPPORTED_CONTENT, files=[(
        'url',
        'audio/mpeg',
        episodefile
    )]))
    sub.save()
    sub._save_index()

    app.edit('name',
        filename_template='{subscription_name}-{id}',
        move_files=True
    )
    reloaded = app.subscription_for_name('name')
    newpath = reloaded.episodes[0].files[0][2]
    assert newpath != episodefile
    assert os.path.isfile(newpath)


def test_rename(app):
    oldname = 'oldname'
    newname = 'newname'
    sub = app.add_subscription('some-url', oldname)

    content_dir = sub.content_dir
    cachefile = sub._cache_path('etag')
    indexfile = sub.index_file
    episodefile = os.path.join(content_dir, 'file.mp3')

    require_directory(content_dir)
    with open(episodefile, 'w') as f:
        f.write('content')

    sub._cache_put('etag', 'somevalue')
    sub.episodes.append(Episode(sub, 'id', SUPPORTED_CONTENT, files=[(
        'url',
        'audio/mpeg',
        episodefile
    )]))
    sub._save_index()

    # preconditions
    assert os.path.isfile(cachefile)
    assert os.path.isfile(indexfile)
    assert os.path.isdir(content_dir)
    assert os.path.isfile(episodefile)

    app.edit(oldname, name=newname, move_files=True)

    with pytest.raises(NoSubscriptionError):
        app.subscription_for_name(oldname)

    # old files must not exist any more
    assert not os.path.isfile(indexfile)
    assert not os.path.isfile(cachefile)
    assert not os.path.isfile(episodefile)
    assert not os.path.isdir(content_dir)

    # new files must exist
    reloaded = app.subscription_for_name(newname)
    assert reloaded is not None
    assert len(reloaded.episodes) == 1
    assert os.path.isfile(reloaded.episodes[0].files[0][2])


if __name__ == '__main__':
    pytest.main(__file__)
