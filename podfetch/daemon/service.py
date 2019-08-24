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

    def on_sigint(unused_sig, unused_frame):
        LOG.info('Stopping services.')
        services = _load_services()
        for service in services:
            try:
                service.stop()
            except Exception as err:
                LOG.error('Error stopping service: %s', err)
                LOG.debug(err, exc_info=True)

    signal.signal(signal.SIGINT, on_sigint)

    LOG.info('Starting services.')
    services = _load_services()
    for counter, service in enumerate(services):
        worker = Thread(
            target=service.start,
            args=(app, options),
            daemon=True,
            name='service-worker-%d' % counter)
        worker.start()

    signal.pause()  # wait ...


def _load_services():
    return [
        dbusapi,
        scheduler,
        webapi,
    ]
