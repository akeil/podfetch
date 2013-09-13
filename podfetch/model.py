#-*- coding: utf-8 -*-
'''
Podfetch Models

Format for subscription files::

    [subscription]
    url = http://example.com/feed

'''
import os
import stat
import logging
import tempfile
import shutil
from collections import namedtuple

try:
    import configparser  # python 3.x
except ImportError:
    import ConfigParser as configparser  # python 2.x

try:
    from urllib.request import urlretrieve  # python 3.x
except ImportError:
    from urllib import urlretrieve  # python 2.x

import feedparser

from podfetch.exceptions import NoSubscriptionError
from podfetch.exceptions import FeedGoneError
from podfetch.exceptions import FeedNotFoundError


log = logging.getLogger(__name__)


OK = 0
SOME_EPISODES_FAILED = 1
ALL_EPISODES_FAILED = 2


ContentTypeInfo = namedtuple('ContentTypeInfo', 'file_ext')

SUPPORTED_CONTENT = {
    'audio/mpeg': ContentTypeInfo(file_ext='mp3'),
    'audio/ogg': ContentTypeInfo(file_ext='ogg'),
    'audio/flac': ContentTypeInfo(file_ext='flac'),
}


class Subscription(object):
    '''Represents a RSS/Atom feed that the user has subscribed.
    ``Subscription`` instances are based on a config-file
    (one for each subscription) and represent the data from that file.

    ``Subscription`` instances are normally created and used by the
    :class:`Podfetch` application class.

    Provides methods to :method:`update` itself from the RSS-feed.

    :var str name:
        The name of the subscription and also
        the name of its config-file
        and the directory in which downloaded episodes are stored
        and the name och cache-files generated for this subscription.
    :var str feed_url:
        The URL for the podcast-feed.
        Read from the confoig file.
    :var int max_episodes:
        The maximum number of episodes to keep downloaded.
        Read from the confoig file.
    '''

    def __init__(self, name, feed_url, config_dir, content_dir, cache_dir,
        max_episodes=-1):
        self.name = name
        self.feed_url = feed_url
        self.content_dir = os.path.join(content_dir, self.name)
        self.cache_dir = cache_dir
        self.max_episodes = max_episodes
        self.config_dir = config_dir

        self.index_file = os.path.join(
            self.cache_dir, '{}.index'.format(self.name))
        self.index = {}
        self._load_index()

    def save(self):
        '''Save this subscription to an ini-file in the given
        directory. The filename will be the ``name`` of this subscription.

        :param str dirname:
            The directory in which the ini-file is placed.
        '''
        cfg = configparser.ConfigParser()
        cfg.add_section('subscription')
        cfg.set('subscription', 'url', self.feed_url)
        cfg.set('subscription', 'max_episodes', str(self.max_episodes))
        filename = os.path.join(self.config_dir, self.name)
        log.debug(
            'Save Subscription {!r} to {!r}.'.format(self.name, filename))
        with open(filename, 'w') as fp:
            cfg.write(fp)

    @classmethod
    def from_file(cls, path, content_dir, cache_dir):
        '''Load a ``Subscription`` from its config file.

        :rtype object:
            A Subscription instance.
        :raises:
            NoSubscriptionError if no config file exists.
        '''
        cfg = configparser.ConfigParser()
        read_from = cfg.read(path)
        if not read_from:
            raise NoSubscriptionError(
                'No config file exists at {!r}.'.format(path))

        log.debug('Read subscription from {!r}.'.format(path))
        config_dir, name = os.path.split(path)
        feed_url = cfg.get('subscription', 'url')
        try:
            max_episodes = cfg.getint('subscription', 'max_episodes')
        except configparser.NoOptionError:
            max_episodes = -1
        return cls(name, feed_url, config_dir, content_dir, cache_dir,
            max_episodes=max_episodes)


    def _load_index(self):
        try:
            with open(self.index_file) as f:
                lines = f.readlines()
        except IOError as e:
            if e.errno == os.errno.ENOENT:
                lines = []
            else:
                raise

        self.index = {}
        for line in lines:
            id_, local_path = line.split('\t')
            self.index[id_] = local_path

    def _save_index(self):
        if self.index:
            with open(self.index_file, 'w') as f:
                for id_, local_path in self.index.items():
                    f.write('{}\t{}\n'.format(id_, local_path))
        else:
            try:
                os.unlink(self.index_file)
            except OSError as e:
                if e.errno != os.errno.ENOENT:
                    raise

    def _add_to_index(self, entry, enclosure_number, local_filename):
        id_ = '{}_{}'.format(entry.id, enclosure_number)
        self.index[id_] = local_filename

    def _in_index(self, entry, enclosure_number):
        return self._local_file(entry, enclosure_number) is not None

    def _local_file(self, entry, enclosure_number):
        id_ = '{}_{}'.format(entry.id, enclosure_number)
        return self.index.get(id_)

    def update(self):
        '''fetch the RSS/Atom feed for this podcast and download any new
        episodes.

        :rtype int:
            Error code indicating the result of individual downloads.
            ``0``: OK,
            ``1``: some episodes failed,
            ``2``: all episodes failed.
        :raises:
            In addition to the error code, a :class:`FeedNotFoundError`
            or :class:`FeedGoneError` can be raised.
        '''
        etag, modified = self._get_cached_headers()
        feed = _fetch_feed(self.feed_url, etag=etag, modified=modified)

        if feed.status == 304:
            log.info('Feed for {!r} is not modified.'.format(self.name))
            return OK
        elif feed.status == 301:  # moved permanent
            log.info('Received status 301, change url for subscription.')
            self.feed_url = feed.href
            self.save()

        try:
            rv = self._apply_updates(feed)
        finally:
            self._save_index()
        # store etag, modified only _after_ successful update
        self._store_cached_headers(feed.get('etag'), feed.get('modified'))
        return rv

    def _apply_updates(self, feed):
        errors = 0
        for index, entry in enumerate(feed.entries):
            try:
                self._process_feed_entry(entry)
                num_processed = index + 1
                if num_processed == self.max_episodes:
                    break
            except Exception as e:
                log.error(('Failed to fetch entry for feed {n!r}.'
                    ' Error was: {e}').format(n=self.name, e=e))
                errors += 1

        if errors == len(feed.entries):
            return ALL_EPISODES_FAILED
        elif errors != 0:
            return SOME_EPISODES_FAILED
        else:
            return OK

    def _process_feed_entry(self, entry):
        # metadata
        title = entry.get('title', '')
        author = ''
        published = ''

        enclosures = entry.get('enclosures', [])
        for index, enclosure in enumerate(enclosures):
            if self._accept(entry, enclosure, index):
                filename = generate_filename_for_enclosure(
                    entry, index, enclosure)
                require_directory(self.content_dir)
                dst_path = os.path.join(self.content_dir, filename)
                download(enclosure.href, dst_path)
                self._add_to_index(entry, index, dst_path)

    def _accept(self, entry, enclosure, enclosure_num):
        content_type = enclosure.get('type', '')
        if not content_type.startswith('audio'):
            return False

        if self._in_index(entry, enclosure_num):
            return False

        return True

    def _get_cached_headers(self):

        def read(path):
            try:
                with open(path) as f:
                    content = f.read()
                    return content or None
            except IOError as e:
                if e.errno == os.errno.ENOENT:
                    return None
                else:
                    raise

        etag_path = os.path.join(
            self.cache_dir, '{}.etag'.format(self.name))
        modified_path = os.path.join(
            self.cache_dir, '{}.modified'.format(self.name))
        etag = read(etag_path)
        modified = read(modified_path)
        return etag, modified

    def _store_cached_headers(self, etag, modified):

        def write(content, path):
            if content:
                require_directory(os.path.dirname(path))
                try:
                    with open(path, 'w') as f:
                        f.write(content)
                except IOError as e:
                    log.error(e)
            else:
                try:
                    os.unlink(path)
                except OSError as e:
                    if e.errno != os.errno.ENOENT:
                        raise

        etag_path = os.path.join(
            self.cache_dir, '{}.etag'.format(self.name))
        modified_path = os.path.join(
            self.cache_dir, '{}.modified'.format(self.name))
        write(etag, etag_path)
        write(modified, modified_path)


