# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""
Urwid extensions: Eventlet happy Raw display implementation
"""

import eventlet, select, errno
from urwid import raw_display
from eventlet.green import time


class RawScreen(raw_display.Screen):

    def __init__(self):
        super(RawScreen, self).__init__()

    def signal_init(self):
        pass

    def real_signal_init(self):
        super(RawScreen, self).signal_init()

    def signal_restore(self):
        pass

    def real_signal_restore(self):
        super(RawScreen, self).signal_restore()

    def _wait_for_input_ready(self, timeout):
        ready = None
        p = select.poll()
        p.register(self._term_input_file.fileno(), select.POLLIN)

        if self.gpm_mev is not None:
            p.register(self.gpm_mev.stdout.fileno(), select.POLLIN)

        while True:
            try:
                if timeout is None:
                    events = p.poll(0)
                    if events is None or len(events) == 0:
                        eventlet.sleep(0.1)
                        continue
                else:
                    events = p.poll(timeout)
                ready = []
                for fd, event in events:
                    if event == select.POLLIN:
                        ready.append(fd)
                break

            except select.error, e:
                if e.args[0] != select.EINTR:
                    raise
                if self._resized:
                    ready = []
                    break

        return ready

