#-*- coding: utf-8 -*-
'''
Main application module.
'''
import os
import shutil
import tempfile
import logging

try:
    from urllib.parse import urlparse  # python 3.x
except ImportError:
    from urlparse import urlparse  # python 2.x

try:
    from urllib.request import urlretrieve  # python 3.x
except ImportError:
    from urllib import urlretrieve  # python 2.x

import feedparser

from podfetch.model import Subscription


log = logging.getLogger(__name__)

ALL_FAILED = 2
SOME_FAILED = 3
OK = 0


class Podfetch(object):
    '''The main application class.
    Used to manage and update subscriptions.'''

    def __init__(self, subscriptions_dir, content_dir):
        self.subscriptions_dir = subscriptions_dir
        self.content_dir = content_dir

    def fetch_all(self):
        '''Update all subscriptions.

        Retrieves the feeds for each subscription
        and downloads any new episodes.

        :rtype int:
            An *Error Code* describing the result.
        '''
        error_count = 0
        for subscription in self.iter_subscriptions():
            try:
                rv = self._update_subscription(subscription)
            except Exception as e:
                log.error(('Failed to fetch feed {n!r}.'
                    ' Error was: {e}').format(n=subscription.name, e=e))
                error_count += 1

        # run hook for downloads complete
        # if we did download anything

        if error_count:
            if error_count == len(feed_urls):
                return ALL_FAILED
            else:
                return SOME_FAILED
        else:
            return OK

    def iter_subscriptions(self):
        '''Iterate over all configured subscriptions.
        *yields* a :class:`Subscription` instance for each configuration file
        in the ``subscriptions_dir``.
        '''
        for basedir, dirnames, filenames in os.walk(self.subscriptions_dir):
            for filename in filenames:
                path = os.path.join(basedir, filename)
                try:
                    yield Subscription.from_file(path)
                except Exception as e:
                    log.error(e)

    def fetch_one(self, name):
        '''Update the subscription with the given ``name``.

        :param str name:
            The name of the config file for the subscription.
        '''
        filename = os.path.join(self.subscriptions_dir, name)
        subscription = Subscription.from_file(filename)
        self._update_subscription(subscription)

    def _update_subscription(self, subscription):
        '''Fetch the given feed, download any new episodes.

        :param object subscription:
            The :class:`Subscription` instance to update.
        :rtype int:
            An *Error Code* describing the result.
            0: all is well or no new episodes
            1: failed to fetch one or more new episodes
            2: failed to fetch all episodes.
        :raises:
            Some Exception if we failed to fetch the feed.
            Failed to look up the url
            connection failure
            bad url
            authentication failure
        '''
        log.info('Update subscription {!r}.'.format(subscription.name))
        feed = feedparser.parse(subscription.feed_url)
        error_count = 0
        for entry in feed.entries:
            try:
                self._process_entry(subscription.name, entry)
            except Exception as e:
                log.error(('Failed to fetch entry for feed {n!r}.'
                    ' Error was: {e}').format(n=subscription.name, e=e))
                error_count += 1

        # run hooks for feed downloaded
        # the list of downloaded files in the hook
        # skip if nothing was fetched.

        if error_count:
            if error_count == num_items:
                return ALL_ITEMS_FAILED
            else:
                return SOME_ITEMS_FAILED
        else:
            return OK

    def _process_entry(self, feed_name, entry):
        '''Process a single feed entry.
        Fetch the content for each enclosure (RSS feeds have max one,
        Atom feeds can have multiple enclosures per item).
        Determines the destination path for the enclosures,
        checks if we have already downloaded them
        and if not, downloads.
        '''
        enclosures = entry.get('enclosures', [])
        for index, enclosure in enumerate(enclosures):
            try:
                # TODO filter enclosures that are not audio files
                filename = generate_filename_for_enclosure(entry, index, enclosure)
                dirname = os.path.join(self.content_dir, feed_name)
                require_directory(dirname)
                dst_path = os.path.join(dirname, filename)
                if os.path.exists(dst_path):
                    log.info('Enclosure {}-{}-{} already downloaded.'.format(
                        feed_name, entry.guid, index))
                    continue
                else:
                    download(enclosure.href, dst_path)
                    # run hook for item downloaded
            except Exception as e: # TODO error handling
                log.error(e)

    def add_subscription(self, url, name=None):
        '''Add a new subscription.

        :param str url:
            The feed URL for the new subscription
        :param str name:
            *optional* name for the subscription.
            If name is *None*, the name will be derived from the url.
            If necessary, the ``name`` will be modified so that it is unique
            within the subscriptions dir.
        :rtype object:
            A :class:`Subscription` instance.
        '''
        if not name:
            name = name_from_url(url)
        uname = self.make_unique_name(name)
        sub = Subscription(uname, url)
        sub.save(self.subscriptions_dir)
        return sub

    def remove_subscription(self, name, delete_content=True):
        '''Delete the subscription with the given name.

        This will remove the configuration for this subscription
        and optionally clean up all downloaded content.

        :param str name:
            The name of the subscription to be removed.
        :param bool delete_content:
            Whether to delete downloaded audio file from that subscription.
            Defaults to *True*.
        '''
        filename = os.path.join(self.subscriptions_dir, name)
        log.info('Delete subscription at {!r}.'.format(filename))
        try:
            os.unlink(filename)
        except os.error as e:
            if e.errno != os.errno.ENOENT:
                raise

        if delete_content:
            content_dir = os.path.join(self.content_dir, name)
            log.info('Delete contents at {!r}.'.format(content_dir))
            shutil.rmtree(content_dir, ignore_errors=True)


    def make_unique_name(self, name):
        '''Modify the given ``name`` so that we get  a name that does
        not already exist as a config file in the ``subscriptions_dir``.

        :param str name:
            The name to start with.
        :rtype str:
            The original ``name`` if that was already unique
            or a modified name that is unique.
        '''
        existing_names = [s.name for s in self.iter_subscriptions()]
        original_name = name
        counter = 1
        while name in existing_names:
            name = '{}-{}'.format(original_name, counter)
            counter += 1

        if name != original_name:
            log.info(
                'Changed name from {!r} to {!r}.'.format(original_name, name))

        return name


def name_from_url(url):
    '''Derive a subscription name from a URL.

    :param str url:
        The URL to use.
    :rtype str:
        The subscription name derived from the URL.
    '''
    components = urlparse(url)
    name = components.hostname
    if name.startswith('www.'):
        name = name[4:]
    return name


def file_extension_for_mime(mime):
    '''Get the appropriate file extension for a given mime-type.

    :param str mim:
        The content type, e.g. "audio/mpeg".
    :rtype str:
        The associated file extension *without* a dot ("."),
        e.g. "mp3".
    '''
    try:
        return {
            'audio/mpeg': 'mp3',
            'audio/ogg': 'ogg',
            'audio/flac': 'flac',
        }[mime.lower()]
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

    basename, ext = os.path.splitext(entry.guid)
    known_extensions = ('.mp3', '.ogg', '.flac')
    if ext in known_extensions:
        name = basename
    else:
        name = entry.guid

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
    finally:
        try:
            os.unlink(tempdst)
        except os.error as e:
            if e.errno != os.errno.EEXIST:
                raise


def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as e:
        if e.errno != os.errno.EEXIST:
            raise
