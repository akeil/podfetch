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
import tempfile
from contextlib import closing
from datetime import datetime

import feedparser
import requests

from podfetch.exceptions import FeedGoneError
from podfetch.exceptions import FeedNotFoundError
from podfetch.timehelper import UTC
from podfetch.utils import require_directory
from podfetch.utils import delete_if_exists


LOG = logging.getLogger(__name__)


# for generating enclosure-filenames
DEFAULT_FILENAME_TEMPLATE = '{pub_date}_{id}'

# cache keys
CACHE_ETAG = 'etag'
CACHE_MODIFIED = 'modified'
CACHE_ALL = [CACHE_ETAG, CACHE_MODIFIED,]


class Subscription:
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
        and the name of cache-files generated for this subscription.
    :var str feed_url:
        The URL for the podcast-feed.
        Read from the confoig file.
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

    def __init__(self,
        name,
        feed_url,
        index_dir,
        default_content_dir,
        title=None,
        max_episodes=-1,
        content_dir=None,
        enabled=True,
        filename_template=None,
        app_filename_template=None,
        supported_content=None):

        self.name = name
        self.feed_url = feed_url
        self.title = title or name
        self.index_dir = index_dir
        self._default_content_dir = default_content_dir
        self._content_dir = content_dir
        self.max_episodes = max_episodes
        self.enabled = enabled
        self.filename_template = filename_template
        self.app_filename_template = app_filename_template
        self.supported_content = supported_content
        self.episodes = []

    @property
    def content_dir(self):
        '''The content directory to which episodes are downloaded.

        This is
        - either a subdirectory within the application wide ``content_dir``,
          named after this subscription
        - or an indivdually defined directory for this subscription only
        '''
        return self._content_dir or os.path.join(self._default_content_dir,
                                                 self.name)

    @content_dir.setter
    def content_dir(self, dirname):
        # convert '' to None, but NOT None to 'None'
        self._content_dir = None if not str(dirname) else dirname

    def delete_downloaded_files(self):
        for episode in self.episodes:
            episode.delete_local_files()
        try:
            os.rmdir(self.content_dir)
        except os.error as err:
            if err.errno == os.errno.ENOENT:
                pass
            elif err.errno == os.errno.ENOTEMPTY:
                LOG.warning(('Directory %r was not removed because it'
                             ' is not empty.'), self.content_dir)
            else:
                raise

    def update(self, storage, force=False):
        '''fetch the RSS/Atom feed for this podcast and download any new
        episodes.

        :param Storage storage:
            Reference to the storage backend.
        :param bool force:
            *optional*, if *True*, force downloading the feed even if
            HTTP headers indicate it was not modified.
            Also, re-download all episodes, even if they already exist.
            Defaults to *False*.
        :raises:
            In addition to the error code, a :class:`FeedNotFoundError`
            or :class:`FeedGoneError` can be raised.
        '''
        feed = _fetch_feed(
            self.feed_url,
            etag=storage.cache_get(self.name, CACHE_ETAG),
            modified=storage.cache_get(self.name, CACHE_MODIFIED),
        )
        LOG.debug('Feed status is %s', feed.status)

        if feed.status == 304:  # not modified
            if force:
                LOG.debug('Forced download, ignore HTTP etag and modified.')
            else:
                LOG.info('Feed for %r is not modified.', self.name)
                return
        elif feed.status == 301:  # moved permanent
            LOG.info('Received status 301, change url for subscription.')
            self.feed_url = feed.href

        entries_ok = True
        try:
            entries_ok = self._update_entries(feed, storage, force=force)
        finally:
            entries_ok = False

        # store etag, modified after *successful* update
        if entries_ok:
            storage.cache_put(self.name, CACHE_ETAG, feed.get('etag'))
            storage.cache_put(self.name, CACHE_MODIFIED, feed.get('modified'))

    def _update_entries(self, feed, storage, force=False):
        '''Download content for all feed entries.

        Returns *True* if all downloads were successful,
        *False* if one or more downloads failed.
        '''
        has_errors = False
        for entry in feed.get('entries', []):
            should_save = False
            id_ = id_for_entry(entry)
            episode = self._episode_for_id(id_)
            LOG.debug('Check episode id %r.', id_)
            if episode:
                pass
            else:
                episode = Episode.from_entry(
                    self, self.supported_content, entry)
                if episode.has_attachments:
                    self.episodes.append(episode)
                    should_save = True
                else:
                    LOG.debug(('%r does not have attachments'
                               ' and is ignored.'), episode)
                    continue

            try:
                episode.download(force=force)
                should_save = True
            except Exception as err:
                has_errors = True
                LOG.error('Failed to update episode %s. Error was %r',
                    episode, err)

            if should_save:
                try:
                    storage.save_episode(episode)
                except Exception as err:
                    LOG.error('Failed to save episode %r.', episode)
                    LOG.debug(err, exc_info=True)
                    has_errors = True

            return not has_errors

    def _episode_for_id(self, id_):
        for episode in self.episodes:
            if episode.id == id_:
                return episode

    def purge(self, storage, simulate=False):
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

        LOG.info('Purge %r, select %s episodes to delete (%s to keep)',
            self, len(selected), keep)

        deleted_files = []
        for episode in selected:
            deleted_files += [filename for __, __, filename in episode.files]
            if not simulate:
                episode.delete_local_files()
                storage.delete_episode(episode)

        if not simulate:
            self._remove_empty_directories()

        return deleted_files

    def _remove_empty_directories(self):
        '''Remove directories from this subscription's content dir
        if they are empty.'''
        # list all empty directories below content_dir
        empty_dirs = []
        for base, dirnames, filenames in os.walk(self.content_dir):
            if not dirnames and not filenames:
                empty_dirs.append(base)

        # delete each directory
        # since the parent directory may have become empty,
        # add it to the list of empty dirs
        while empty_dirs:
            path = empty_dirs.pop(0)
            parent = os.path.dirname(path)
            try:
                os.rmdir(path)
                LOG.info('Deleted directory %s', path)
                if parent != self.content_dir:
                    # TODO - does not seem to work
                    if parent not in empty_dirs:
                        empty_dirs.append(parent)
            except OSError as err:
                if err.errno == os.errno.ENOTEMPTY:
                    pass
                else:
                    raise

    def rename(self, storage, newname, move_files=False):
        '''Rename this subscription.

        This will *always* rename files for internal use
        (e.g. inside the *cache_dir*).
        It will *optionally* rename downloaded episodes, moving them to
        a different *content_dir*.
        '''
        LOG.info('Rename subscription %r -> %r.', self.name, newname)

        storage.rename_subscription(self.name, newname)

        old_content_dir = self.content_dir

        self.name = newname
        if move_files:
            self.rename_files()

        try:
            os.rmdir(old_content_dir)
        except OSError as err:
            LOG.warning('Could not delete directory %r. Error was %s.',
                old_content_dir, err)
            if err.errno not in (os.errno.ENOENT, os.errno.ENOTEMPTY):
                raise

    def rename_files(self, storage):
        '''Rename file to match a new filename pattern or content dir.'''
        LOG.info('Rename downloaded episodes for %r', self.name)
        try:
            for episode in self.episodes:
                episode.move_local_files()
        finally:
            storage.save_episodes(self.name, self.episodes)

    def __repr__(self):
        return '<Subscription name={s.name!r}>'.format(s=self)


