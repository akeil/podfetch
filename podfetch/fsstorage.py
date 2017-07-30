#-*- coding: utf-8 -*-
'''
File system storage.


'''
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
from podfetch.model import Subscription


LOG = logging.getLogger(__name__)

# section in subscription ini's
SECTION = 'subscription'


class FileSystemStorage(Storage):

    def __init__(self, config_dir):
        self.config_dir = config_dir

    # Subscriptons ------------------------------------------------------------

    def _subscription_path(self, name):
        return os.path.join(self.config_dir, name)

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

        return Subscription(
            name, feed_url,
            self.config_dir,
            index_dir,
            app_content_dir,
            cache_dir,
            title=get('title'),
            max_episodes=get('max_episodes', default=-1, fmt='int'),
            enabled=get('enabled', default=True, fmt='bool'),
            content_dir=get('content_dir'),
            filename_template=get('filename_template'),
            **kwargs
        )

    def delete_subscription(self, subscription_or_name):
        '''Delete a single subscription.'''
        name = None
        if isinstance(subscription_or_name, Subscription):
            name = subscription_or_name.name
        else:
            name = subscription_or_name

        #TODO.
        # - clean up index file
        # - clean up cache
        # - delete downloaded episode files
        # - delete the content dir
        # -

        self._cache_forget()
        delete_if_exists(self.index_file)
        if not keep_episodes:
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
        raise StorageError('Not Implemented')

    def iter_subscriptions(self, predicate):
        '''Iterate over all subscriptions matching
        the given ``predicate``.'''
        raise StorageError('Not Implemented')

    def rename_subscription(self, oldname, newname):
        '''Change the name for an existing subscription.'''
        raise StorageError('Not Implemented')

    # Episodes ----------------------------------------------------------------

    def load_episodes(self, subscription_name):
        raise StorageError('Not Implemented')

    def save_episodes(self, episodes):
        raise StorageError('Not Implemented')

    def save_episode(self, episode):
        raise StorageError('Not Implemented')

    def delete_episode(self, episode):
        raise StorageError('Not Implemented')

    def find_episodes(self, predicate):
        raise StorageError('Not Implemented')


def _mk_config_parser():
    '''Create a config parser instance depending on python version.
    important point here is not to have interpolation
    because it conflicts with url escapes (e.g. "%20").
    '''
    try:
        return RawConfigParser()  # py 2.x
    except NameError:
        return ConfigParser(interpolation=None)  # py 3.x

#TODO move to "helpers" module
def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except os.error as err:
        if err.errno != os.errno.EEXIST:
            raise
