#-*- coding: utf-8 -*-
'''Podfetch Models

Format for subscription files::

    [subscription]
    url = http://example.com/feed

Creating Subscription instances

Instances of the ``Subscription`` class are normally created by the
``Podfetch`` application in one of two ways:

    create new
        uses Subscription.__init__()

    load existing
        uses Subscription.from_file()
        which internally uses Subscription.__init__()
        passing values from the config file.
    
'''
import os
import stat
import logging
import shutil
import itertools
import re
from collections import namedtuple
from datetime import datetime
import json

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
    'video/mpeg': ContentTypeInfo(file_ext='mp4')
}

# for generating enclosure-filenames
DEFAULT_FILENAME_TEMPLATE = '{pub_date}_{id}'


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
    :var str config_dir:
        Base directory where the config file for this subscription is kept.
        File name for config file is ``/{CONFIG_DIR}/{SUBSCRIPTION_NAME}``.
    :var str index_dir:
        Base directory for the index file of this subscription.
        File name for index file is ``/{INDEX_DIR}/{SUBSCRIPTION_NAME}``.
    :var str default_content_dir:
        The default content directory for the application.
        Individual subscriptions download to
        ``/{DEFAULT_CONTENT_DIR}/{SUBSCRIPTION_NAME}``
        *unless* an individual ``content_dir`` is defined.
    :var str content_dir:
        Download directory for episodes, overrides the ``default_content_dir``
        for this subscription only. Note that this directory is not combined
        with the subscription name.
    :var int max_episodes:
        The maximum number of episodes to keep downloaded.
        Read from the config file.
    :var str filename_template:
        Template string used to generate the filenames for downloaded episodes.
    '''

    def __init__(self, name, feed_url,
        config_dir, index_dir, default_content_dir, cache_dir,
        title=None, max_episodes=-1, content_dir=None,
        filename_template=None, app_filename_template=None):

        self.name = name
        self.feed_url = feed_url
        self.title = title or name
        self.index_dir = index_dir
        self._default_content_dir = default_content_dir
        self._content_dir = content_dir
        self.cache_dir = cache_dir
        self.max_episodes = max_episodes
        self.config_dir = config_dir
        self.filename_template = filename_template
        self.app_filename_template = app_filename_template

        self.index_file = os.path.join(
            self.index_dir, '{}.json'.format(self.name))
        self.episodes = []
        self._load_index()

    @property
    def content_dir(self):
        '''The content directory to which episodes are downloaded.

        This is
        - either a subdirectory within the application wide ``content_dir``,
          named after this subscription
        - or an indivdually defined directory for this subscription only
        '''
        return self._content_dir or os.path.join(
            self._default_content_dir,
            self.name
        )

    @content_dir.setter
    def content_dir(self, dirname):
        # convert '' to None, but NOT None to 'None'
        self._content_dir = None if not str(dirname) else dirname

    def save(self):
        '''Save this subscription to an ini-file in the given
        directory. The filename will be the ``name`` of this subscription.

        :param str dirname:
            The directory in which the ini-file is placed.
        '''
        cfg = configparser.ConfigParser()
        sec = 'subscription'
        cfg.add_section(sec)

        _set = lambda k, v: cfg.set(sec, k,v)

        _set('url', self.feed_url)
        _set('max_episodes', str(self.max_episodes))

        if self.title:
            _set('title', self.title)

        if self.filename_template:
            _set('filename_template', self.filename_template)

        if self._content_dir:
            _set('content_dir', self._content_dir)

        filename = os.path.join(self.config_dir, self.name)
        log.debug(
            'Save Subscription {!r} to {!r}.'.format(self.name, filename))
        require_directory(self.config_dir)
        with open(filename, 'w') as fp:
            cfg.write(fp)

    @classmethod
    def from_file(cls, path, index_dir, app_content_dir, cache_dir):
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
        sec = 'subscription'

        # mandatory properties
        config_dir, name = os.path.split(path)
        feed_url = cfg.get(sec, 'url')

        # optional properties
        try:
            max_episodes = cfg.getint(sec, 'max_episodes')
        except configparser.NoOptionError:
            max_episodes = -1

        try:
            filename_template = cfg.get(sec, 'filename_template')
        except configparser.NoOptionError:
            filename_template = None

        try:
            content_dir = cfg.get(sec, 'content_dir')
        except configparser.NoOptionError:
            content_dir = None

        try:
            title = cfg.get(sec, 'title')
        except configparser.NoOptionError:
            title = None

        return cls(
            name, feed_url,
            config_dir, index_dir, app_content_dir, cache_dir,
            title=title,
            max_episodes=max_episodes,
            content_dir=content_dir,
            filename_template=filename_template
        )

    def _load_index(self):
        try:
            with open(self.index_file) as f:
                data = json.load(f)
        except IOError as e:
            if e.errno == os.errno.ENOENT:
                data = []
            else:
                raise

        self.episodes = [Episode.from_dict(self, d) for d in data]

    def _save_index(self):
        '''Save the index file for this subscription to disk.'''
        data = [e.as_dict() for e in self.episodes]
        if data:
            require_directory(os.path.dirname(self.index_file))
            with open(self.index_file, 'w') as f:
                json.dump(data, f)
        else:
            delete_if_exists(self.index_file)

    def delete(self, keep_episodes=False):
        '''Delete this subscription.
        Includes:
        - cached header values in ``cache_dir``
        - index file in ``index_dir``
        - episode files, if ``keep_episodes`` is *False*
        - the ``content_dir``, if ``keep_episodes`` is *False*

        Does **not include** the subscription file,
        which is managed by the application.
        '''
        self._clear_cached_headers()
        delete_if_exists(self.index_file)
        if not keep_episodes:
            for episode in self.episodes:
                episode.delete_local_files()
            try:
                os.rmdir(self.content_dir)
            except os.error as e:
                if e.errno == os.errno.ENOENT:
                    pass
                elif e.errno == os.errno.ENOTEMPTY:
                    log.warning(('Directory {!r} was not removed because it'
                        ' is not empty.').format(self.content_dir))
                    pass
                else:
                    raise

    def update(self, force=False):
        '''fetch the RSS/Atom feed for this podcast and download any new
        episodes.

        :param bool force:
            *optional*, if *True*, force downloading the feed even if
            HTTP headers indicate it was not modified.
            Also, re-download all episodes, even if they already exist.
            Defaults to *False*.
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
        log.debug('Feed status is {}'.format(feed.status))

        if feed.status == 304:  # not modified
            if force:
                log.debug('Forced download, ignore HTTP etag and modified.')
            else:
                log.info('Feed for {!r} is not modified.'.format(self.name))
                return OK
        elif feed.status == 301:  # moved permanent
            log.info('Received status 301, change url for subscription.')
            self.feed_url = feed.href
            self.save()

        try:
            rv = self._update_entries(feed, force=force)
        finally:
            self._save_index()
        # store etag, modified after *successful* update
        self._store_cached_headers(feed.get('etag'), feed.get('modified'))
        return rv

    def _update_entries(self, feed, force=False):
        errors = 0
        for entry in feed.get('entries', []):
            id_ = id_for_entry(entry)
            episode = self._episode_for_id(id_)
            if episode:
                pass
                # TODO
                # episode.update_from_entry(entry)
            else:
                episode = Episode.from_entry(self, entry)
                self.episodes.append(episode)

            try:
                episode.download(force=force)
            except Exception as e:
                errors += 1
                log.error(('Failed to update episode {epi}.'
                    ' Error was {e!r}').format(epi=episode, e=e))

        if errors == len(feed.entries):
            return ALL_EPISODES_FAILED
        elif errors != 0:
            return SOME_EPISODES_FAILED
        else:
            return OK

    def _episode_for_id(self, id_):
        for episode in self.episodes:
            if episode.id == id_:
                return episode

    @property
    def _etag_path(self):
        return os.path.join(self.cache_dir, '{}.etag'.format(self.name))

    @property
    def _modified_path(self):
        return os.path.join(self.cache_dir, '{}.modified'.format(self.name))

    def _get_cached_headers(self):
        '''Try to get the cached HTTP headers for this subscription.

        :rtype tuple:
            Returns a tuple (etag, modified) with the values for these
            HTTP headers.
        '''

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

        etag = read(self._etag_path)
        modified = read(self._modified_path)
        return etag, modified

    def _store_cached_headers(self, etag, modified):
        '''Store the values for the ``etag`` and ``modified`` headers
        in the cache.
        '''

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

        write(etag, self._etag_path)
        write(modified, self._modified_path)

    def _clear_cached_headers(self):
        '''Forget (delete) the cached values from HTTP headers.'''
        delete_if_exists(self._etag_path)
        delete_if_exists(self._modified_path)


