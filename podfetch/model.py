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
import itertools
import json
import logging
import os
import re
import shutil
import stat
from collections import namedtuple
from datetime import datetime

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


ContentTypeInfo = namedtuple('ContentTypeInfo', 'file_ext')


SUPPORTED_CONTENT = {
    'audio/mpeg': ContentTypeInfo(file_ext='mp3'),
    'audio/mp4': ContentTypeInfo(file_ext='m4a'),
    'audio/ogg': ContentTypeInfo(file_ext='ogg'),
    'audio/flac': ContentTypeInfo(file_ext='flac'),
    'video/mpeg': ContentTypeInfo(file_ext='mp4')
}

# for generating enclosure-filenames
DEFAULT_FILENAME_TEMPLATE = '{pub_date}_{id}'

# section in subscription ini's
SECTION = 'subscription'

# cache keys
CACHE_ETAG = 'etag'
CACHE_MODIFIED = 'modified'
CACHE_ALL = [CACHE_ETAG, CACHE_MODIFIED,]


try:  # py 3.x
    from datetime import timezone
    UTC = timezone.utc
except ImportError:  # py 2.x
    from datetime import tzinfo
    from datetime import timedelta

    _ZERO = timedelta(0)

    class _UTC(tzinfo):

        def utcoffset(self, dt):
            return _ZERO

        def tzname(self, dt):
            return 'UTC'

        def dst(self, dt):
            return _ZERO

    UTC = _UTC()


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
    :var bool enabled:
        Whether this Subscription is *enabled*. Subscriptions which are
        disabled are not updated.
        Defaults to *True*.
    :var str filename_template:
        Template string used to generate the filenames for downloaded episodes.
    '''

    def __init__(self, name, feed_url,
        config_dir, index_dir, default_content_dir, cache_dir,
        title=None, max_episodes=-1, content_dir=None, enabled=True,
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
        self.enabled = enabled
        self.filename_template = filename_template
        self.app_filename_template = app_filename_template

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

    @property
    def index_file(self):
        '''Absolute path to the index file for this Subscription.'''
        return os.path.join(self.index_dir, '{}.json'.format(self.name))

    def save(self, path=None):
        '''Save this subscription to an ini-file in the given
        directory. The filename will be the ``name`` of this subscription.

        :param str path:
            *optional*, path to the file to save to.
            Default is ``config_dir/name``.
        '''
        cfg = configparser.ConfigParser()
        cfg.add_section(SECTION)

        def _set(key, value):
            if value:  # will lose max_episodes = 0
                cfg.set(SECTION, key ,value)

        _set('url', self.feed_url)
        _set('max_episodes', str(self.max_episodes))
        _set('enabled', 'yes' if self.enabled else 'no')
        _set('title', self.title)
        _set('filename_template', self.filename_template)
        _set('content_dir', self._content_dir)

        filename = path or os.path.join(self.config_dir, self.name)
        log.debug(
            'Save Subscription {!r} to {!r}.'.format(self.name, filename))
        require_directory(os.path.dirname(filename))
        with open(filename, 'w') as fp:
            cfg.write(fp)

    @classmethod
    def from_file(cls, path, index_dir, app_content_dir, cache_dir):
        '''Load a ``Subscription`` from its config file.

        :param str path:
            File to load from.
        :param str index_dir:
            Base directory in which the loaded Subscription should located
            it's ``index_file``.
        :param str app_content_dir:
            Base directory to which the Subscription should save downloaded
            episodes *unless* a content directory is configured in the supplied
            ini file.
        :param str cache_dir:
            Directory to store cache files.
        :rtype object:
            A Subscription instance.
        :raises:
            NoSubscriptionError if no config file exists.
        '''
        cfg = configparser.ConfigParser()
        # possible errors:
        # file does not exist
        # file is no in ini format
        # missing sections and options
        try:
            read_from = cfg.read(path)
        except configparser.Error:
            raise NoSubscriptionError(
                'Failed to read subscription from {!r}.'.format(path))
        if not read_from:
            raise NoSubscriptionError(
                'No config file exists at {!r}.'.format(path))

        log.debug('Read subscription from {!r}.'.format(path))

        def get(key, default=None, fmt=None):
            rv = default
            try:
                if fmt == 'int':
                    rv = cfg.getint(SECTION, key)
                elif fmt == 'bool':
                    rv = cfg.getboolean(SECTION, key)
                else:
                    rv = cfg.get(SECTION, key)
            except (configparser.NoSectionError, configparser.NoOptionError):
                log.debug('Could not read {k!r} from ini.'.format(k=key))
            return rv

        feed_url = get('url')  # mandatory property 'url'
        if not feed_url:
            raise NoSubscriptionError(
                'Failed to read URL from {p!r}.'.format(p=path))

        config_dir, name = os.path.split(path)
        return cls(
            name, feed_url,
            config_dir, index_dir, app_content_dir, cache_dir,
            title=get('title'),
            max_episodes=get('max_episodes', default=-1, fmt='int'),
            enabled=get('enabled', default=True, fmt='bool'),
            content_dir=get('content_dir'),
            filename_template=get('filename_template')
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
        self._cache_forget()
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
        feed = _fetch_feed(
            self.feed_url,
            etag=self._cache_get(CACHE_ETAG),
            modified=self._cache_get(CACHE_MODIFIED),
        )
        log.debug('Feed status is {}'.format(feed.status))

        if feed.status == 304:  # not modified
            if force:
                log.debug('Forced download, ignore HTTP etag and modified.')
            else:
                log.info('Feed for {!r} is not modified.'.format(self.name))
                return
        elif feed.status == 301:  # moved permanent
            log.info('Received status 301, change url for subscription.')
            self.feed_url = feed.href
            self.save()

        try:
            self._update_entries(feed, force=force)
        finally:
            self._save_index()
        # store etag, modified after *successful* update
        self._cache_put(CACHE_ETAG, feed.get('etag'))
        self._cache_put(CACHE_MODIFIED, feed.get('modified'))

    def _update_entries(self, feed, force=False):
        for entry in feed.get('entries', []):
            id_ = id_for_entry(entry)
            episode = self._episode_for_id(id_)
            if episode:
                pass
            else:
                episode = Episode.from_entry(self, entry)
                self.episodes.append(episode)

            try:
                episode.download(force=force)
            except Exception as e:
                log.error(('Failed to update episode {epi}.'
                    ' Error was {e!r}').format(epi=episode, e=e))

    def _episode_for_id(self, id_):
        for episode in self.episodes:
            if episode.id == id_:
                return episode

    def purge(self, simulate=False):
        '''Delete old episodes, keep only *max_episodes*.
        If ``self.max_episodes`` is 0 or less, an unlimited number of
        allowed episodes is assumed and nothing is deleted.

        :param bool simulate:
            List filenames to be deleted
            but do not delete anything.
        :rtype list:
            list of absolute paths to be deleted.
        '''
        # sort by date received - oldest come first
        # select everything EXCEPT the ones to keep
        episodes = sorted(self.episodes, key=lambda x: x.pubdate)
        keep = max(self.max_episodes, 0)  # -1 to 0
        selected = episodes[:-keep]

        log.info('Purge {!r}, select {} episodes to delete ({} to keep)'.format(
            self, len(selected), keep))

        deleted_files = []
        for episode in selected:
            deleted_files += [filename for __, __, filename in episode.files]
            if not simulate:
                episode.delete_local_files()
                self.episodes.remove(episode)

        return deleted_files

    def rename(self, newname, move_files=False):
        log.info('Rename subscription {o!r} -> {n!r}.'.format(
            o=self.name, n=newname))

        log.info('Forget cache entries.')
        cached = {}
        for key in CACHE_ALL:
            cached[key] = self._cache_get(key)
        self._cache_forget(*CACHE_ALL)

        old_index_file = self.index_file
        old_content_dir = self.content_dir

        self.name = newname
        self.save()  # TODO: let caller `save()` ?
        if move_files:
            self.rename_files()

        # index was loaded - save it to the new name
        log.info('Save index under new name {f!r}.'.format(f=self.index_file))
        self._save_index()
        if self.index_file != old_index_file:
            log.info('Delete old index file {f!r}.'.format(f=old_index_file))
            os.unlink(old_index_file)

        log.info('Save cache under new name.')
        for key, value in cached.items():
            self._cache_put(key, value)

        try:
            os.rmdir(old_content_dir)
        except OSError as e:
            log.warning(('Could not delete directory {d!r}.'
                ' Error was {e}.').format(d=old_content_dir, e=e))
            if e.errno not in (os.errno.ENOENT, os.errno.ENOTEMPTY):
                raise

    def rename_files(self):
        '''Rename file to match a new filename pattern or content dir.'''
        log.info('Rename downloaded episodes for {n!r}'.format(n=self.name))
        for episode in self.episodes:
            episode.move_local_files()
        self._save_index()

    # cache ------------------------------------------------------------------

    def _cache_get(self, key):
        result = None
        try:
            with open(self._cache_path(key)) as f:
                result = f.read()
        except IOError as e:
            if e.errno != os.errno.ENOENT:
                raise

        return result or None  # convert '' to None

    def _cache_put(self, key, value):
        path = self._cache_path(key)
        forget = not bool(value)
        if not forget:
            try:
                require_directory(os.path.dirname(path))
                with open(path, 'w') as f:
                    f.write(value)
            except Error as e:
                log.error('Error writing cache file: {!r}'.format(e))
                forget = True

        # value was empty or writing failed
        if forget:
            self._cache_forget(key)

    def _cache_forget(self, *keys):
        '''Remove entries for the given cache keys.
        Remove all entries if no key is given.'''
        for key in keys or CACHE_ALL:
            try:
                delete_if_exists(self._cache_path(key))
            except Exception as e:
                log.error('Failed to delete cache {!r} ofr {!r}.'.format(
                    key, self.name))

    def _cache_path(self, key):
        return os.path.join(self.cache_dir, '{}.{}'.format(self.name, key))

    def __repr__(self):
        return '<Subscription name={s.name!r}>'.format(s=self)


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
        today = datetime.now(UTC).timetuple()
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

        # if pubdate is in the future, set it to 'now'
        today = datetime.now(UTC)
        pubdate = entry.published_parsed
        if pubdate:
            fromentry = datetime(
                pubdate[0],  # year
                pubdate[1],  # month
                pubdate[2],  # day
                pubdate[3],  # hour
                pubdate[4],  # minute
                pubdate[5],  # second
                tzinfo=UTC
            )

            if fromentry > today:
                pubdate = today.timetuple()
        else:
            pubdate = today.timetuple()

        return class_(parent_subscription, id_,
            title=entry.title,
            description=entry.description,
            pubdate=pubdate,
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
            local_file = unique_filename(local_file)

        log.info('Download from {!r}.'.format(url))
        log.info('Local file is {!r}.'.format(local_file))
        require_directory(os.path.dirname(local_file))
        download(url, local_file)
        return local_file

    def _generate_filename(self, content_type, index):
        '''Generate a filename for an enclosure with the given index.

        The filename will be generated from ``filename_template`` and passed
        through ``safe_filename``.

        If the template does not contain a file extension, one will be added
        automatically.

        :param str content_type:
            The content type of the enclosure.
            Used to determine the file extension.
        :param int index:
            0-based index for episodes with multiple files
        :rtype str:
            returns the generated filename.
        '''
        template = self.subscription.filename_template \
                   or self.subscription.app_filename_template \
                   or DEFAULT_FILENAME_TEMPLATE

        ext = file_extension_for_mime(content_type)
        kind = content_type.split('/')[0]
        values = {k: pretty(v) for k, v in {
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
        }.items()}
        filename = safe_filename(template.format(**values))

        # template may or may not include file-ext
        #  - make sure we append a file-extension
        #  - maybe insert the index between ext and basename
        basename, ext_from_template = os.path.splitext(filename)
        known_exts = [x.file_ext for x in SUPPORTED_CONTENT.values()]
        if ext_from_template in known_exts:
            filename = basename

        # in case we have multiple files for an episode,
        # add an index-suffix for every file but the first.
        if index:
            filename = '{}-{:0>2d}'.format(filename, index)

        filename = '{}.{}'.format(filename, ext)
        return safe_filename(filename)

    def delete_local_files(self):
        '''Delete the local files for this episode (if they exist).'''
        while self.files:
            __, __, local_file = self.files.pop()
            delete_if_exists(local_file)

        # TODO remove empty directories

    def move_local_files(self):
        files = self.files[:]
        for index, details in enumerate(files):
            url, content_type, oldpath = details
            newpath = os.path.join(
                self.subscription.content_dir,
                self._generate_filename(content_type, index)
            )
            if newpath != oldpath:
                newpath = unique_filename(newpath)
                dirname = os.path.dirname(newpath)
                require_directory(dirname)
                log.debug('Move {o!r} -> {n!r}'.format(o=oldpath, n=newpath))
                try:
                    shutil.move(oldpath, newpath)
                    self.files[index] = (url, content_type, newpath)
                except OSError as e:
                    if e.errno != os.errno.ENOENT:
                        raise
                    log.warning(('Failed to rename file {f!r}.'
                        ' File does not exist.').format(f=oldpath))

    def __repr__(self):
        return '<Episode id={s.id!r}>'.format(s=self)


def _fetch_feed(url, etag=None, modified=None):
    '''Download an parse a RSS feed.'''
    feed = feedparser.parse(url, etag=etag, modified=modified)

    if feed.status == 410:  # HTTP Gone
        raise FeedGoneError(
            'Request for URL {!r} returned HTTP 410.'.format(url))
    elif feed.status == 404:  # HTTP Not Found
        raise FeedNotFoundError(
            'Request for URL {!r} returned HTTP 404.'.format(url))
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


def pretty(unpretty):
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

    rv = str(unpretty)

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
        rv = rv.replace(text, replacement)

    # delete non-ascii chars and whitespace
    import string
    allowed_chars = string.ascii_letters + string.digits + string.punctuation
    rv = ''.join(c for c in rv if c in allowed_chars)

    # replace multiple occurence of separators with one separator
    # "---" becomes "-"
    separators = ['-', '_', '.']
    for sep in separators:
        pattern = '[{}]+'.format(sep)
        rv = re.sub(pattern, sep, rv)

    return rv


def safe_filename(unsafe):
    '''Convert a string so that it is save for use as a filename.
    :param str unsafe:
        The potentially unsafe string.
    :rtype str:
        A string safe for use as a filename.
    '''
    safe = unsafe.replace('\\', '_')
    safe = safe.replace(':', '_')
    return safe


def unique_filename(path, suffix=None):
    '''Given an absolute path, check if a file with that name exists.
    If yes, append ``suffix + counter`` to the filename until it is unique.'''
    candidate = path
    counter = 0
    max_recurse = 999
    suffix = suffix or '.'
    while os.path.isfile(candidate):
        if counter > max_recurse:
            raise RuntimeError('Max recursion depth reached.')
        name, ext = os.path.splitext(path)
        candidate = '{n}{s}{c:0>3d}{e}'.format(n=name, s=suffix, c=counter, e=ext)
        counter += 1

    return candidate


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
