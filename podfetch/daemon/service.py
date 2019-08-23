#-*- coding: utf-8 -*-
'''Podfetch daemon main module.'''
import logging
import signal
from threading import Timer
from threading import Thread

from podfetch.daemon.dbusapi import DBus
from podfetch.daemon.webapi import Web


LOG = logging.getLogger(__name__)


def run(app, options):
    daemon = Daemon(app, options)

    def on_sigint(sig, frame):
        daemon.stop()

    signal.signal(signal.SIGINT, on_sigint)
    daemon.start()
    signal.pause()  # wait ...


class Daemon:

    def __init__(self, app, options):
        self._services = [
            Web(app, options),
            _Scheduler(app, options),
            DBus(app, options),
        ]

    def start(self):
        LOG.debug('Daemon starts')

        n = 0
        for service in self._services:
            LOG.info('Starting service %r', service)
            worker = Thread(
                target=service.run,
                daemon=True,
                name='service-worker-%d' % n)
            worker.start()
            n += 1

    def stop(self):
        LOG.debug('Daemon stops')
        for service in self._services:
            LOG.debug('Shutdown %r', service)
            service.stop()


class _Scheduler:

    def __init__(self, app, options):
        self._timer = None
        self._interval = options.daemon.update_interval * 60.0  # minutes to seconds

    def run(self):
        self._start_timer()

    def stop(self):
        self._cancel_timer()

    def _start_timer(self):
        self._cancel_timer()

        def tick():
            self._app.update()
            self._start_timer()  # schedule next

        self._timer = Timer(self._interval, tick)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def __repr__(self):
        return '<Scheduler interval=%s>' % self._interval
