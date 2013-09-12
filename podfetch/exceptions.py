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
