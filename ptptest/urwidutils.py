# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""
Urwid extensions
"""

import heapq, eventlet, select, errno, urwid
from eventlet.green import time

class EventletEventLoop(object):
    """
    Event loop based on :func:`Eventlet`
    """

    def __init__(self):
        self._alarms = []
        self._watch_files = {}
        self._poll = select.poll()
        self._idle_handle = 0
        self._idle_callbacks = {}
        self._idle_ts = 0
        self.running = False

        eventlet.spawn(self._task);

    def _test_event_loop(self):
        """
        >>> import os
        >>> rd, wr = os.pipe()
        >>> evl = EventletEventLoop()
        >>> def step1():
        ...     print "writing"
        ...     os.write(wr, "hi".encode('ascii'))
        >>> def step2():
        ...     print os.read(rd, 2).decode('ascii')
        ...     raise ExitMainLoop
        >>> handle = evl.alarm(0, step1)
        >>> handle = evl.watch_file(rd, step2)
        >>> evl.run()
        writing
        hi
        """

    def alarm(self, seconds, callback):
        """
        Call callback() given time from from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- floating point time to wait before calling callback
        callback -- function to call from event loop
        """
        handle = eventlet.spawn_after(seconds, callback)
        heapq.heappush(self._alarms, handle)
        return handle

    def remove_alarm(self, handle):
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        try:
            handle.cancel()
            self._alarms.remove(handle)
            heapq.heapify(self._alarms)
            return True
        except ValueError:
            return False

    def _test_remove_alarm(self):
        """
        >>> evl = EventletEventLoop()
        >>> handle = evl.alarm(50, lambda: None)
        >>> evl.remove_alarm(handle)
        True
        >>> evl.remove_alarm(handle)
        False
        """

    def watch_file(self, fd, callback):
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.

        Returns a handle that may be passed to remove_watch_file()

        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """
        self._watch_files[fd] = callback
        self._poll.register(fd, select.POLLIN)

        return fd

    def remove_watch_file(self, handle):
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise
        """
        if handle in self._watch_files:
            self._poll.unregister(handle)
            del self._watch_files[handle]
            return True

        return False

    def _test_remove_watch_file(self):
        """
        >>> evl = EventletEventLoop()
        >>> handle = evl.watch_file(5, lambda: None)
        >>> evl.remove_watch_file(handle)
        True
        >>> evl.remove_watch_file(handle)
        False
        """

    def enter_idle(self, callback):
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_idle()
        """
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def remove_enter_idle(self, handle):
        """
        Remove an idle callback.

        Returns True if the handle was removed.
        """
        try:
            del self._idle_callbacks[handle]
        except KeyError:
            return False
        return True

    def _entering_idle(self):
        """
        Call all the registered idle callbacks.
        """
        for callback in self._idle_callbacks.values():
            callback()
            eventlet.sleep(0.01)
        self._idle_ts = time.time()

    def run(self):
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.
        """

        self.running = True

        # This can be done much much better...
        while self.running:
            eventlet.sleep(0.75)

    def _test_run(self):
        """
        >>> import os
        >>> rd, wr = os.pipe()
        >>> os.write(wr, "data".encode('ascii')) # something to read from rd
        4
        >>> evl = EventletEventLoop()
        >>> def say_hello():
        ...     print "hello"
        >>> def say_waiting():
        ...     print "waiting"
        >>> def exit_clean():
        ...     print "clean exit"
        ...     raise ExitMainLoop
        >>> def exit_error():
        ...     1/0
        >>> handle = evl.alarm(0.1, exit_clean)
        >>> handle = evl.alarm(0.05, say_hello)
        >>> evl.enter_idle(say_waiting)
        1
        >>> evl.run()
        waiting
        hello
        waiting
        clean exit
        >>> handle = evl.watch_file(rd, exit_clean)
        >>> evl.run()
        clean exit
        >>> evl.remove_watch_file(handle)
        True
        >>> handle = evl.alarm(0, exit_error)
        >>> evl.run()
        Traceback (most recent call last):
           ...
        ZeroDivisionError: integer division or modulo by zero
        >>> handle = evl.watch_file(rd, exit_error)
        >>> evl.run()
        Traceback (most recent call last):
           ...
        ZeroDivisionError: integer division or modulo by zero
        """

    def _task(self):
        while self.running:
            try:
                self._loop()
                eventlet.sleep(0.01)
            except select.error, e:
                print "oooh"
                if e.args[0] != errno.EINTR:
                    # not just something we need to retry
                    raise
            except urwid.ExitMainLoop:
                self.running = False


    def _loop(self):
        """
        A single iteration of the event loop
        """
        ready = self._poll.poll(0)
        if ready is not None and len(ready):
            for fd, event in ready:
                if event == select.POLLIN:
                    self._watch_files[fd]()
        else:
            self._entering_idle()

        # Make sure idle cb's don't get starved
        if time.time() - self._idle_ts > 0.5:
            self._entering_idle()


class Screen(urwid.raw_display.Screen):

    def __init__(self):
        super(Screen, self).__init__()

    def signal_init(self):
        pass

    def real_signal_init(self):
        super(Screen, self).signal_init()

    def signal_restore(self):
        pass

    def real_signal_restore(self):
        super(Screen, self).signal_restore()

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

