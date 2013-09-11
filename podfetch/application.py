#-*- coding: utf-8 -*-
'''
Main application module.
'''
import os
import logging

import feedparser

from podfetch.model import Subscription

log = logging.getLogger(__name__)

ALL_FAILED = 2
SOME_FAILED = 3
OK = 0


def fetch_all(subscriptions_dir, content_dir):
    '''Fetch all feeds.

    :rtype int:
        An *Error Code* describing the result.
    '''
    error_count = 0
    for subscription in iter_subscriptions(subscriptions_dir):
        try:
            rv = update_subscription(content_dir, subscription)
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


def iter_subscriptions(subscriptions_dir):
    for basedir, dirnames, filenames in os.walk(subscriptions_dir):
        for filename in filenames:
            path = os.path.join(basedir, filename)
            try:
                log.info('Read subscription from {!r}.'.format(path))
                yield Subscription.from_file(path)
            except Exception as e:
                log.error(e)


def fetch_one(subscriptions_dir, content_dir, name):
    '''Update the subscription with the given ``name``.'''
    filename = os.path.join(subscriptions_dir, name)
    subscription = Subscription.from_file(filename)
    update_subscription(content_dir, subscription)


def update_subscription(content_dir, subscription):
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
            process_entry(content_dir, subscription.name, entry)
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


def purge():
    '''Remove old files that were previously downloaded.'''
    for subscription in iter_subscriptions(SUBSCRIPTIONS_DIR):
        purge_subscription(subscription)


def purge_subscription(subscription):
    content_dir = os.path.join(CONTENT_DIR, subscription.name)
    # iter files
    # check age
    # check max files
    # remove old
    # hook


def process_entry(content_basedir, feed_name, entry):
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
            dirname = os.path.join(content_basedir, feed_name)
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


def file_extension_for_mime(mime):
    try:
        return {
            'audio/mpeg': 'mp3',
            'audio/ogg': 'ogg',
            'audio/flac': 'flac',
        }[mime.lower()]
    except (KeyError, AttributeError):
        raise ValueError('Unupported content type {!r}.'.format(mime))


def safe_filename(unsafe):
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
    # TODO if the guid contains a file extension, remove it.
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
    # TODO is this "The Right Way"?
    import urllib
    urllib.request.urlretrieve(download_url, dst_path)


def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as e:
        if e.errno != os.errno.EEXIST:
            raise