class Episode(object):
    '''Relates to a single entry in a Subscriptions feed.
    There can be one ore more "enclosures" in a feed-entry
    which will be downloaded to local files.

    Can be an episode that was already downloaded or a fresh episode from a
    feed entry.
    '''
    def __init__(self, parent_subscription, id_, **kwargs):
        if not id_:
            raise ValueError('Invalid value for id {!r}.'.format(id_))
        self.id = id_
        if not parent_subscription:
            raise ValueError('Missing required parent_subscription.')
        self.subscription = parent_subscription

        self.title = kwargs.get('title')
        self.description = kwargs.get('description')
        today = datetime.today().timetuple()
        self.pubdate = kwargs.get('pubdate', today)
        self.files = [
            (url, content_type, local)
            for url, content_type, local
            in kwargs.get('files', [])
        ]

    @classmethod
    def from_entry(class_, parent_subscription, entry):
        '''Create an episode from the information in a feed entry.
        :param object entry:
            The feed entry.
        :rtype object:
            an Episode instance.
        '''
        id_ = id_for_entry(entry)
        return class_(parent_subscription, id_,
            title=entry.title,
            description=entry.description,
            pubdate=entry.published_parsed,
            files=[
                (enc.href, enc.type, None)
                for enc in entry.get('enclosures', [])
            ],
        )

    @classmethod
    def from_dict(class_, parent_subscription, data_dict):
        '''Create an Episode instance from the given data.
        Data looks like this::

            {
                'id': 'The ID'
                'title': 'The title,'
                'description': 'The description',
                'pudate': (2000, 1, 1, 15, 31, 2, 3),
                'files': [
                    (source_url, type, local_path),
                    (source_url, type, local_path),
                    ...
                ]
            }

        :param dict data_dict:
            The data to create the Episode from.
        :rtype:
            an Episode instance.
        '''
        id_ = data_dict.get('id')
        return class_(parent_subscription, id_, **data_dict)

    def as_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'pubdate': tuple(self.pubdate),
            'files': [
                (url, content_type, local)
                for url, content_type, local in self.files
            ],
        }

    def download(self, force=False):
        '''Download all enclosures for this episode.
        Update the association (download url => local_file) in ``self.files``.

        :param bool force:
            *optional*, if *True*, downloads enclosures even if
            a local file already exists (overwriting the local file).
            Defaults to *False*.
        '''
        for index, item in enumerate(self.files[:]):
            url, content_type, local_file = item
            want = self._should_download(url, content_type)
            have = self._is_downloaded(url)
            if (want and not have) or (want and force):
                local_file = self._download_one(index, url, content_type,
                    dst_file=local_file)
                self.files[index] = (url, content_type, local_file)
            else:
                log.debug('Skip {!r}.'.format(url))

    def _is_downloaded(self, url):
        '''Tell if the enclosure for the given URL has been downloaded.
        Specifically, if the local file associated with the URL exists.'''
        for existing_url, __, local_file in self.files:
            if url == existing_url:
                return local_file is not None and os.path.isfile(local_file)
        return False

    def _should_download(self, url, content_type):
        return content_type in SUPPORTED_CONTENT

    def _download_one(self, index, url, content_type, dst_file=None):
        '''Download a single enclosure from the given URL.
        Generates a local filename for the enclosure and stores the downloaded
        data there.
        If dst is given, no filename is generated but dst_path is used.
        returns the path to the local file.
        '''
        if dst_file:
            local_file = dst_file
        else:
            filename = self._generate_filename(content_type, index)
            local_file = os.path.join(self.subscription.content_dir, filename)

        log.info('Download from {!r}.'.format(url))
        log.info('Local file is {!r}.'.format(local_file))
        require_directory(os.path.dirname(local_file))
        download(url, local_file)
        return local_file

    def _generate_filename(self, content_type, index):
        '''Generate a filename for an enclosure with the given index.'''
        template = self.subscription.filename_template \
                   or self.subscription.app_filename_template \
                   or DEFAULT_FILENAME_TEMPLATE

        ext = file_extension_for_mime(content_type)
        kind = content_type.split('/')[0]
        values = {
            'subscription_name': self.subscription.name,
            'pub_date': '{}-{:0>2d}-{:0>2d}'.format(*self.pubdate[0:3]),
            'year': '{:0>4d}'.format(self.pubdate[0]),
            'month': '{:0>2d}'.format(self.pubdate[1]),
            'day': '{:0>2d}'.format(self.pubdate[2]),
            'hour': '{:0>2d}'.format(self.pubdate[3]),
            'minute': '{:0>2d}'.format(self.pubdate[4]),
            'second': '{:0>2d}'.format(self.pubdate[5]),
            'title': self.title,
            'feed_title': self.subscription.title,
            'id': self.id,
            'ext': ext,
            'kind': kind,
        }
        filename = safe_filename(template.format(**values))

        # template may or may not include file-ext
        #  - make sure we append a file-extension
        #  - maybe insert the index between ext and basename
        basename, ext_from_template = os.path.splitext(filename)
        known_exts = [x.file_ext for x in SUPPORTED_CONTENT.values()]
        if ext_from_template in known_exts:
            filename = basename

        if index:
            filename = '{}-{:0>2d}'.format(filename, index)

        filename = '{}.{}'.format(filename, ext)
        return safe_filename(pretty_filename(filename))

    def delete_local_files(self):
        '''Delete the local files for this episode (if they exist).'''
        while self.files:
            __, __, local_file = self.files.pop()
            delete_if_exists(local_file)


