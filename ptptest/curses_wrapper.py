# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""
Urwid extensions: eventlet-happy Curses implementation
"""

import eventlet
from urwid import curses_display
from eventlet.green import time


class CursesScreen(curses_display.Screen):

    def __init__(self):
        super(CursesScreen, self).__init__()

    def real_signal_init(self):
        pass

    def real_signal_restore(self):
        pass

    def _getch(self, wait_tenths):
        ts = time.time()
        if wait_tenths is None:
            while True:
                ch = self._getch_nodelay()
                if ch != -1:
                    return ch
                eventlet.sleep(0.001)

        while wait_tenths >= 0:
            ch = self._getch_nodelay()
            if ch != -1:
                return ch
            wait_tenths -= 1
            if wait_tenths > 0:
                eventlet.sleep(0.1)

        return -1

