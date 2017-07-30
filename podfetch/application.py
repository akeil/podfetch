#-*- coding: utf-8 -*-
'''
Main application module.

Hooks
-----
The following events exist::

    SUBSCRIPTION_UPDATED = 'subscription_updated'
    UPDATES_COMPLETE = 'updates_complete'
    SUBSCRIPTION_ADDED = 'subscription_added'
    SUBSCRIPTION_REMOVED = 'subscription_removed'

Context:

:SUBSCRIPTION_UPDATED:
    subscription.name,
    subscription.content_dir

:SUBSCRIPTION_ADDED:
    subscription.name,
    subscription.content_dir

:SUBSCRIPTION_REMOVED:
    subscription.name,
    subscription.content_dir

'''
import logging
import os
import threading
from pkg_resources import iter_entry_points

try:
    from urllib.parse import urlparse  # python 3.x
except ImportError:
    from urlparse import urlparse  # python 2.x

try:
    import queue  # python 3.x
except ImportError:
    import Queue as queue  # python 2.x

import feedparser

from podfetch.fsstorage import FileSystemStorage
from podfetch.model import Subscription
from podfetch.predicate import Filter
from podfetch.predicate import WildcardFilter
from podfetch import exceptions as ex


LOG = logging.getLogger(__name__)


# events ----------------------------------------------------------------------
SUBSCRIPTION_UPDATED = 'subscription_updated'
UPDATES_COMPLETE = 'updates_complete'
SUBSCRIPTION_ADDED = 'subscription_added'
SUBSCRIPTION_REMOVED = 'subscription_removed'
EVENTS = (
    SUBSCRIPTION_UPDATED,
    UPDATES_COMPLETE,
    SUBSCRIPTION_ADDED,
    SUBSCRIPTION_REMOVED,
)
EP_EVENTS = 'podfetch.events'


# application -----------------------------------------------------------------


