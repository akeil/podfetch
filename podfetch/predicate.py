#-*- coding: utf-8 -*-
'''
Filters for Subscriptions and Episodes
'''
import fnmatch
import logging
from datetime import date


LOG = logging.getLogger(__name__)


class Filter:
    '''Filter baseclass; can be used directly as an accept-all filter.'''

    def __call__(self, candidate):
        return True

    def is_not(self):
        '''Invert this filter.'''
        return _Not(self)

    def or_is(self, other):
        '''Chain with another filter using OR'''
        return _Chain('OR', self, other)

    def or_not(self, other):
        '''Chain with an inverted other filter using OR.'''
        return self.or_is(other.is_not())

    def and_is(self, other):
        '''Chain with another filter using AND.'''
        return _Chain('AND', self, other)

    def and_not(self, other):
        '''Chain with an inverted other filter using AND.'''
        return self.and_is(other.is_not())

    def __repr__(self):
        return '<Filter *>'


class _Not(Filter):
    '''Invert filter'''

    def __init__(self, filter):
        self.filter = filter

    def __call__(self, candidate):
        return not(self.filter(candidate))

    def __repr__(self):
        return '<Not {s.filter!r}>'.format(s=self)


class _Chain(Filter):
    '''Combine multiple filters into one
    using either ``OR`` or ``AND``.'''

    def __init__(self, mode, *filters):
        self.mode = mode
        self.filters = filters[:]

    def __call__(self, candidate):
        result = self.filters[0](candidate)
        for filter in self.filters[1:]:
            matches = filter(candidate)
            if self.mode == 'AND':
                result = result and matches
                if not result:
                    return False
            else:  # self.mode == 'OR'
                result = result or matches
                if result:
                    return True

        return result

    def __repr__(self):
        return '<Chain {s.mode!r} {s.filters!r}>'.format(s=self)


class NameFilter(Filter):

    def __init__(self, name):
        self.name = name

    def __call__(self, candidate):
        if hasattr(candidate, 'name'):
            # for Subscriptions and Episodes
            return getattr(candidate, 'name') == self.name
        else:
            # for strings
            return candidate == self.name


class WildcardFilter(Filter):
    '''Filter with shell wildcards using ``fnmatch``.'''

    def __init__(self, *patterns):
        self.patterns = patterns[:] if patterns else ['*']

    def __call__(self, candidate):
        name = None
        if hasattr(candidate, 'name'):
            # for Subscriptions and Episodes
            name = getattr(candidate, 'name')
        else:
            # for strings
            name = candidate

        for pattern in self.patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def __repr__(self):
        return '<Wildcard {s.patterns!r}>'.format(s=self)


class EnabledFilter(Filter):
    '''Filter for Subscriptions to clear out disabled entries.'''

    def __call__(self, candidate):
        if hasattr(candidate, 'enabled'):
            # Subscriptions
            return candidate.enabled == True
        else:
            # Strings (can't check)
            return True

    def __repr__(self):
        return '<EnabledFilter>'


class PubdateAfter(Filter):

    def __init__(self, since):
        self.since = since

    def __call__(self, candidate):
        if candidate.pubdate:
            return date(*candidate.pubdate[:3]) >= self.since
        else:
            return False

    def __repr__(self):
        return '<PubdateAfter {s.since!r}>'.format(s=self)


class PubdateBefore(Filter):

    def __init__(self, until):
        self.until = until

    def __call__(self, candidate):
        if candidate.pubdate:
            return date(*candidate.pubdate[:3]) <= self.until
        else:
            return False

    def __repr__(self):
        return '<PubdateBefore {s.until!r}>'.format(s=self)
