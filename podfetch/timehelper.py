#-*- coding: utf-8 -*-
'''
Helper for datetime related stuff.
'''
try:  # py 3.x
    from datetime import timezone
    UTC = timezone.utc
except ImportError:  # py 2.x
    from datetime import tzinfo
    from datetime import timedelta

    _ZERO = timedelta(0)

    class _UTC(tzinfo):

        def utcoffset(self, dt):
            return _ZERO

        def tzname(self, dt):
            return 'UTC'

        def dst(self, dt):
            return _ZERO

    UTC = _UTC()
