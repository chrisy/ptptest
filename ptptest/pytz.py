# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""Pytz dummy module"""

# This empty module with the name pytz.py fools
# bson.py into loading; we then provide the only
# pytz-reference used by bson - 'utc'

from datetime import datetime
from datetime import tzinfo


class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

utc = UTC()
