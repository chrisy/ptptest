# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""
UI
"""

import eventlet, urwid
from urwidutils import EventletEventLoop


class UI(object):
    client = False
    server = False
    parent = None

    _root = None
    _log = None
    _mainloop = None

    palette = [
            ('header', 'yellow', 'dark blue', 'standout'),
            ('log-hdr', 'white', 'dark blue', 'standout'),
            ('log', 'light gray', 'black'),
            ('table header', 'light green', 'black', 'standout'),
            ('table server', 'light gray', 'black', 'standout'),
            ('table client', 'yellow', 'black', 'standout'),
            ('body', 'dark green', 'black'),
    ]

    cols = [
        ('addr', 'Address',   '%s', 3,),
        ('sent', 'Pkts Sent', '%d', 1,),
        ('lost', 'Pkts Lost', '%d', 1,),
        ('rtt',  'Avg RTT',   '%f', 1,),
    ]

    _peers = {}
    _group = {}

    def __init__(self, client=False, server=False, parent=None):
        super(UI, self).__init__()

        self.client = client
        self.server = server
        self.parent = parent

        # Initialize the UI elements
        root = self._buildui()

        self._peers['client'] = []
        self._peers['server'] = []

        # GUI thread
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

            # This runs the UI loop - it only returns when we're exiting
            self._mainloop.run()

            # Remove this, to stop further interaction
            self._mainloop = None

            # Signal the parent that we're stopping
            if parent is not None:
                parent.running = False

        # Start the UI thread
        eventlet.spawn(uirun)

    def _buildui(self):

        self._header = urwid.Text('')
        header = urwid.AttrMap(self._header, 'header')

        hcols = []
        for col in self.cols:
            (label, descr, fmt, weight) = col
            w = urwid.Text(descr)
            hcols.append(('weight', weight, w))

        table_header = urwid.AttrMap(urwid.Columns(hcols), 'table header')

        th = urwid.ListBox(urwid.SimpleFocusListWalker([table_header]))
        self._group = {
            'client': urwid.SimpleListWalker([]),
            'server': urwid.SimpleListWalker([]),
        }
        parts = [th]
        parts.append(urwid.AttrMap(urwid.ListBox(self._group['server']), 'table server'))
        parts.append(urwid.AttrMap(urwid.ListBox(self._group['client']), 'table client'))
        #parts.append(urwid.Divider())
        body = urwid.AttrMap(urwid.Pile(parts), 'body')

        self._log = urwid.SimpleFocusListWalker([])
        log = urwid.ListBox(self._log)
        log = urwid.BoxAdapter(log, 10)
        log = urwid.AttrMap(log, 'log')

        footer = urwid.Pile([
            urwid.Divider(div_char=u'\u2500'),
            urwid.AttrMap(urwid.Text("Log output"), 'log-hdr'),
            log])
        footer = urwid.AttrMap(footer, 'footer')

        return urwid.Frame(body, header=header, footer=footer)

    def log(self, text, stdout=False):
        """Send a log message to the logging part of the UI"""

        if stdout:
            print(text)

        for line in text.split("\n"):
            while len(self._log) > 10:
                self._log.pop(0)
            self._log.append(urwid.Text(line))

        self._log.set_focus(len(self._log)-1)

        #if self._mainloop is not None:
            #self._mainloop.draw_screen()

    def title(self, text, stdout=False):
        """Set page title"""
        if stdout:
            print(text)
        self._header.set_text(text)

    def _find_peer(self, group, sin):
        index = 0
        for peer in self._peers[group]:
            if peer == sin:
                return index 
            index += 1
        return None

    def peer_update(self, group, sin, stats):
        if 'sent' in stats and 'rcvd' in stats:
            stats['lost'] = stats['sent'] - stats['rcvd']

        index = self._find_peer(group, sin)
        if index is None:
            return

        colnum = -1
        for col in self.cols:
            (label, descr, fmt, weight) = col
            colnum += 1
            if label in ('addr',):
                continue
            if label in stats:
                text = fmt % stats[label]
                self._group[group][index][colnum].set_text(text)

    def peer_add(self, group, sin):
        if self._find_peer(group, sin) is not None:
            return

        hcols = []
        for col in self.cols:
            (label, descr, fmt, weight) = col
            text = None
            if label == 'addr':
                text = repr(sin)
            else:
                text = ""
            w = urwid.Text(text)
            hcols.append(('weight', weight, w))

        te = urwid.Columns(hcols)

        self._peers[group].append(sin)
        self._group[group].append(te)

    def peer_del(self, group, sin):
        index = self._find_peer(group, sin)

        if index is None:
            return

        self._peers[group].pop(index)
        self._group[group].pop(index)
