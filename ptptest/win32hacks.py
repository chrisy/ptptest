# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
"""PTP Server"""

import sys

def noop1(dummy1):
	pass

def install_hacks():
    import signal
    signal.SIGALRM = signal.SIGFPE
    signal.alarm = noop1

    import urwid.display_common
    urwid.display_common.termios = sys.modules[__name__]
    urwid.display_common.termios.tcgetattr = noop1
