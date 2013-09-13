#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
test_podfetch
----------------------------------

Tests for `podfetch` module.
'''
import os

import pytest
import mock
import feedparser

from podfetch import model
from podfetch.model import Subscription
from podfetch.exceptions import NoSubscriptionError
from podfetch.exceptions import FeedNotFoundError


@pytest.fixture
def sub(tmpdir):
    config_dir = tmpdir.mkdir('config')
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    sub = Subscription('name', 'http://example.com',
        str(config_dir), str(content_dir), str(cache_dir))
    return sub


FEED_DATA = '''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
>
<channel>
  <title>1LIVE Plan B Reportage</title>
  <link>http://www.einslive.de/sendungen/plan_b/reportage/index.jsp</link>
  <description>Im Dunkeln hört man besser! Atmosphärisches: Eingefangen, aufgenommen, mitgenommen. Von draußen ins Studio. Aus Thailand, Remscheid oder London. Beim Heilfasten, den &quot;Jesus Freaks&quot; oder in &quot;Members Only&quot;-Clubs. Stimmungen statt Statements. Im Jugendknast, Drogenentzug oder Flüchtlingslager. Was der Reporter sieht, erzählt er. Was der Reporter hört, lässt er hören. Miterleben, das geschieht immer montags in der 1LIVE Plan B Reportage.</description>
  <language>de</language>
  <generator>wdr-podcast</generator>
  <copyright>Copyright 2013, WDR</copyright>
  <image>
    <url>http://www.wdr.de/radio/podcast/img/2012/1LIVE/1live_planb600x600.jpg</url>
    <title>1LIVE Plan B Reportage</title>
    <link>http://www.einslive.de/sendungen/plan_b/reportage/index.jsp</link>
  </image>
  <ttl>360</ttl>
  <category>Society &amp; Culture</category>
  <lastBuildDate>Thu, 05 Sep 2013 00:00:16 +0200</lastBuildDate>
  <pubDate>Thu, 05 Sep 2013 00:00:16 +0200</pubDate>
  <managingEditor>radio@wdr.de</managingEditor>
  <webMaster>radio@wdr.de</webMaster>

<item>
  <title>1LIVE - Plan B Reportage: &quot;1 Beeck, 10 Festivals, 100 Aufgaben&quot;:Festivalsommer m. Simon Beeck (02.09.2013)</title>
  <pubDate>Wed, 04 Sep 2013 00:00:00 +0200</pubDate>
  <description> © WDR 2013</description>
  <guid isPermaLink="false">/1live_planb_reportage_made_by_wdr_20130904.mp3</guid>
  <enclosure url="http://medien.wdr.de/m/1378303880/radio/planbreportage/1live_planb_reportage_made_by_wdr_20130904.mp3" length="17567124" type="audio/mpeg" />
  <link>http://medien.wdr.de/m/1378303880/radio/planbreportage/1live_planb_reportage_made_by_wdr_20130904.mp3</link>
</item>

<item>
  <title>1LIVE - Plan B Reportage: Vegan ist der Plan (19.08.2013)</title>
  <pubDate>Mon, 19 Aug 2013 00:00:00 +0200</pubDate>
  <description> © WDR 2013</description>
  <guid isPermaLink="false">/1live_planb_reportage_made_by_wdr_20130819.mp3</guid>
  <enclosure url="http://medien.wdr.de/m/1376937347/radio/planbreportage/1live_planb_reportage_made_by_wdr_20130819.mp3" length="17420178" type="audio/mpeg" />
  <link>http://medien.wdr.de/m/1376937347/radio/planbreportage/1live_planb_reportage_made_by_wdr_20130819.mp3</link>
</item>
</channel>
</rss>
'''

def with_dummy_feed(monkeypatch, status=200, href=None,
    return_etag=None, return_modified=None):

    def mock_fetch_feed(url, etag=None, modified=None):
        feed = feedparser.parse(FEED_DATA)
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


class DummyEntry(object):

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.enclosures = kwargs.get('enclosures', [])
        self.published_parsed = kwargs.get(
            'published_parsed',(2013,9,10,11,12,13,0))
        self.data = kwargs

    def get(self, name, fallback=None):
        return self.data.get(name, fallback)


class DummyEnclosure(object):

    def __init__(self, **kwargs):
        self.type = kwargs.get('type')
        self.href = kwargs.get('href', 'http://example.com/download')
        self.data = kwargs

    def get(self, name, fallback=None):
        return self.data.get(name, fallback)


def test_load_subscription_from_file(tmpdir):
    '''Load a subscription from its config file.'''
    load_from = tmpdir.join('the_name')
    load_from.write('\n'.join([
        '[subscription]',
        'url=http://example.com/feed',
        'max_episodes = 30',
    ]))

    sub = Subscription.from_file(str(load_from), 'content_dir', 'cache_dir')

    assert sub.name == 'the_name'
    assert sub.feed_url == 'http://example.com/feed'
    assert sub.max_episodes == 30


def test_load_nonexisting_raises_error():
    '''Trying to load a Subscription from a non-existing config file
    must raise a NoSubscriptionError.'''
    with pytest.raises(NoSubscriptionError):
        sub = Subscription.from_file(
            'does-not-exist', 'content_dir', 'cache_dir')


def test_save(tmpdir, sub):
    sub.max_episodes = 123
    sub.save()
    filename = os.path.join(sub.config_dir, 'name')
    with open(filename) as f:
        lines = f.readlines()

    assert 'http://example.com' in ''.join(lines)
    assert '123' in ''.join(lines)


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
    non_audio_enclosure = DummyEnclosure(type='video/mpeg')
    unknown_enclosure = DummyEnclosure()
    assert not sub._accept(existing, enclosure, 0)
    assert sub._accept(existing, enclosure, 1)
    assert sub._accept(not_existing, enclosure, 0)
    assert not sub._accept(not_existing, non_audio_enclosure, 0)
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
    requested_urls = []

    def mock_download(url, dst):
        requested_urls.append(url)
        with open(dst, 'w') as f:
            f.write('something')
    monkeypatch.setattr(model, 'download', mock_download)

    sub._process_feed_entry(entry)

    assert sub._in_index(entry, 0)
    assert sub._in_index(entry, 1)
    assert os.path.isfile(sub._local_file(entry, 0))
    assert os.path.isfile(sub._local_file(entry, 1))
    assert sub._local_file(entry, 0) != sub._local_file(entry, 1)
    assert href1 in requested_urls
    assert href2 in requested_urls
    assert not sub._in_index(entry, 3)
    assert href3 not in requested_urls


def test_apply_updates_max_episodes():
    '''in apply updates, max entries to be processed
    is max_episodes for this subscription.
    '''
    assert False, 'No test written'


def test_apply_updates_error_handling():
    '''Error for one feed entry should not stop us.'''
    assert False, 'No test written'


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


def test_downloaded_file_perms(monkeypatch):
    '''Assert that a downloaded file has the correct permissions.'''
    # monkeypatch urrlib.urlretrieve(url, dst)
    assert False, 'No test written'


def test_download_error():
    assert False, 'No test written'


def test_generate_enclosure_filename():
    enclosure = DummyEnclosure(type='audio/mpeg', href='does-not-matter')
    entry = DummyEntry(
        id='the-id',
        published_parsed=(2013,9,10,11,12,13,0),
        enclosures=[enclosure,],
    )

    filename = model.generate_filename_for_enclosure(entry, 0, enclosure)
    assert filename == '2013-09-10_11-12-13_the-id_0.mp3'


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


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
