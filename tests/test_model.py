#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
test_model
----------

Tests for `model` module.
'''
import os
import stat
from datetime import datetime
from datetime import timedelta

import pytest
import mock
import feedparser

from podfetch import model
from podfetch.model import Subscription
from podfetch.model import Episode
from podfetch.model import unique_filename
from podfetch.exceptions import NoSubscriptionError
from podfetch.exceptions import FeedNotFoundError

from tests import common


SUPPORTED_CONTENT = {
    'audio/mpeg': 'mp3',
    'audio/x-mpeg': 'mp3',
    'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/ogg': 'ogg',
    'audio/flac': 'flac',
    'video/mpeg': 'mp4',
}


@pytest.fixture
def sub(tmpdir):
    config_dir = tmpdir.mkdir('config')
    index_dir = tmpdir.mkdir('index')
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    sub = Subscription('name', 'http://example.com',
        str(config_dir), str(index_dir), str(content_dir), str(cache_dir),
        supported_content=SUPPORTED_CONTENT
    )
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

    mock_download = mock.MagicMock(side_effect=create_file)
    monkeypatch.setattr(model, 'download', mock_download)
    return mock_download


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
        'title': None,
        'description': None
    }


class DummyEnclosure(_Dummy):

    defaults = {
        'href': 'http://example.com/download',
    }


# Subscription Tests ----------------------------------------------------------


def test_load_subscription_from_file(tmpdir):
    '''Load a subscription from its config file.'''
    load_from = tmpdir.join('the_name')
    load_from.write('\n'.join([
        '[subscription]',
        'url=http://example.com/feed',
        'max_episodes = 30',
        'filename_template = template',
        'title = the_title',
        'content_dir = subscription_content_dir',
        'enabled = False',
    ]))

    sub = Subscription.from_file(
        str(load_from), 'index_dir', 'content_dir', 'cache_dir'
    )

    assert sub.name == 'the_name'
    assert sub.feed_url == 'http://example.com/feed'
    assert sub.title == 'the_title'
    assert sub.max_episodes == 30
    assert sub.filename_template == 'template'
    assert sub.content_dir == 'subscription_content_dir'
    assert sub.enabled == False


def test_load_nonexisting_raises_error():
    '''Trying to load a Subscription from a non-existing config file
    must raise a NoSubscriptionError.'''
    with pytest.raises(NoSubscriptionError):
        sub = Subscription.from_file(
            'does-not-exist',
            'index_dir', 'content_dir', 'cache_dir'
        )


def test_load_invalid_raises_error(tmpdir):
    '''Loading a subscription from a file that is not in ini-format.'''
    invalid_file = tmpdir.join('invalid_file')
    invalid_file.write('something')
    with pytest.raises(NoSubscriptionError):
        Subscription.from_file(
            str(invalid_file),
            'index_dir', 'content_dir', 'cache_dir'
        )


def test_load_empty_raises_error(tmpdir):
    '''Loading a subscription from an empty file.'''
    empty_file = tmpdir.join('invalid_file')
    empty_file.write('')
    with pytest.raises(NoSubscriptionError):
        Subscription.from_file(
            str(empty_file),
            'index_dir', 'content_dir', 'cache_dir'
        )


def test_load_missing_url(tmpdir):
    '''Loading a subscription from ini file with required fields missing.'''
    invalid_file = tmpdir.join('invalid_file')
    invalid_file.write('[subscription]\nfield = value')
    with pytest.raises(NoSubscriptionError):
        Subscription.from_file(
            str(invalid_file),
            'index_dir', 'content_dir', 'cache_dir'
        )


def test_save(tmpdir, sub):
    sub.max_episodes = 123
    sub.filename_template = 'template'
    sub.title = 'subscription-title'
    sub.content_dir = 'my-content-dir'
    sub.save()
    filename = os.path.join(sub.config_dir, 'name')
    with open(filename) as f:
        lines = f.readlines()

    text = ''.join(lines)
    assert 'http://example.com' in text
    assert '123' in text
    assert 'template' in text
    assert 'subscription-title' in text
    assert 'my-content-dir' in text
    assert 'yes' in text  # from enabled=True


def test_save_and_load_index(sub):
    '''Save the index of downloaded enclosures to disk and load it.'''
    for index in range(5):
        sub.episodes.append(
            Episode(sub, 'id.{}'.format(index), SUPPORTED_CONTENT)
        )

    sub._save_index()

    assert os.path.isfile(sub.index_file)

    reloaded_sub = Subscription('name', 'url',
        'index_dir', 'config_dir', 'content_dir', sub.cache_dir)
    reloaded_sub._load_index()
    for index in range(5):
        id_ = 'id.{}'.format(index)
        episode = sub._episode_for_id(id_)
        assert episode is not None

    assert sub._episode_for_id('bogus') is None


def test_save_index_create_directory(sub, tmpdir):
    '''Assert that the directory for the index file is created
    if it does not exist.'''
    sub.index_dir = str(tmpdir.join('does-not-exist'))
    sub.name = 'name'
    sub.episodes.append(Episode(sub, 'id', SUPPORTED_CONTENT))
    sub._save_index()
    assert os.path.isfile(os.path.join(sub.index_dir, 'name.json'))


def test_delete(sub, monkeypatch):
    '''Assert that after a subscription is deleted,
    content, index file and cached header files are deleted.'''
    with_dummy_feed(monkeypatch, return_etag='x', return_modified='x')
    with_mock_download(monkeypatch)

    sub.update()
    assert len(os.listdir(sub.content_dir)) > 0
    assert os.path.isfile(sub._cache_path('etag'))
    assert os.path.isfile(sub._cache_path('modified'))
    assert os.path.isfile(sub.index_file)

    sub.delete()
    assert not os.path.exists(sub.content_dir)
    assert not os.path.exists(sub._cache_path('etag'))
    assert not os.path.exists(sub._cache_path('modified'))
    assert not os.path.exists(sub.index_file)


def test_write_read_cache(sub):
    '''Write to cache and retrieve correctly.'''
    data = {
        'foo': 'xyz',
        'bar': 'abc',
        'None': None,
    }
    for k, v in data.items():
        sub._cache_put(k, v)

    for k in data.keys():
        assert sub._cache_get(k) == data[k]


def test_write_read_cache_empty(sub):
    '''Reading non-existent key from cache should be None.'''
    assert sub._cache_get('does-not-exist') is None


def test_apply_updates_max_episodes(sub, monkeypatch):
    '''in apply updates, max entries to be processed
    is max_episodes for this subscription.
    '''
    with_dummy_feed(monkeypatch)
    with_mock_download(monkeypatch)

    sub.max_episodes = 1
    sub._process_feed_entry = mock.MagicMock()
    sub.update()
    assert sub._process_feed_entry.call_count == 1


def test_apply_updates_error_handling(sub, monkeypatch):
    '''Error for one feed entry should not stop us.'''
    # we rely on the dummy feed having more than one item
    with_dummy_feed(monkeypatch)
    with_mock_download(monkeypatch)

    mock_download = mock.MagicMock(side_effect=ValueError)
    monkeypatch.setattr(Episode, 'download', mock_download)
    sub.update()
    assert Episode.download.call_count > 1


def test_update_feed_unchanged(sub, monkeypatch):
    '''When the feed is not modified, update() should return OK
    but ot update.'''
    with_dummy_feed(monkeypatch, status=304)
    with_mock_download(monkeypatch)

    sub._cache_put('etag', 'etag-value')
    sub._cache_put('modified', 'modified-value')
    sub._update_entries = mock.MagicMock()

    sub.update()

    assert not sub._update_entries.called
    assert sub._cache_get('etag') == 'etag-value'
    assert sub._cache_get('modified') == 'modified-value'


def test_forced_update_feed_unchanged(sub, monkeypatch):
    '''Ignore unchanged feed when using ``force``.'''
    with_dummy_feed(monkeypatch, status=304)
    with_mock_download(monkeypatch)

    sub._cache_put('etag', 'etag-value')
    sub._cache_put('modified', 'modified-value')

    sub.update(force=True)

    assert len(sub.episodes) > 0


def test_update_store_feed_headers(sub, monkeypatch):
    '''After a successful update, we must remember
    the ``etag`` and ``modified`` header.
    '''
    with_dummy_feed(monkeypatch, return_etag='new-etag',
        return_modified='new-modified')
    with_mock_download(monkeypatch)

    sub._cache_put('etag', 'initial-etag')
    sub._cache_put('modified', 'intial-modified')
    sub._update_entries = mock.MagicMock()

    sub.update()

    assert sub._update_entries.called
    assert sub._cache_get('etag') == 'new-etag'
    assert sub._cache_get('modified') == 'new-modified'


def test_failed_update_no_store_feed_headers(sub, monkeypatch):
    '''After an error in feed-processing update, we must NOT remember
    the ``etag`` and ``modified`` header.
    '''
    with_dummy_feed(monkeypatch, return_etag='new-etag',
        return_modified='new-modified')
    with_mock_download(monkeypatch)
    sub._cache_put('etag', 'initial-etag')
    sub._cache_put('modified', 'initial-modified')
    sub._update_entries = mock.MagicMock(side_effect=ValueError)

    with pytest.raises(ValueError):
        sub.update()

    assert sub._cache_get('etag') == 'initial-etag'
    assert sub._cache_get('modified') == 'initial-modified'


def test_update_feed_moved_permanently(sub, monkeypatch):
    new_url='http://example.com/new'
    with_dummy_feed(monkeypatch, status=301, href=new_url)
    with_mock_download(monkeypatch)

    sub._update_entries = mock.MagicMock()

    sub.update()

    assert sub._update_entries.called
    assert sub.feed_url == new_url


def test_update_error_fetching_feed(sub, monkeypatch):
    sub._cache_put('etag', 'initial-etag')
    sub._cache_put('modified', 'initial-modified')

    def mock_fetch_feed(url, etag=None, modified=None):
        raise FeedNotFoundError

    monkeypatch.setattr(model, '_fetch_feed', mock_fetch_feed)

    with pytest.raises(FeedNotFoundError):
        sub.update()

    etag = sub._cache_get('etag')
    modified = sub._cache_get('modified')
    assert etag == 'initial-etag'
    assert modified == 'initial-modified'


def test_downloaded_file_perms(tmpdir, monkeypatch):
    '''Assert that a downloaded file has the correct permissions.'''
    def mock_urlretrieve(url):
        dst = str(tmpdir.join('somefile'))
        with open(dst, 'w') as f:
            f.write('something')
        return dst, None

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
    '''if download failed, episode should be present but w/o local file'''
    with_dummy_feed(monkeypatch)

    def failing_download(url, dst):
        raise ValueError

    # precondition
    assert len(sub.episodes) == 0

    monkeypatch.setattr(model, 'download', failing_download)
    sub.update()

    assert len(sub.episodes) > 1
    assert not sub.episodes[0].files[0][2]  # no local file


def outdated_test_generate_enclosure_filename_template(sub):
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
    sub.filename_template = '{year}-{month}-{day}T{hour}-{minute}-{second}'
    expected = '2001-02-03T04-05-06.mp3'
    assert gen(None) == expected

    # title and replace forbidden chars
    sub.filename_template = '{title}'
    assert '/' not in gen(None)
    assert gen(None).startswith('entry')


def test_purge(sub, monkeypatch):
    '''Assert that the right episodes are deleted with purge'''
    with_dummy_feed(monkeypatch)
    with_mock_download(monkeypatch)
    sub.update()
    sub.max_episodes = 1

    # relies on common.FEED_DATA having exactly two items
    assert len(sub.episodes) == 2
    assert len(os.listdir(sub.content_dir)) == 2

    deleted = sub.purge()
    assert len(deleted) == 1
    assert len(sub.episodes) == 1
    assert len(os.listdir(sub.content_dir)) == 1


def test_purge_simulate(sub, monkeypatch):
    '''Assert that no episodes are deleted with purge
    in simulation mode'''
    with_dummy_feed(monkeypatch)
    with_mock_download(monkeypatch)
    sub.update()
    sub.max_episodes = 1

    # relies on common.FEED_DATA having exactly two items
    assert len(sub.episodes) == 2
    assert len(os.listdir(sub.content_dir)) == 2

    deleted = sub.purge(simulate=True)
    assert len(deleted) == 1
    assert len(sub.episodes) == 2
    assert len(os.listdir(sub.content_dir)) == 2


def test_purge_keepall(sub, monkeypatch):
    '''Assert that no episodes are deleted with purge
    if max_episodes < 1'''
    with_dummy_feed(monkeypatch)
    with_mock_download(monkeypatch)
    sub.update()
    sub.max_episodes = -1

    # relies on common.FEED_DATA having exactly two items
    assert len(sub.episodes) == 2
    assert len(os.listdir(sub.content_dir)) == 2

    deleted = sub.purge(simulate=True)
    assert len(deleted) == 0
    assert len(sub.episodes) == 2
    assert len(os.listdir(sub.content_dir)) == 2


# Tests Episode ---------------------------------------------------------------


def test_episode_download(monkeypatch, tmpdir, sub):
    '''Test for `Episode.download()`
      - should download all urls from self.files
        - which are not downloaded already
        - which haven an acceptable content type
    '''
    mock_download = with_mock_download(monkeypatch)

    local_path = str(tmpdir.join('file'))
    with open(local_path, 'w') as f:
        f.write('I exist.')
    files = [
        ('http://example.com/1', 'audio/mpeg', local_path),  # already there
        ('http://example.com/2', 'audio/mpeg', None),        # should download
        ('http://example.com/3', 'audio/mpeg', None),        # should download
        ('http://example.com/4', 'text/html', None),         # reject
        ('http://example.com/5', None, None),         # reject
    ]
    episode = Episode(sub, 'id', SUPPORTED_CONTENT, files=files)

    episode.download()
    assert mock_download.call_count == 2  # 2x previously not downloaded
    assert mock_download.called_with('http://example.com/2')
    assert mock_download.called_with('http://example.com/3')
    old_len = len(files)
    assert old_len == len(episode.files)


def test_episode_force_download(monkeypatch, tmpdir, sub):
    mock_download = with_mock_download(monkeypatch)

    local_path = str(tmpdir.join('file'))
    existing_content = 'I exist'
    with open(local_path, 'w') as f:
        f.write(existing_content)

    files = [
        ('http://example.com/1', 'audio/mpeg', local_path),  # already there
        ('http://example.com/2', 'audio/mpeg', None),        # should download
        ('http://example.com/4', 'text/html', None),         # reject
    ]
    episode = Episode(sub, 'id', SUPPORTED_CONTENT, files=files)

    episode.download(force=True)

    assert mock_download.call_count == 2  # one new, one forced, one rejected
    assert mock_download.called_with('http://example.com/1')
    assert mock_download.called_with('http://example.com/2')
    old_len = len(files)
    assert old_len == len(episode.files)
    # check that the forced file was actually overwritten
    with open(local_path) as f:
        assert f.read() != existing_content


def test_content_dir_from_subscription_config(monkeypatch, sub, tmpdir):
    '''Assert that if subscription defines a different `content_dir`,
    new episodes are downloaded to that directory.'''
    mock_download = with_mock_download(monkeypatch)
    #with_dummy_feed(monkeypatch)

    content_dir = tmpdir.mkdir('episodes')
    sub.content_dir = str(content_dir)

    files = [
        ('http://example.com/1', 'audio/mpeg', None)
    ]
    episode = Episode(sub, 'id', SUPPORTED_CONTENT, files=files)
    episode.download()
    assert len(episode.files) > 0
    for unused, unused_also, path in episode.files:
        assert os.path.dirname(path) == str(content_dir)


def test_generate_filename_episode(sub):
    episode = Episode(sub, 'the-id', SUPPORTED_CONTENT,
        title='the-title',
        pubdate=(2001,2,3,4,5,6,0),
    )

    gen = lambda x: episode._generate_filename('audio/mpeg', x)

    sub.filename_template = 'constant'
    assert gen(None) == 'constant.mp3'

    # ext in template
    sub.filename_template = 'something.{ext}'
    assert gen(1).endswith('01.mp3')

    # timestamp
    sub.filename_template = '{year}-{month}-{day}T{hour}-{minute}-{second}'
    expected = '2001-02-03T04-05-06.mp3'
    assert gen(None) == expected

    # title and replace forbidden chars
    sub.filename_template = '{title}'
    assert '/' not in gen(None)
    assert gen(None).startswith('the-title')

    # index
    sub.filename_template = 'constant'
    many = set([gen(i) for i in range(10)])
    assert len(many) == 10

def test_generate_filename_pathsep(sub):
    '''Allow path separator in template, but not in template args.'''
    sub.filename_template = '{year}/{month}/{title}'
    episode = Episode(sub, 'the-id', SUPPORTED_CONTENT,
        title='the/title',
        pubdate=(2001,2,3,4,5,6,0),
    )

    generated = episode._generate_filename('audio/mpeg', 0)
    assert generated == '2001/02/the_title.mp3'


def test_filename_template_from_app_config(sub):
    '''If no template is set for the subscription,
    use template from app-config'''
    sub.filename_template = ''
    sub.app_filename_template = 'app-template'
    episode = Episode(sub, 'id', SUPPORTED_CONTENT)
    feed = DummyFeed()
    entry = DummyEntry()
    enclosure = DummyEnclosure(type='audio/mpeg')
    gen = lambda x: episode._generate_filename('audio/mpeg', x)

    assert gen(None) == 'app-template.mp3'
    sub.filename_template = 'specific'
    assert gen(None) == 'specific.mp3'


def test_episode_from_dict(sub):
    '''Test creating an Episode from a data-dict.
    The dict is normally loaded from a JSON file.
    '''
    file1 = ('http://example.com/1', 'audio/mpeg', '/local/path/1')
    file2 = ('http://example.com/2', 'audio/mpeg', None)
    data = {
        'id': 'the-id',
        'title': 'the-title',
        'description': 'the-description',
        'files': [
            file1,
            file2,
        ]
    }
    episode = Episode.from_dict(sub, SUPPORTED_CONTENT, data)
    assert episode.id == 'the-id'
    assert episode.title == 'the-title'
    assert episode.description == 'the-description'
    assert file1 in episode.files
    assert file2 in episode.files
    assert len(episode.files) == 2


def test_episode_from_dict_minimal_data(sub):
    '''Test creating an Episode from a data-dict.
    Omitting all optional fields.
    The dict is normally loaded from a JSON file.
    '''
    data = {'id': 'the-id'}
    episode = Episode.from_dict(sub, SUPPORTED_CONTENT, data)
    assert episode.id == 'the-id'
    assert episode.title is None
    assert episode.description is None
    assert type(episode.files) == list
    assert len(episode.files) == 0


def test_episode_from_dict_no_id_raises(sub):
    data = {'id': None}
    with pytest.raises(ValueError):
        Episode.from_dict(sub, SUPPORTED_CONTENT, data)


def test_episode_from_entry(sub):
    pubdate = (2001,2,3,13,13,15,0)
    entry = DummyEntry(
        id='the-id',
        title='the-title',
        description='the-description',
        enclosures=[
            DummyEnclosure(href='http://example.com/1', type='audio/mpeg'),
            DummyEnclosure(href='http://example.com/2', type='audio/mpeg'),
        ],
        published_parsed=pubdate,
    )

    episode = Episode.from_entry(sub, SUPPORTED_CONTENT, entry)
    assert episode.id == 'the-id'
    assert episode.title == 'the-title'
    assert episode.description == 'the-description'
    assert episode.pubdate == pubdate
    assert ('http://example.com/1', 'audio/mpeg', None) in episode.files
    assert ('http://example.com/2', 'audio/mpeg', None) in episode.files
    assert len(episode.files) == 2


def test_episode_from_entry_pubdate(sub):
    '''Assert that the pubdate is floored to "now"'''
    future = datetime.utcnow() + timedelta(days=2)
    pubdate = future.timetuple()
    entry = DummyEntry(
        id='the-id',
        published_parsed=pubdate
    )

    episode = Episode.from_entry(sub, SUPPORTED_CONTENT, entry)
    assert episode.pubdate[2] != pubdate[2]

def test_episode_as_dict(sub):
    pubdate = (2001,2,3,13,13,15,0)
    file1 = ('http://example.com/1', 'audio/mpeg', 'abc')
    file2 = ('http://example.com/2', 'audio/mpeg', '123')
    episode = Episode(
        sub, 'the-id', SUPPORTED_CONTENT,
        title='the-title',
        description='the-description',
        files=[
            file1,
            file2
        ],
        pubdate=pubdate,
    )

    data = episode.as_dict()
    assert data['id'] == 'the-id'
    assert data['title'] == 'the-title'
    assert data['description'] == 'the-description'
    assert data['pubdate'] == pubdate
    assert len(data['files']) == 2
    assert file1 in data['files']
    assert file2 in data['files']


def test_safe_filename():
    cases = [
        ('already-safe', 'already-safe'),
        ('with witespace', 'with witespace'),
        ('a\\b', 'a_b'),
        ('a:b', 'a_b'),
    ]
    for unsafe, expected in cases:
        assert model.safe_filename(unsafe) == expected


def test_pretty_filename():
    cases = [
        ('', ''),
        (None, None),
        ('pretty', 'pretty'),
        ('replace whitespace', 'replace_whitespace'),
        ('abcäöüßabc', 'abcaeoeuessabc'),
        ('multi _ separator', 'multi_separator'),
        ('a---b', 'a-b'),
        ('abcÄÜÖabc', 'abcAeUeOeabc'),
        ('what?', 'what'),
        ('***', ''),
        ('This{and}That', 'This_and_That'),
        ('abc/def', 'abc_def'),
        ('a&b', 'a+b'),
        ('something, something', 'something_something'),
        # non-ascii characters are deleted
        ('A³', 'A'),
        ('a€c', 'ac'),
    ]
    for unpretty, expected in cases:
        assert model.pretty(unpretty) == expected


def test_file_extension_for_mime(sub):
    episode = Episode(sub, 'id', SUPPORTED_CONTENT)
    supported_cases = [
        ('audio/mpeg', 'mp3'),
        ('audio/ogg', 'ogg'),
        ('audio/flac', 'flac'),
        ('audio/MPEG', 'mp3'),
        ('AUDIO/ogg', 'ogg'),
        ('AUDIO/FLAC', 'flac'),
    ]
    for mime, expected in supported_cases:
        assert episode._file_extension_for_content_type(mime) == expected

    unsupported = [
        'image/jpeg',
        'bogus',
        1,
        None,
    ]
    for mime in unsupported:
        with pytest.raises(ValueError):
            episode._file_extension_for_content_type(mime)


def test_unique_filename(tmpdir):
    f = tmpdir.join('file.ext')
    f.write('content')
    filename = str(f)

    unique0 = unique_filename(filename)
    assert unique0 != filename
    assert unique0.endswith('.ext')
    assert os.path.dirname(unique0) == os.path.dirname(filename)

    with open(unique0, 'w') as u0:
        u0.write('conent')

    unique1 = unique_filename(filename)
    assert unique1 != filename
    assert unique1 != unique0
    assert unique1.endswith('.ext')


def test_feeditem_no_ids(sub, monkeypatch):
    '''Handling a RSS-feed where the //item/guid is missing.
    Nornally, entry.id is used to generate the filename and
    as the key to identify an episode.

    Test that we download the items ok - and only once
    '''
    with_dummy_feed(monkeypatch, feed_data=common.FEED_NO_IDS)
    with_mock_download(monkeypatch)

    assert len(sub.episodes) == 0
    sub.update()
    new_items = len(sub.episodes)
    assert new_items > 0

    model.download.reset_mock()
    sub.update()
    assert not model.download.called
    assert len(sub.episodes) == new_items


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
