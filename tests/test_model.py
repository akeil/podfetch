#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
test_model
----------

Tests for `model` module.
'''
import os
import stat

import pytest
import mock
import feedparser

from podfetch import model
from podfetch.model import Subscription
from podfetch.exceptions import NoSubscriptionError
from podfetch.exceptions import FeedNotFoundError

from tests import common

@pytest.fixture
def sub(tmpdir):
    config_dir = tmpdir.mkdir('config')
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    sub = Subscription('name', 'http://example.com',
        str(config_dir), str(content_dir), str(cache_dir))
    return sub


def with_dummy_feed(monkeypatch, status=200, href=None,
    return_etag=None, return_modified=None, feed_data=None):

    if feed_data is None:
        feed_data = common.FEED_DATA

    def mock_fetch_feed(url, etag=None, modified=None):
        feed = feedparser.parse(feed_data)
        original_get = feed.get

        def override_get(what, fallback=None):
            if what == 'etag':
                return return_etag
            elif what == 'modified':
                return return_modified
            else:
                return original_get(what, fallback)

        feed.get = override_get

        feed.status = status
        feed.href = href
        feed.etag = return_etag
        feed.modified = return_modified
        return feed

    monkeypatch.setattr(model, '_fetch_feed', mock_fetch_feed)


def with_mock_download(monkeypatch):

    def create_file(url, dst):
        with open(dst, 'w') as f:
            f.write('something')

    monkeypatch.setattr(model, 'download',
        mock.MagicMock(side_effect=create_file))


class _Dummy(object):

    def __init__(self, **kwargs):
        self.data = kwargs
        self.data.update([
            (k,v) for k,v in self.__class__.defaults.items()
            if k not in self.data
        ])

    def __getattribute__(self, name):
        if name != 'data':
            try:
                return self.data[name]
            except KeyError:
                return object.__getattribute__(self, name)
        else:
            return object.__getattribute__(self, name)

    def get(self, name, fallback=None):
        return self.data.get(name, fallback)


class DummyFeed(_Dummy):

    defaults = {
        'title': None,
        'author': None,
        'entries': [],
    }

class DummyEntry(_Dummy):

    defaults = {
        'id': None,
        'enclosures': [],
        'published_parsed': (2013,9,10,11,12,13,0),
    }


class DummyEnclosure(_Dummy):

    defaults = {
        'href': 'http://example.com/download',
    }


def test_load_subscription_from_file(tmpdir):
    '''Load a subscription from its config file.'''
    load_from = tmpdir.join('the_name')
    load_from.write('\n'.join([
        '[subscription]',
        'url=http://example.com/feed',
        'max_episodes = 30',
        'filename_template = template',
    ]))

    sub = Subscription.from_file(str(load_from), 'content_dir', 'cache_dir')

    assert sub.name == 'the_name'
    assert sub.feed_url == 'http://example.com/feed'
    assert sub.max_episodes == 30
    assert sub.filename_template == 'template'


def test_load_nonexisting_raises_error():
    '''Trying to load a Subscription from a non-existing config file
    must raise a NoSubscriptionError.'''
    with pytest.raises(NoSubscriptionError):
        sub = Subscription.from_file(
            'does-not-exist', 'content_dir', 'cache_dir')


def test_save(tmpdir, sub):
    sub.max_episodes = 123
    sub.filename_template = 'template'
    sub.save()
    filename = os.path.join(sub.config_dir, 'name')
    with open(filename) as f:
        lines = f.readlines()

    assert 'http://example.com' in ''.join(lines)
    assert '123' in ''.join(lines)
    assert 'template' in ''.join(lines)


def test_save_and_load_index(sub):
    '''Save the index of downloaded enclosures to disk and load it.'''
    for index in range(5):
        id_ = 'id.{}'.format(index)
        entry = DummyEntry(id= id_)
        for enclosure_num in range(5):
            local_file = '/some/file/{}-{}'.format(index, enclosure_num)
            sub._add_to_index(entry, enclosure_num, local_file)
    sub._save_index()

    assert os.path.isfile(sub.index_file)

    reloaded_sub = Subscription('name', 'url',
        'config_dir', 'content_dir', sub.cache_dir)
    reloaded_sub._load_index()
    for index in range(5):
        id_ = 'id.{}'.format(index)
        entry = DummyEntry(id= id_)
        for enclosure_num in range(5):
            assert sub._in_index(entry, enclosure_num)

        assert not sub._in_index(entry, 99)

    assert not sub._in_index(DummyEntry(id='does not exist'), 0)


def test_load_index_ignore_empty_lines(sub):
    with open(sub.index_file, 'w') as f:
        for i in range(5):
            f.write('url{}\tlocal-file\n'.format(i))
            f.write('\n')  # empty line

    sub._load_index()
    assert 'url1' in sub.index
    assert len(sub.index) == 5


def test_write_read_cached_headers(sub):
    '''Write ``etag`` and ``modified`` headers to cache and retrieve them
    correctly.'''
    etag = 'etag'
    modified = 'modified'
    sub._store_cached_headers(etag, modified)
    read_etag, read_modified = sub._get_cached_headers()
    assert read_etag == etag
    assert read_modified == modified


def test_write_read_cached_headers_empty(sub):
    '''Make sure that if no ``etag`` or ``modified`` header is received,
    any existing cached haeder is cleared.
    '''
    etag = None
    modified = None
    sub._store_cached_headers(etag, modified)
    read_etag, read_modified = sub._get_cached_headers()
    assert read_etag is None
    assert read_modified is None


def test_accept_enclosure(sub):
    '''Test for the accept() function.
    We should reject anyenclosure that we have already downloaded
    and reject enclosures we don't understand.
    '''
    existing = DummyEntry(id='exists')
    sub._add_to_index(existing, 0, '/some/file')
    not_existing = DummyEntry(id='exists-not')

    enclosure = DummyEnclosure(type='audio/mpeg')
    video_enclosure = DummyEnclosure(type='video/mpeg')
    unknown_enclosure = DummyEnclosure()
    unsupported_enclosure = DummyEnclosure(type='image/jpeg')

    assert not sub._accept(existing, enclosure, 0)
    assert sub._accept(existing, enclosure, 1)
    assert sub._accept(not_existing, enclosure, 0)
    assert sub._accept(not_existing, video_enclosure, 0)
    assert not sub._accept(not_existing, unsupported_enclosure, 0)
    assert not sub._accept(not_existing, unknown_enclosure, 0)


def test_process_feed_entry(monkeypatch, sub):
    '''Test that feed entries are handled correctly.
    Download enclosures and add to index.
    '''
    href1 = 'href1'
    href2 = 'href2'
    href3 = 'href3'
    enclosures = [
        DummyEnclosure(type='audio/mpeg', href=href1),
        DummyEnclosure(type='audio/mpeg', href=href2),
        DummyEnclosure(type='text/plain', href=href3),  # will not be accepted
    ]
    entry = DummyEntry(id='test-id', enclosures=enclosures)
    feed = DummyFeed(title='feed-title', entries=[entry,])
    requested_urls = []

    def mock_download(url, dst):
        requested_urls.append(url)
        with open(dst, 'w') as f:
            f.write('something')
    monkeypatch.setattr(model, 'download', mock_download)

    sub._process_feed_entry(feed, entry)

    assert sub._in_index(entry, 0)
    assert sub._in_index(entry, 1)
    assert os.path.isfile(sub._local_file(entry, 0))
    assert os.path.isfile(sub._local_file(entry, 1))
    assert sub._local_file(entry, 0) != sub._local_file(entry, 1)
    assert href1 in requested_urls
    assert href2 in requested_urls
    assert not sub._in_index(entry, 3)
    assert href3 not in requested_urls


def test_apply_updates_max_episodes(sub, monkeypatch):
    '''in apply updates, max entries to be processed
    is max_episodes for this subscription.
    '''
    with_dummy_feed(monkeypatch)
    sub.max_episodes = 1
    sub._process_feed_entry = mock.MagicMock()
    sub.update()
    sub._process_feed_entry.assert_called_once()


def test_apply_updates_error_handling(sub, monkeypatch):
    '''Error for one feed entry should not stop us.'''
    # we rely on the dummy feed having more than one item
    with_dummy_feed(monkeypatch)
    sub._process_feed_entry = mock.MagicMock(side_effect=ValueError)
    sub.update()
    assert sub._process_feed_entry.call_count > 1


def test_update_feed_unchanged(sub, monkeypatch):
    with_dummy_feed(monkeypatch, status=304)
    sub._store_cached_headers('etag-value', 'modified-value')
    sub._apply_updates = mock.MagicMock()

    sub.update()

    assert not sub._apply_updates.called
    etag, modified = sub._get_cached_headers()
    assert etag == 'etag-value'
    assert modified == 'modified-value'


def test_update_store_feed_headers(sub, monkeypatch):
    '''After a successful update, we must remember
    the ``etag`` and ``modified`` header.
    '''
    with_dummy_feed(monkeypatch, return_etag='new-etag',
        return_modified='new-modified')
    sub._store_cached_headers('initial-etag', 'intial-modified')
    sub._apply_updates = mock.MagicMock()

    sub.update()

    assert sub._apply_updates.called
    etag, modified = sub._get_cached_headers()
    assert etag == 'new-etag'
    assert modified == 'new-modified'


def test_failed_update_no_store_feed_headers(sub, monkeypatch):
    '''After an error in feed-processing update, we must NOT remember
    the ``etag`` and ``modified`` header.
    '''
    with_dummy_feed(monkeypatch, return_etag='new-etag',
        return_modified='new-modified')
    sub._store_cached_headers('initial-etag', 'initial-modified')
    sub._apply_updates = mock.MagicMock(side_effect=ValueError)

    with pytest.raises(ValueError):
        sub.update()

    etag, modified = sub._get_cached_headers()
    assert etag == 'initial-etag'
    assert modified == 'initial-modified'


def test_update_feed_moved_permanently(sub, monkeypatch):
    new_url='http://example.com/new'
    with_dummy_feed(monkeypatch, status=301, href=new_url)
    sub._apply_updates = mock.MagicMock()

    sub.update()

    assert sub._apply_updates.called
    assert sub.feed_url == new_url


def test_update_error_fetching_feed(sub, monkeypatch):
    sub._store_cached_headers('initial-etag', 'initial-modified')

    def mock_fetch_feed(url, etag=None, modified=None):
        raise FeedNotFoundError

    monkeypatch.setattr(model, '_fetch_feed', mock_fetch_feed)

    with pytest.raises(FeedNotFoundError):
        sub.update()

    etag, modified = sub._get_cached_headers()
    assert etag == 'initial-etag'
    assert modified == 'initial-modified'


def test_downloaded_file_perms(tmpdir, monkeypatch):
    '''Assert that a downloaded file has the correct permissions.'''
    def mock_urlretrieve(url, dst):
        with open(dst, 'w') as f:
            f.write('something')

    monkeypatch.setattr(model, 'urlretrieve', mock_urlretrieve)

    dst = str(tmpdir.join('dst'))
    model.download('some-url', dst)
    mode = os.stat(dst).st_mode

    # minimum permissions we want: -rw-r--r--
    assert mode & stat.S_IRUSR  # owner read
    assert mode & stat.S_IWUSR  # owner write
    assert mode & stat.S_IRGRP  # group read
    assert mode & stat.S_IROTH  # other read


def test_download_error(sub, monkeypatch):
    with_dummy_feed(monkeypatch)

    def failing_download(url, dst):
        raise ValueError

    monkeypatch.setattr(model, 'download', failing_download)
    rv = sub.update()

    assert rv == model.ALL_EPISODES_FAILED


def test_generate_enclosure_filename_template(sub):
    enclosure = DummyEnclosure(type='audio/mpeg', href='does-not-matter')
    entry = DummyEntry(title='entry/title', enclosures=[enclosure],
        published_parsed=(2001,2,3,4,5,6,0)
    )
    feed = DummyFeed(title='feed-title', entries=[entry,])

    gen = lambda x: sub._generate_enclosure_filename(
        feed, entry, enclosure, index=x)

    sub.filename_template = 'constant'
    assert gen(None) == 'constant.mp3'

    # ext in template
    sub.filename_template = 'something.{ext}'
    assert gen(1).endswith('01.mp3')

    # timestamp
    sub.filename_template = '{year}-{month}-{day} {hour}-{minute}-{second}'
    expected = '2001-02-03 04-05-06.mp3'
    assert gen(None) == expected

    # title and replace forbidden chars
    sub.filename_template = '{title}'
    assert '/' not in gen(None)
    assert gen(None).startswith('entry')


def test_filename_template_from_app_config(sub):
    '''If no template is set for the subscription,
    use template from app-config'''
    sub.filename_template = ''
    sub.app_filename_template = 'app-template'
    feed = DummyFeed()
    entry = DummyEntry()
    enclosure = DummyEnclosure(type='audio/mpeg')
    gen = lambda: sub._generate_enclosure_filename(feed, entry, enclosure)

    assert gen() == 'app-template.mp3'
    sub.filename_template = 'specific'
    assert gen() == 'specific.mp3'


def test_safe_filename():
    cases = [
        ('already-safe', 'already-safe'),
        ('with witespace', 'with witespace'),
        ('path/separator', 'path_separator'),
        ('a\\b', 'a_b'),
        ('a:b', 'a_b'),
    ]
    for unsafe, expected in cases:
        assert model.safe_filename(unsafe) == expected


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
        assert model.file_extension_for_mime(mime) == expected

    unsupported = [
        'image/jpeg',
        'bogus',
        1,
        None,
    ]
    for mime in unsupported:
        with pytest.raises(ValueError):
            model.file_extension_for_mime(mime)


def test_feeditem_no_ids(sub, monkeypatch):
    '''Handling a RSS-feed where the //item/guid is missing.
    Nornally, entry.id is used to generate the filename and
    as the key to identify an entry in the local index.

    Test that we download the items ok - any only once'''
    with_dummy_feed(monkeypatch, feed_data=common.FEED_NO_IDS)
    with_mock_download(monkeypatch)

    assert len(sub.index) == 0
    sub.update()
    new_items = len(sub.index)
    assert new_items > 0

    model.download.reset_mock()
    sub.update()
    assert not model.download.called
    assert len(sub.index) == new_items


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
