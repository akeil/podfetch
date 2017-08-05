#-*- coding: utf-8 -*-
'''
File system storage.


'''
import json
import logging
import os

try:
    from configparser import ConfigParser  # python 3.x
    from configparser import Error as _ConfigParserError
except ImportError:
    from ConfigParser import RawConfigParser  # python 2.x
    from ConfigParser import Error as _ConfigParserError

from podfetch.storage import Storage
from podfetch.exceptions import StorageError
from podfetch.exceptions import NoSubscriptionError
from podfetch.model import Episode
from podfetch.model import Subscription
from podfetch.predicate import Filter
from podfetch.predicate import WildcardFilter
from podfetch.utils import require_directory
from podfetch.utils import delete_if_exists


LOG = logging.getLogger(__name__)

# section in subscription ini's
SECTION = 'subscription'


class FileSystemStorage(Storage):

    def __init__(self,
        config_dir,
        index_dir,
        default_content_dir,
        cache_dir,
        ignore):

        self.config_dir = config_dir
        self.index_dir = index_dir
        self.default_content_dir = default_content_dir
        self.cache_dir = cache_dir
        self.ignore = ignore

    # Subscriptons ------------------------------------------------------------

    def _subscription_path(self, name):
        return os.path.join(self.config_dir, name)

    def _index_path(self, name):
        return os.path.join(self.index_dir, '{}.json'.format(name))

    def save_subscription(self, subscription):
        '''Save a single subscription.'''
        s = subscription
        cfg = _mk_config_parser()
        cfg.add_section(SECTION)

        def _set(key, value):
            if value:  # will lose max_episodes = 0
                cfg.set(SECTION, key, value)

        _set('url', s.feed_url)
        _set('max_episodes', str(s.max_episodes))
        _set('enabled', 'yes' if s.enabled else 'no')
        _set('title', s.title)
        _set('filename_template', s.filename_template)
        _set('content_dir', s._content_dir)

        path = self._subscription_path(s.name)
        LOG.debug('Save Subscription %r to %r.', s.name, path)
        require_directory(os.path.dirname(path))
        with open(path, 'w') as fp:
            cfg.write(fp)

    def iter_subscriptions(self, predicate=None):
        '''Iterate over all subscriptions matching the given ``predicate``.'''
        predicate = predicate or Filter()

        if self.ignore:
            predicate = predicate.and_not(WildcardFilter(*self.ignore))

        for basedir, dirnames, filenames in os.walk(self.config_dir):
            for name in filenames:
                if predicate(name):
                    try:
                        yield self.load_subscription(name)
                    except Exception as err:  # TODO exception type
                        LOG.error(err)
                        LOG.debug(err, exc_info=True)

    def load_subscription(self, name, **kwargs):
        '''Load a single subscription by name.'''
        path = self._subscription_path(name)

        cfg = _mk_config_parser()
        # possible errors:
        # file does not exist
        # file is no in ini format
        # missing sections and options
        try:
            read_from = cfg.read(path)
        except _ConfigParserError:
            raise NoSubscriptionError(('Failed to read subscription from'
                                       ' {!r}.').format(path))
        if not read_from:
            raise NoSubscriptionError(('No config file exists at'
                                       ' {!r}.').format(path))

        LOG.debug('Read subscription from %r.', path)

        def get(key, default=None, fmt=None):
            result = default
            try:
                if fmt == 'int':
                    result = cfg.getint(SECTION, key)
                elif fmt == 'bool':
                    result = cfg.getboolean(SECTION, key)
                else:
                    result = cfg.get(SECTION, key)
            except _ConfigParserError:
                LOG.debug('Could not read %r from ini.', key)
            return result

        feed_url = get('url')
        if not feed_url:
            raise NoSubscriptionError(('Failed to read URL from'
                                       ' {p!r}.').format(p=path))

        sub = Subscription(
            name,
            feed_url,
            self.index_dir,
            self.default_content_dir,
            title=get('title'),
            max_episodes=get('max_episodes', default=-1, fmt='int'),
            enabled=get('enabled', default=True, fmt='bool'),
            content_dir=get('content_dir'),
            filename_template=get('filename_template'),
            **kwargs
        )

        sub.episodes = self._load_episodes(sub) or []

        return sub

    def delete_subscription(self, name):
        '''Delete a single subscription.'''
        path = self._subscription_path(name)
        LOG.info('Delete subscription at %r.', path)
        try:
            os.unlink(path)
        except os.error as e:
            if e.errno != os.errno.ENOENT:
                raise

        delete_if_exists(self._index_path(name))

        self.cache_forget(name)

    def rename_subscription(self, oldname, newname):
        '''Change the name for an existing subscription.'''
        raise StorageError('Not Implemented')

    # Episodes ----------------------------------------------------------------

    def _load_episodes(self, sub):
        '''Load all episodes for the given subscription.'''
        name = sub.name
        data = self._load_episode_index(name)

        return [
            Episode.from_dict(sub, sub.supported_content, d)
            for d in data
        ]

    def _load_episode_index(self, name):
        data = []
        try:
            with open(self._index_path(name)) as src:
                data = json.load(src)
        except IOError as err:
            if err.errno == os.errno.ENOENT:
                pass
            else:
                raise

        return data

    def save_episodes(self, name, episodes):
        '''Save all episodes for a subscription.'''
        data = [e.as_dict() for e in episodes]
        self._save_index_file(name, data)

    def _save_index_file(self, name, data):
        path = self._index_path(name)
        if data:
            require_directory(os.path.dirname(path))
            with open(path, 'w') as dst:
                json.dump(data, dst)
        else:
            delete_if_exists(path)

    def save_episode(self, episode):
        '''Save a single episode.'''
        name = episode.subscription.name
        episode_id = episode.id
        episode_list = self._load_episode_index(name)

        episode_data = episode.as_dict()

        update_index = None
        for index, item in enumerate(episode_list):
            existing_id = item['id']
            if existing_id == episode_id:
                update_index = index
                break

        if update_index is not None:
            episode_list[update_index] = episode_data
        else:
            episode_list.append(episode_data)

        self._save_index_file(name, episode_list)

    def delete_episode(self, episode):
        raise StorageError('Not Implemented')

    def find_episodes(self, predicate):
        raise StorageError('Not Implemented')

    # Cache -------------------------------------------------------------------

    def cache_get(self, namespace, key):
        '''Get a value from the cache.'''
        result = None
        try:
            with open(self._cache_path(namespace, key)) as cachefile:
                result = cachefile.read()
        except IOError as err:
            if err.errno != os.errno.ENOENT:
                raise

        return result or None  # convert '' to None

    def cache_put(self, namespace, key, value):
        path = self._cache_path(namespace, key)
        forget = not bool(value)
        if not forget:
            try:
                require_directory(os.path.dirname(path))
                with open(path, 'w') as cachefile:
                    cachefile.write(value)
            except Exception as err:
                LOG.error('Error writing cache file: %r', err)
                forget = True

        # value was empty or writing failed
        if forget:
            self._cache_forget(namespace, key)

    def cache_forget(self, namespace, keys=None):
        '''Remove entries for the given cache keys.'''

        #TODO: if keys is empty, remove all
        for key in keys:
            try:
                delete_if_exists(self._cache_path(namespace, key))
            except Exception:
                LOG.error('Failed to delete cache %r of %r.', key, self.name)

    def _cache_path(self, namespace, key):
        return os.path.join(self.cache_dir, '{}.{}'.format(namespace, key))


def _mk_config_parser():
    '''Create a config parser instance depending on python version.
    important point here is not to have interpolation
    because it conflicts with url escapes (e.g. "%20").
    '''
    try:
        return RawConfigParser()  # py 2.x
    except NameError:
        return ConfigParser(interpolation=None)  # py 3.x