def _fetch_feed(url, etag=None, modified=None):
    '''Download an parse a RSS feed.'''
    feed = feedparser.parse(url, etag=etag, modified=modified)

    if feed.status == 410:  # HTTP Gone
        raise FeedGoneError(
            'Request for URL {!r} returned HTTP 410.'.format(feed_url))
    elif feed.status == 404:  # HTTP Not Found
        raise FeedNotFoundError(
            'Request for URL {!r} returned HTTP 404.'.format(feed_url))
    # TODO AuthenticationFailure
    # TODO Connection error, Timeouts
    return feed


def id_for_entry(entry):
    entry_id = entry.get('id')
    if entry_id:
        return entry_id
    else:
        return '{}.{}'.format(
            ''.join(str(x) for x in entry.published_parsed),
            entry.get('title', '')
        )
        log.debug('Missing entry-ID, using {!r} instead.'.format(entry.id))

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
        raise ValueError('Unsupported content type {!r}.'.format(mime))


def pretty_filename(unpretty):
    '''Apply some replacements and conversion to the given string
    and return a converted string that makes a "prettier" filename.

    "Pretty" in this case means:
      - replace some special characters with a "_"
      - remove some unwanted characters.

    Use ``safe_filename`` to remove forbidden chars.

    :param str unpretty:
        The string to be converted.
    :rtype str:
        The "pretty"-converted string.
    '''
    if unpretty is None:
        return None

    pretty = unpretty

    translations = [
        (' ', '_'),
        (':', '_'),
        (',', '_'),
        (';', '_'),
        ('/', '_'),
        ('{', '_'),
        ('}', '_'),
        ('&', '+'),
        ('Ä', 'Ae'),
        ('Ö', 'Oe'),
        ('Ü', 'Ue'),
        ('ä', 'ae'),
        ('ö', 'oe'),
        ('ü', 'ue'),
        ('ß', 'ss'),
    ]
    # unwanted ascii chars
    deletions = ['*', '?', '!', '"', '\'', '^', '\\', '´', '`', '<', '>']

    for text, replacement in itertools.chain(translations, [(c, '') for c in deletions]):
        pretty = pretty.replace(text, replacement)

    # delete non-ascii chars and whitespace
    import string
    allowed_chars = string.ascii_letters + string.digits + string.punctuation
    pretty = ''.join(c for c in pretty if c in allowed_chars)

    # replace multiple occurence of separators with one separator
    # "---" becomes "-"
    separators = ['-', '_', '.']
    for sep in separators:
        pattern = '[{}]+'.format(sep)
        pretty = re.sub(pattern, sep, pretty)

    return pretty


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


def download(download_url, dst_path):
    '''Download whatever is located at ``download_url``
    and store it at ``dst_path``.

    :param str dst_path:
        Absolute path to the download destination.
        The parent directory of the destination file
        *must* exist.
    '''
    tempdst, headers = urlretrieve(download_url)
    log.debug('Downloaded to tempdst: {!r}.'.format(tempdst))
    try:
        shutil.move(tempdst, dst_path)
        # desired permissions are -rw-r--r
        perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(dst_path, perms)
    finally:
        delete_if_exists(tempdst)


def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as e:
        if e.errno != os.errno.EEXIST:
            raise


def delete_if_exists(filename):
    '''Delete the given filename (absolute path) if it exists.'''
    try:
        os.unlink(filename)
    except os.error as e:
        if e.errno != os.errno.ENOENT:
            raise
