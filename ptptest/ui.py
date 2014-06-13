# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""
UI
"""

import eventlet, urwid, sys, signal
from urwid_eventlet import EventletEventLoop


class UI(object):
    client = False
    server = False
    parent = None
    log_lines = 10

    _root = None
    _log = None
    _mainloop = None
    _screen = None
    _event_loop = None
    _address = None
    _stuntype = None
    _stunaddress = None

    palette = [
            ('header', 'yellow', 'dark blue', 'standout'),
            ('log-hdr', 'white', 'dark blue', 'standout'),
            ('log', 'light gray', 'black'),
            ('table header', 'light green', 'dark blue', 'standout'),
            ('table server', 'light gray', 'black', 'standout'),
            ('table client', 'yellow', 'black', 'standout'),
            ('body', 'dark green', 'black'),
    ]

    cols = [
        ('addr', 'Address',   '%s', 3,),
        ('sent', 'Pkts Sent', '%d', 1,),
        ('rcvd', 'Pkts Rcvd', '%d', 1,),
        ('lost', 'Acks Lost', '%d', 1,),
        ('rtt',  'Avg RTT',   '%f', 1,),
    ]

    _peers = {}
    _group = {}

    def __init__(self, client=False, server=False, parent=None,
            force_curses=False):
        super(UI, self).__init__()

        self.client = client
        self.server = server
        self.parent = parent

        # Initialize the UI elements
        root = self._buildui()

        self._peers['client'] = []
        self._peers['server'] = []

        # The screen for the UI
        # https://docs.python.org/2/library/sys.html#sys.platform
        if force_curses or sys.platform == 'win32': # Does not include Cygwin
            from curses_wrapper import CursesScreen
            self._screen = CursesScreen()
            self._screen.set_input_timeouts(max_wait=0.1)
            self._event_loop = None
        else:
            from raw_wrapper import RawScreen
            self._screen = RawScreen()
            self._screen.real_signal_init()
            self._event_loop = EventletEventLoop()

        def sigint(signal, frame):
            if self._mainloop is not None:
                self._mainloop.event_loop.running = False

        try: signal.signal(signal.SIGINT, sigint)
        except: pass
        try: signal.signal(signal.CTRL_C_EVENT, sigint)
        except: pass

        # GUI thread
        def uirun():

            # Handle our keypresses
            def inkey(key):
                self.log('inkey=%s' % key)
                if key in ('q', 'Q'):
                    raise urwid.ExitMainLoop()
                return False

            # Build the UI mainloop
            self._mainloop = urwid.MainLoop(
                    widget=root,
                    palette=self.palette,
                    screen=self._screen,
                    event_loop=self._event_loop,
                    unhandled_input=inkey,
                    handle_mouse=False)
            self._root = root

            if self._event_loop is None:
                def draw_screen():
                    if self._mainloop is not None:
                        self._mainloop.draw_screen()
                        eventlet.spawn_after(1, draw_screen)

                eventlet.spawn_after(1, draw_screen)

            # This runs the UI loop - it only returns when we're exiting
            self._mainloop.run()

            # Remove signals
            self._screen.real_signal_restore()
            try: signal.signal(signal.SIGINT, signal.SIG_DFL)
            except: pass
            try: signal.signal(signal.CTRL_C_EVENT, signal.SIG_DFL)
            except: pass

            # Remove these, to stop further interaction
            self._mainloop = None
            self._screen = None

            # Signal the parent that we're stopping
            if self.parent is not None:
                self.parent.running = False
                self.parent = None

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

        # The parts of the window
        parts = []

        # Table header
        table_header = urwid.AttrMap(urwid.Columns(hcols), 'table header')
        parts.append(('pack', table_header))

        # Client and server sections
        self._group = {
            'client': urwid.Pile([]),
            'server': urwid.Pile([]),
        }
        parts.append(('pack', urwid.AttrMap(self._group['server'], 'table server')))
        parts.append(urwid.AttrMap(self._group['client'], 'table client'))
        
        body = urwid.AttrMap(urwid.Pile(parts), 'body')

        # Logging output footer
        self._log = urwid.SimpleFocusListWalker([])
        log = urwid.ListBox(self._log)
        log = urwid.BoxAdapter(log, self.log_lines)
        log = urwid.AttrMap(log, 'log')

        log_footer = urwid.Pile([
            #urwid.AttrMap(urwid.Divider(div_char=u'\u2500'), 'log-hdr'),
            urwid.AttrMap(urwid.Text("Log output"), 'log-hdr'),
            log])

        self._address = urwid.Text("")
        self._stuntype = urwid.Text("")
        self._stunaddress = urwid.Text("")

        self.set_address('Unknown', None)
        self.set_stun('Unknown', 'Unknown', None)

        status_footer = urwid.Pile([
            urwid.AttrMap(urwid.Text("Status"), 'log-hdr'),
            self._address,
            self._stuntype,
            self._stunaddress,
        ])

        footer = urwid.Columns([
            ('weight', 4, log_footer),
            ('weight', 2, status_footer),
        ])
        footer = urwid.AttrMap(footer, 'footer')

        return urwid.Frame(body, header=header, footer=footer)

    def log(self, text, stdout=False, indent=''):
        """Send a log message to the logging part of the UI"""

        if stdout:
            print(text)

        for line in text.split("\n"):
            while len(self._log) > self.log_lines:
                self._log.pop(0)
            self._log.append(urwid.Text(indent + line))

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
            stats['lost'] = stats['sent'] - stats['ackd']
            if stats['lost'] < 0: stats['lost'] = 0

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
        self._group[group].contents.append((te, ('pack', None)))

    def peer_del(self, group, sin):
        index = self._find_peer(group, sin)

        if index is None:
            return

        self._peers[group].pop(index)
        self._group[group].contents.pop(index)

    def set_address(self, address, port):
        addr = str(address)
        if port:
            addr = "%s:%d" % (addr, int(port))
        self._address.set_text("Address: %s" % addr)

    def set_stun(self, nat_type, external_ip, external_port):
        self._stuntype.set_text("NAT type: %s" % str(nat_type))
        addr = str(external_ip)
        #if external_port:
        #    addr = "%s:%d" % (addr, int(external_port))
        self._stunaddress.set_text("NAT address: %s" % addr)

