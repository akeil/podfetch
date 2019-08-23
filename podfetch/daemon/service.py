#-*- coding: utf-8 -*-
'''Podfetch daemon main module.'''
import logging
import signal
from threading import Timer
from threading import Thread

from podfetch.daemon.webapi import Web


LOG = logging.getLogger(__name__)


def run(app, options):
    daemon = Daemon(app, options)

    def on_sigint(sig, frame):
        daemon.stop()

    signal.signal(signal.SIGINT, on_sigint)
    daemon.start()
    signal.pause()  #wait ...


class Daemon:

    def __init__(self, app, options):
        self._app = app
        self._options = options
        self._timer = None
        self._interval = options.daemon.update_interval
        self._services = [
            Web(app, options),
        ]

    def start(self):
        LOG.debug('Daemon starts')
        LOG.debug('Timer starts (interval %s minutes)', self._interval)
        self._start_timer()

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
        if self._timer:
            LOG.debug('Stopping timer')
            self._timer.cancel()

        for service in self._services:
            LOG.debug('Shutdown %r', service)
            service.stop()

    def _start_timer(self):
        if self._timer:
            self._timer.cancel()

        def tick():
            LOG.debug('Timer ticked')
            self._start_timer()  # schedule next
            self._app.update()

        interval = self._interval * 60.0  # minutes to seconds
        self._timer = Timer(interval, tick)
        self._timer.daemon = True
        self._timer.start()
