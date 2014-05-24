# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""
UI
"""

import eventlet, urwid
from urwidutils import EventletEventLoop

class LogBox(urwid.ListBox):
    length = 10

    def __init__(self, length=10):
        body = urwid.SimpleFocusListWalker([urwid.Text("Log")])
        super(LogBox, self).__init__(body)
        self.length = length

    def addline(self, line):
        while len(self.body) > self.length:
            self.body.pop(0)
        self.body.append(urwid.Text(text))


class UI(object):
    client = False
    server = False
    parent = None

    _root = None
    _log = None
    _mainloop = None

    palette = [
            ('body', 'black', 'light gray'),
            ('header', 'yellow', 'black', 'standout'),
            ('footer', 'light gray', 'black'),
    ]

    def __init__(self, client=False, server=False, parent=None):
        super(UI, self).__init__()

        self.client = client
        self.server = server
        self.parent = parent

        root = self._buildui()
        # Gui thread
        def uirun():

            # Handle our keypresses
            def inkey(key):
                if key in ('q', 'Q'):
                    raise urwid.ExitMainLoop()

            # The screen
            self._screen = urwid.raw_display.Screen()

            # Build the UI mainloop
            self._mainloop = urwid.MainLoop(
                    widget=root,
                    palette=self.palette,
                    screen=self._screen,
                    event_loop=EventletEventLoop(),
                    unhandled_input=inkey,
                    handle_mouse=False)
            self._root = root

            self._mainloop.run()

            # Remove this, to stop further interaction
            self._mainloop = None

            # Signal the parent that we're stopping
            if parent is not None:
                parent.running = False

        eventlet.spawn(uirun)

    def _buildui(self):

        header = urwid.Text("Header")
        header = urwid.AttrMap(header, 'header')

        body = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text("body")]))
        body = urwid.AttrMap(body, 'body')

        footer = urwid.SimpleFocusListWalker([urwid.Text("Log")])
        self._log = footer
        footer = urwid.ListBox(footer)
        footer = urwid.BoxAdapter(footer, 10)
        footer = urwid.AttrMap(footer, 'footer')

        return urwid.Frame(body, header=header, footer=footer)

    def log(self, text):
        """Send a log message to the logging part of the UI"""
        for line in text.split("\n"):
            while len(self._log) > 10:
                self._log.pop(0)
            self._log.append(urwid.Text(line))

        self._log.set_focus(len(self._log)-1)

        if self._mainloop is not None:
            self._mainloop.draw_screen()


