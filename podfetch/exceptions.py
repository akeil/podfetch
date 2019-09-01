# -*- coding: utf-8 -*-
'''Exceptions used by podfetch.

Exception hierarchy::

    PodfetchError

        NoSubscriptionError

'''

class PodfetchError(Exception):
    pass


class NoSubscriptionError(PodfetchError):
    pass


class NoEpisodeError(PodfetchError):
    pass


class FeedGoneError(PodfetchError):
    '''Raised when we try to fetch an RSS feed that is marked as
    "Gone" (HTTP 410).'''
    pass


class FeedNotFoundError(PodfetchError):
    '''Raised when accessing a feed URL returns a HTTP 404.'''
    pass


class UserError(Exception):
    '''Raised for bad input, missing parameters, ...'''
    pass


class StorageError(PodfetchError):
    pass
