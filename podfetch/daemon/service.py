#-*- coding: utf-8 -*-
'''Podfetch daemon main module.'''
import logging
import signal
from threading import Thread

from podfetch.daemon import dbusapi
from podfetch.daemon import scheduler
from podfetch.daemon import webapi


LOG = logging.getLogger(__name__)


def run(app, options):
    '''Run a podfetch instance in daemon mode.

    Will start all registered services and wait for SIGINT.
    On SIGINT, services will be shutdown and the daemon stops.
    '''
    services = _ServiceManager(app, options)

    def on_sigint(sig, frame):
        services.stop()

    signal.signal(signal.SIGINT, on_sigint)
    services.start()
    signal.pause()  # wait ...


class _ServiceManager:

    def __init__(self, app, options):
        self._app = app
        self._options = options
        self._services = [
            dbusapi,
            scheduler,
            webapi,
        ]

    def start(self):
        LOG.debug('Daemon starts')

        n = 0
        for service in self._services:
            worker = Thread(
                target=service.start,
                args=(self._app, self._options),
                daemon=True,
                name='service-worker-%d' % n)
            worker.start()
            n += 1

    def stop(self):
        LOG.debug('Daemon stops')
        for service in self._services:
            service.stop()