class Episode(object):
    '''Relates to a single entry in a Subscriptions feed.
    There can be one ore more "enclosures" in a feed-entry
    which will be downloaded to local files.

    Can be an episode that was already downloaded or a fresh episode from a
    feed entry.
    '''
    def __init__(self, parent_subscription, id_, supported_content, **kwargs):
        if not id_:
            raise ValueError('Invalid value for id {!r}.'.format(id_))

        if not parent_subscription:
            raise ValueError('Missing required parent_subscription.')

        self.id = id_
        self.subscription = parent_subscription
        self.supported_content = supported_content or {}

        self.title = kwargs.get('title')
        self.description = kwargs.get('description')
        today = datetime.now(UTC).timetuple()
        self.pubdate = kwargs.get('pubdate', today)
        self.files = [(url, content_type, local)
                      for url, content_type, local
                      in kwargs.get('files', [])]

    @classmethod
    def from_entry(cls, parent_subscription, supported_content, entry):
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
            fromentry = datetime(pubdate[0],  # year
                                 pubdate[1],  # month
                                 pubdate[2],  # day
                                 pubdate[3],  # hour
                                 pubdate[4],  # minute
                                 pubdate[5],  # second
                                 tzinfo=UTC)

            if fromentry > today:
                pubdate = today.timetuple()
        else:
            pubdate = today.timetuple()

        return cls(parent_subscription, id_, supported_content,
                   title=entry.title,
                   description=entry.description,
                   pubdate=pubdate,
                   files=[(enc.href, enc.type, None)
                          for enc
                          in entry.get('enclosures', [])])

    @classmethod
    def from_dict(cls, parent_subscription, supported_content, data_dict):
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
        return cls(parent_subscription, id_, supported_content, **data_dict)

    def as_dict(self):
        '''Return this Episode's details as a *dict*
        with JSON serializable data.
        '''
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

    def _iter_attachments(self):
        '''Iterate over all attachments that we accept.'''
        files = self.files[:]
        for item in files:
            content_type = item[1]
            if self._should_download(content_type):
                yield item

    @property
    def has_attachments(self):
        return len([f for f in self._iter_attachments()]) > 0

    def download(self, force=False):
        '''Download all enclosures for this episode.
        Update the association (download url => local_file) in ``self.files``.

        :param bool force:
            *optional*, if *True*, downloads enclosures even if
            a local file already exists (overwriting the local file).
            Defaults to *False*.
        '''
        for index, item in enumerate(self._iter_attachments()):
            url, content_type, local_file = item
            have = self._is_downloaded(url)
            if not have or force:
                local_file = self._download_one(index, url, content_type,
                                                dst_file=local_file)
                self.files[index] = (url, content_type, local_file)
            else:
                LOG.debug('Skip %r.', url)

    def _is_downloaded(self, url):
        '''Tell if the enclosure for the given URL has been downloaded.
        Specifically, if the local file associated with the URL exists.'''
        for existing_url, unused, local_file in self.files:
            if url == existing_url:
                return local_file is not None and os.path.isfile(local_file)
        return False

    def _should_download(self, content_type):
        return content_type in self.supported_content

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

        LOG.info('Download from %r.', url)
        LOG.info('Local file is %r.', local_file)
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

        ext = self._file_extension_for_mime(content_type)
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
        known_exts = [x for x in self.supported_content.values()]
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
            unused, unused_also, local_file = self.files.pop()
            if local_file:  # filename may be empty or None
                delete_if_exists(local_file)

    def move_local_files(self):
        '''Re-apply the filename template for this Episode's downloaded
        files and rename files.

        Useful if the filename pattern changes.
        '''
        files = self.files[:]
        for index, details in enumerate(files):
            url, content_type, oldpath = details
            newpath = os.path.join(self.subscription.content_dir,
                                   self._generate_filename(content_type, index))
            if not oldpath:
                LOG.warning('Episode %r has no local file', self)
            elif newpath != oldpath:
                newpath = unique_filename(newpath)
                dirname = os.path.dirname(newpath)
                require_directory(dirname)
                LOG.debug('Move %r -> %r', oldpath, newpath)
                try:
                    shutil.move(oldpath, newpath)
                    self.files[index] = (url, content_type, newpath)
                except OSError as err:
                    if err.errno != os.errno.ENOENT:
                        raise
                    LOG.warning(('Failed to rename file %r.'
                        ' File does not exist.'), oldpath)

    def _file_extension_for_mime(self, content_type):
        '''Get the appropriate file extension for a given content type.

        :param str content_type:
            The content type, e.g. "audio/mpeg".
        :rtype str:
            The associated file extension *without* a dot ("."),
            e.g. "mp3".
        '''
        try:
            return self.supported_content[content_type.lower()]
        except (KeyError, AttributeError):
            supported = ', '.join(self.supported_content.keys())
            message = ('Unsupported content type {c!r}.'
                       ' Supported: {s!r}').format(c=content_type,
                                                   s=supported)
            raise ValueError(message)

    def __repr__(self):
        return '<Episode id={s.id!r}>'.format(s=self)