class Podfetch:
    '''The main application class.
    Used to manage and update subscriptions.

    :var str subscriptions_dir:
        Path to a directory in which Podfetch looks for configured
        subscriptions.
    :var str index_dir:
        Base directory in which the index files with the list of downloaded
        episodes for each subscription are stored.
    :var str content_dir:
        the destination directory into which downloaded files are stored.
    :var cache_dir:
        Location where helper files are stored.
    :var str filename_template:
        Template string used to generate filenames for downloaded episodes
        if no specific template is defined on the subscription level.
    :var int update_threads:
        The number of update threads to use.
    '''

    def __init__(self, config_dir, index_dir, content_dir, cache_dir,
        filename_template=None, update_threads=1, ignore=None,
        supported_content=None):
        self.config_dir = config_dir
        self.subscriptions_dir = os.path.join(config_dir, 'subscriptions')
        self._storage = FileSystemStorage(self.subscriptions_dir)
        self.index_dir = index_dir
        self.content_dir = content_dir
        self.cache_dir = cache_dir
        self.filename_template = filename_template
        self.update_threads = max(1, update_threads)
        self.ignore = ignore
        self.supported_content = supported_content or {}

        LOG.debug('config_dir: %r.', self.config_dir)
        LOG.debug('index_dir: %r', self.index_dir)
        LOG.debug('content_dir: %r.', self.content_dir)
        LOG.debug('cache_dir: %r.', self.cache_dir)
        LOG.debug('filename_template: %r.', self.filename_template)
        LOG.debug('update_threads: %s', self.update_threads)
        LOG.debug('ignore: %r', self.ignore)
        LOG.debug('supported_content: %s', ', '.join(self.supported_content.keys()))

    def subscription_for_name(self, name):
        '''Get the :class:`model.Subscription` with the given name.

        :param str name:
            The unique name of the subscription
        :rtype object:
            :class:`model.Subscription` instance if it exists.
        :raises:
            NoSubscriptionError if no subscription with that name
            exists
        '''
        filename = os.path.join(self.subscriptions_dir, name)
        sub = Subscription.from_file(
            filename, self.index_dir, self.content_dir, self.cache_dir,
            app_filename_template=self.filename_template,
            supported_content=self.supported_content,
        )
        return sub

    def iter_subscriptions(self, predicate=None):
        '''Iterate over all configured subscriptions.
        *yields* a :class:`Subscription` instance for each configuration file
        in the ``subscriptions_dir``.

        :param Filter predicate:
            *optional* a :class:`Filter` instance.
            If given, yields only subscriptions with match the filter.
        '''
        predicate = predicate or Filter()
        if self.ignore:
            predicate = predicate.and_not(WildcardFilter(*self.ignore))
        for basedir, dirnames, filenames in os.walk(self.subscriptions_dir):
            for name in filenames:
                if predicate(name):
                    try:
                        yield self.subscription_for_name(name)
                    except Exception as e:  # TODO exception type
                        LOG.error(e)

    def iter_episodes(self, sub_filter=None):
        '''Iterate over Episodes from all subscriptions.'''
        for subscription in self.iter_subscriptions(predicate=sub_filter):
            for episode in subscription.episodes:
                yield episode

    def update(self, predicate=None, force=False):
        '''Fetch new episodes for the given ``subscription_names``.

        Subscriptions which have the *enabled* property set to *False*
        are not updated.

        Subscriptions are updated in parallel if more than one subscription
        name is supplied and if the number of worker threads is 2 or higher.

        :param bool force:
            *optional*,
            force update, ignore HTTP etag and not modified in feed.
            Re-download all episodes.
            Also update *disabled* subscriptions.
            Default is *False*.
        :param Filter predicate:
            *optional* a :class:`Filter` instance.
            If given, yields only subscriptions with match the filter.
        '''
        predicate = predicate or Filter()
        tasks = queue.Queue()
        num_tasks = 0
        for subscription in self.iter_subscriptions(predicate=predicate):
            if subscription.enabled or force:
                tasks.put(subscription)
                num_tasks += 1

        def work():
            done = False
            while not done:
                try:
                    subscription = tasks.get(block=False)
                    update_one(subscription, force=force)
                except queue.Empty:
                    done = True

        def update_one(subscription, force=False):
            LOG.info('Update %r.', subscription.name)
            initial_episode_count = len(subscription.episodes)
            try:
                subscription.update(force=force)
                self._storage.save_subscription(subscription)
            except Exception as err:
                LOG.error('Failed to fetch feed %r. Error was: %s',
                    subscription.name, err)
                LOG.debug(err, exc_info=True)
            finally:
                tasks.task_done()

            if initial_episode_count < len(subscription.episodes):
                self.run_hooks(
                    SUBSCRIPTION_UPDATED,
                    subscription.name,
                    subscription.content_dir
                )

        num_workers = self.update_threads
        use_threading = num_tasks > 1 and num_workers > 1

        if use_threading:
            LOG.debug('Using %s update-threads.', num_workers)
            for index in range(1, num_workers+1):
                threading.Thread(
                    name='update-thread-{}'.format(index),
                    daemon=True,
                    target=work,
                ).run()
                LOG.debug('Started update-thread-%s.', index)
        else:
            work()

        tasks.join()
        self.run_hooks(UPDATES_COMPLETE)

    def add_subscription(self, url,
        name=None, content_dir=None, max_episodes=-1, filename_template=None):
        '''Add a new subscription.

        :param str url:
            The feed URL for the new subscription
        :param str name:
            *optional* name for the subscription.
            If name is *None*, the name will be derived from the url.
            If necessary, the ``name`` will be modified so that it is unique
            within the subscriptions dir.
        :param str content_dir:
            Download new episodes into this directory.
            If not given, a subdirectory in the application wide ``content_dir``
            is used. The subdirectory is then named after the subscription.
        :param int max_episodes:
            Keep at max *n* downloaded episodes for this subscription.
            Defaults to ``-1`` (unlimited).
        :param str filename_template:
            Template string for episode filenames.
            If omitted, application default is used.
        :rtype object:
            A :class:`Subscription` instance.
        '''
        if not name:
            name = name_from_url(url)
        uname = self._make_unique_name(name)
        sub = Subscription(uname, url,
            self.subscriptions_dir,
            self.index_dir,
            self.content_dir,
            self.cache_dir,
            content_dir=content_dir,
            max_episodes=max_episodes,
            filename_template=filename_template,
            app_filename_template=self.filename_template,
            supported_content=self.supported_content,
        )
        self._storage.save_subscription(sub)
        self.run_hooks(SUBSCRIPTION_ADDED, sub.name, sub.content_dir)
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
        sub = self.subscription_for_name(name)
        filename = os.path.join(self.subscriptions_dir, name)
        sub.delete(keep_episodes=not delete_content)
        LOG.info('Delete subscription at %r.', filename)
        try:
            os.unlink(filename)
        except os.error as e:
            if e.errno != os.errno.ENOENT:
                raise

        self.run_hooks(SUBSCRIPTION_REMOVED, name, sub.content_dir)

    def _make_unique_name(self, name):
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
            LOG.info('Changed name from %r to %r.', original_name, name)

        return name

    def purge_all(self, simulate=False):
        deleted_files = []
        for subscription in self.iter_subscriptions():
            deleted_files += subscription.purge(simulate=simulate)
            self._storage.save_subscription(subscription)
        return deleted_files

    def purge_one(self, name, simulate=False):
        subscription = self.subscription_for_name(name)
        deleted_files = subscription.purge(simulate=simulate)
        self._storage.save_subscription(subscription)
        return deleted_files

    def edit(self, subscription_name, name=None, url=None, title=None,
        enabled=None, max_episodes=None, filename_template=None,
        content_dir=None, move_files=False):
        '''Edit a single subscription.

        Changes the given properties of the subscription and saves changes.

        If the ``name`` of a subscription is changed, the subscription's
        ini-file is saved under the new name and the old file is removed.

        :param str subscription_name:
            Current name of the subscription to edit.
        :param str name:
            *optional*, set a new the name.
        :param str url:
            *optional*, set a new source url.
        :param str title:
            *optional, set a new title.
        :param bool enabled:
            *optional*, enable or disable the feed.
        :param int max_episodes:
            Set the maximum number of episodes.
            Use ``-1`` for unlimited.
        :param str filename_template:
            *optional*, set a new template string for episode filenames.
        :param str content_dir:
            Base directory for downloaded episodes.
        :param bool move_files:
            *optional*, rename files for already downloaded episodes
            if for example the ``filename_template`` is changed.
        '''
        LOG.debug('Edit subscription %r.', subscription_name)
        sub = self.subscription_for_name(subscription_name)
        could_rename_files = False

        if url is not None:
            sub.feed_url = url

        if title is not None:
            sub.title = title
            could_rename_files = True

        if enabled is not None:
            sub.enabled = bool(enabled)

        if filename_template is not None:
            sub.filename_template = filename_template
            could_rename_files = True

        if content_dir is not None:
            sub.content_dir = content_dir
            could_rename_files = True

        if max_episodes is not None:
            sub.max_episodes = int(max_episodes)

        if could_rename_files and move_files:
            sub.rename_files()

        self._storage.save_subscription(sub)

        # special case - name is also the filename
        old_filename = os.path.join(self.subscriptions_dir, sub.name)
        if name is not None:
            sub.rename(name, move_files=move_files)
            self._storage.save_subscription(sub)

        new_filename = os.path.join(self.subscriptions_dir, sub.name)
        if old_filename != new_filename:
            # we did save successfully, so the new file exists
            LOG.info('Delete old subscription %r.', old_filename)
            os.unlink(old_filename)

    def run_hooks(self, event, *args):
        '''Run hooks for the given ``event``.'''
        LOG.debug('Run hooks for event %r', event)
        for ep in iter_entry_points(EP_EVENTS, name=event):
            try:
                hook = ep.load()
            except ImportError as e:
                LOG.error('Failed to load entry point %r', ep)
                continue

            LOG.debug('Run hook {h!r}'.format(h=hook))

            try:
                hook(self, *args)
            except Exception as e:
                LOG.error('Failed to run hook %r', hook)
                LOG.debug(e, exc_info=True)


# Helpers --------------------------------------------------------------------


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


#TODO move to "helpers" module
def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as e:
        if e.errno != os.errno.EEXIST:
            raise
