#-*- coding: utf-8 -*-
'''
Definition for the storage interface.

A Storage implementation is responsible for persisting data on
- Subscriptions
- Episode details

Downloaded media files are stored separately.

TODO: Cache:
- cache get
- cache put
- cache forget

'''
import logging

from podfetch.exceptions import StorageError


LOG = logging.getLogger(__name__)


class Storage:

    # Subscriptons ------------------------------------------------------------

    def save_subscription(self, subscription):
        '''Save a single subscription.'''
        raise StorageError('Not Implemented')

    def load_subscription(self, name):
        '''Load a single subscription by name.'''
        raise StorageError('Not Implemented')

    def delete_subscription(self, subscription_or_name):
        '''Delete a single subscription.'''
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
