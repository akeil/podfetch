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
import os
import shutil
import tempfile
import logging
import subprocess
import shlex

try:
    from shlex import quote as shlex_quote  # python 3.x
except ImportError:
    from pipes import quote as shlex_quote  # python 2.x

try:
    from urllib.parse import urlparse  # python 3.x
except ImportError:
    from urlparse import urlparse  # python 2.x

import feedparser

from podfetch.model import Subscription
from podfetch import exceptions as ex


log = logging.getLogger(__name__)


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

# exit codes ------------------------------------------------------------------
ALL_FAILED = 2
SOME_FAILED = 3
OK = 0


# application -----------------------------------------------------------------


class Podfetch(object):
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
    :var HookManager hooks:
        Delegate to run *hooks*.
    :var str filename_template:
        Template string used to generate filenames for downloaded episodes
        if no specific template is defined on the subscription level.

    '''

    def __init__(self, config_dir, index_dir, content_dir, cache_dir,
        filename_template=None):
        self.subscriptions_dir = os.path.join(config_dir, 'subscriptions')
        self.index_dir = index_dir
        self.content_dir = content_dir
        self.cache_dir = cache_dir
        self.hooks = HookManager(config_dir)
        self.filename_template = filename_template

    def _load_subscription(self, name):
        '''Load a :class:`Subscription` instance from its configuration file.

        :param str name:
            The identifier of the configuration to load.
        :rtype Subscription:
            The Subscription instance.
        :raises:
            NoSubscriptionError if no config-file for a subscription with that
            name exists.
        '''
        filename = os.path.join(self.subscriptions_dir, name)
        sub = Subscription.from_file(
            filename, self.index_dir, self.content_dir, self.cache_dir)
        sub.app_filename_template = self.filename_template
        return sub

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
        return self._load_subscription(name)

    def update_all(self, force=False):
        '''Update all subscriptions.

        Retrieves the feeds for each subscription
        and downloads any new episodes.

        :param bool force:
            *optional*,
            force update, ignore HTTP etag and not modified in feed.
            Re-download all episodes.
            Default is *True*.
        :rtype int:
            An *Error Code* describing the result.
        '''
        error_count = 0
        total_count = 0
        for subscription in self.iter_subscriptions():
            total_count += 1
            try:
                rv = self._update_subscription(subscription, force=force)
            except Exception as e:
                log.error(('Failed to fetch feed {n!r}.'
                    ' Error was: {e}').format(n=subscription.name, e=e))
                error_count += 1

        self.hooks.run_hooks(UPDATES_COMPLETE)
        log.info('Processed {} subscriptions, {} errors.'.format(total_count, error_count))
        if error_count:
            if error_count == total_count:
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
            for name in filenames:
                try:
                    yield self._load_subscription(name)
                except Exception as e:  # TODO exception type
                    log.error(e)

    def update_one(self, name, force=False):
        '''Update the subscription with the given ``name``.

        :param str name:
            The name of the config file for the subscription.
        :param bool force:
            *optional*,
            force update, ignore HTTP etag and not modified in feed.
            Re-download all episodes.
            Default is *False*.
        '''
        subscription = self._load_subscription(name)
        self._update_subscription(subscription, force=force)

    def _update_subscription(self, subscription, force=False):
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
        subscription.update(force=force)

        self.hooks.run_hooks(SUBSCRIPTION_UPDATED, subscription.name,
            subscription.content_dir)

    def add_subscription(self, url, name=None, max_episodes=-1):
        '''Add a new subscription.

        :param str url:
            The feed URL for the new subscription
        :param str name:
            *optional* name for the subscription.
            If name is *None*, the name will be derived from the url.
            If necessary, the ``name`` will be modified so that it is unique
            within the subscriptions dir.
        :param int max_episodes:
            Keep at max *n* downloaded episodes for this subscription.
            Defaults to ``-1`` (unlimited).
        :rtype object:
            A :class:`Subscription` instance.
        '''
        if not name:
            name = name_from_url(url)
        uname = self._make_unique_name(name)
        sub = Subscription(uname, url,
            self.subscriptions_dir, self.index_dir,
            self.content_dir, self.cache_dir
        )
        sub.save()

        self.hooks.run_hooks(SUBSCRIPTION_ADDED, sub.name, sub.content_dir)

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
        content_dir = os.path.join(self.content_dir, name)
        log.info('Delete subscription at {!r}.'.format(filename))
        try:
            os.unlink(filename)
        except os.error as e:
            if e.errno != os.errno.ENOENT:
                raise

        if delete_content:
            # TODO: this should be implemented by the Subscription class
            log.info('Delete contents at {!r}.'.format(content_dir))
            shutil.rmtree(content_dir, ignore_errors=True)

        self.hooks.run_hooks(SUBSCRIPTION_REMOVED, name, content_dir)

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
            log.info(
                'Changed name from {!r} to {!r}.'.format(original_name, name))

        return name

    def purge_all(self):
        for subscription in self.iter_subscriptions():
            self._purge_subscription(subscription)

    def purge_one(self, name):
        subscription = self._load_subscription(name)
        self._purge_subscription(subscription)

    def _purge_subscription(self, subscription):
        if subscription.max_episodes < 0:
            log.info(('Number of episodes not limited'
                ' for subscription {!r}.').format(subscription.name))
        else:
            content_dir = os.path.join(self.content_dir, subscription.name)
            filenames = os.listdir(content_dir)
            delete_count = len(filenames) - subscription.max_episodes
            to_be_deleted = sorted(filenames, reverse=True)[delete_count:]
            for filename in to_be_deleted:
                path = os.path.join(content_dir, filename)
                log.info('Delete episode {!r}'.format(path))
                os.unlink(path)


class HookManager(object):
    '''Helper for :class:`Podfetch` to discover and run *hooks*
    on specific events.
    '''

    def __init__(self, config_dir):
        self.hook_dirs = {
            event_name: os.path.join(config_dir, event_name)
            for event_name in EVENTS
        }

    def run_hooks(self, event, *args):
        log.debug('Run hooks for event {!r}.'.format(event))
        for hook_executable in self.discover_hooks(event):
            self._run_one_hook(event, hook_executable, *args)

    def _run_one_hook(self, event, executable, *args):
        try:
            devnull = subprocess.DEVNULL
        except AttributeError:  # python 2.x
            devnull = open(os.devnull, 'w')

        call_args = [shlex_quote(str(arg)) for arg in args]
        call_args.insert(0, executable)
        argstr = ' '.join(call_args)

        exit_code = subprocess.call(argstr,
            shell=True,
            stdout=devnull,
            stderr=devnull,
        )

        name = os.path.basename(executable)
        if exit_code == 0:
            log.debug(('Successfully ran hook {!r}'
                ' on event {!r}.').format(name, event))
        else:
            log.error(('Hook {!r} exited with non-zero exit status ({})'
                ' on event {!r}.').format(name, exit_code, event))

    def discover_hooks(self, event):
        hooks_dir = self.hook_dirs[event]
        try:
            hooks = os.listdir(hooks_dir)
        except OSError as e:
            if e.errno == os.errno.ENOENT:
                hooks = []
            else:
                raise

        def is_executable(path):
            # must check if it is a _file_
            # directories can also have an "executable" bit set
            return os.path.isfile(path) and os.access(path, os.X_OK)

        for name in hooks:
            path = os.path.join(hooks_dir, name)
            if is_executable(path):
                log.debug('Found hook {!r}.'.format(name))
                yield path
            else:
                log.warning((
                    'File {!r} in hooks dir {!r} is not executable'
                    ' and will not be run.').format(name, hooks_dir))


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


def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as e:
        if e.errno != os.errno.EEXIST:
            raise