def _fetch_feed(url, etag=None, modified=None):
    feed = feedparser.parse(url, etag=etag, modified=modified)

    if feed.status == 410:  # HTTP Gone
        raise FeedGoneError(
            'Request for URL {!r} returned HTTP 410.'.format(feed_url))
    elif feed.status == 404:  # HTTP Not Found
        raise FeedNotFoundError(
            'Request for URL {!r} returned HTTP 404.'.format(feed_url))
    # TODO AuthenticationFailure

    return feed


def file_extension_for_mime(mime):
    '''Get the appropriate file extension for a given mime-type.

    :param str mim:
        The content type, e.g. "audio/mpeg".
    :rtype str:
        The associated file extension *without* a dot ("."),
        e.g. "mp3".
    '''
    try:
        return SUPPORTED_CONTENT[mime.lower()].file_ext
    except (KeyError, AttributeError):
        raise ValueError('Unupported content type {!r}.'.format(mime))


def safe_filename(unsafe):
    '''Convert a string so that it is save for use as a filename.
    :param str unsafe:
        The potentially unsafe string.
    :rtype str:
        A string safe for use as a filename.
    '''
    safe = unsafe.replace('/', '_')
    safe = safe.replace('\\', '_')
    safe = safe.replace(':', '_')
    return safe


def generate_filename_for_enclosure(entry, index, enclosure):
    name_template = '{timestamp}_{name}_{index}.{ext}'
    published = entry.published_parsed
    timestamp = ('{year}-{month:0>2d}-{day:0>2d}'
        '_{hour:0>2d}-{minute:0>2d}-{second:0>2d}').format(
        year=published[0],
        month=published[1],
        day=published[2],
        hour=published[3],
        minute=published[4],
        second=published[5],
    )

    basename, ext = os.path.splitext(entry.id)
    known_extensions = ('.mp3', '.ogg', '.flac')
    if ext in known_extensions:
        name = basename
    else:
        name = entry.id

    return safe_filename( name_template.format(
        timestamp=timestamp,
        name=name,
        index=index,
        ext=file_extension_for_mime(enclosure.type)
    ))


def download(download_url, dst_path):
    '''Download whatever is located at ``download_url``
    and store it at ``dst_path``.
    '''
    log.info('Download file from {!r} to {!r}.'.format(
        download_url, dst_path))
    __, tempdst = tempfile.mkstemp()
    try:
        urlretrieve(download_url, tempdst)
        shutil.move(tempdst, dst_path)
        # desired permissions are -rw-r--r
        perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(dst_path, perms)
    finally:
        try:
            os.unlink(tempdst)
        except os.error as e:
            if e.errno != os.errno.ENOENT:
                raise


def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as e:
        if e.errno != os.errno.EEXIST:
            raise