def _fetch_feed(url, etag=None, modified=None):
    '''Download an parse a RSS feed.'''
    # see:
    # https://github.com/kurtmckee/feedparser/issues/30
    #
    try:
        feed = feedparser.parse(url, etag=etag, modified=modified)
    except TypeError as err:
        try:
            feedparser.PREFERRED_XML_PARSERS.remove('drv_libxml2')
        except ValueError:
            # not in the list
            raise err
        else:
            feed = feedparser.parse(url, etag=etag, modified=modified)


    if feed.status == 410:  # HTTP Gone
        raise FeedGoneError(('Request for URL {!r} returned'
                             ' HTTP 410.').format(url))
    elif feed.status == 404:  # HTTP Not Found
        raise FeedNotFoundError(('Request for URL {!r} returned'
                                 ' HTTP 404.').format(url))
    # TODO AuthenticationFailure
    # TODO Connection error, Timeouts
    return feed


def id_for_entry(entry):
    '''Determine the ID for a feed entry.

    This is preferably the ID defined for the entry.
    If that is missing, use the publication date and title.
    '''
    entry_id = entry.get('id')
    if entry_id:
        return entry_id
    else:
        return '{}.{}'.format(''.join(str(x) for x in entry.published_parsed),
                              entry.get('title', ''))


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

    result = str(unpretty)

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
        result = result.replace(text, replacement)

    # delete non-ascii chars and whitespace
    import string
    allowed_chars = string.ascii_letters + string.digits + string.punctuation
    result = ''.join(c for c in result if c in allowed_chars)

    # replace multiple occurence of separators with one separator
    # "---" becomes "-"
    separators = ['-', '_', '.']
    for sep in separators:
        pattern = '[{}]+'.format(sep)
        result = re.sub(pattern, sep, result)

    return result


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
    with closing(requests.get(download_url, stream=True)) as r:
        r.raise_for_status()
        unused, tempdst = tempfile.mkstemp()
        with open(tempdst, 'wb') as f:
            chunk_size = 1024
            for chunk in r.iter_content(chunk_size):
                f.write(chunk)

    LOG.debug('Downloaded to tempdst: %r.', tempdst)
    try:
        shutil.move(tempdst, dst_path)
        # desired permissions are -rw-r--r
        perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(dst_path, perms)
    finally:
        delete_if_exists(tempdst)
