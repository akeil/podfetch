#-*- coding: utf-8 -*-
'''Podfetch daemon main module.'''
import logging
from pkg_resources import iter_entry_points
import signal
from threading import Thread


LOG = logging.getLogger(__name__)

EP_SERVICE_START = 'podfetch.service.start'
EP_SERVICE_STOP = 'podfetch.service.stop'


def run(app, options):
    '''Run a podfetch instance in daemon mode.

    Will start all registered services and wait for SIGINT.
    On SIGINT, services will be shutdown and the daemon stops.
    '''

    def on_sigint(unused_sig, unused_frame):
        LOG.info('Stopping services.')
        for ep in iter_entry_points(EP_SERVICE_STOP):
            LOG.info('Stopping %r', ep)
            try:
                stop = ep.load()
            except ImportError as e:
                LOG.error('Failed to load entry point %r', ep)
                continue

            try:
                stop()
            except Exception as err:
                LOG.error('Error stopping service: %s', err)
                LOG.debug(err, exc_info=True)

    signal.signal(signal.SIGINT, on_sigint)

    LOG.info('Starting services.')
    counter = 0
    for ep in iter_entry_points(EP_SERVICE_START):
        LOG.info('Starting service %r', ep)
        try:
            start = ep.load()
        except ImportError as e:
            LOG.error('Failed to load entry point %r', ep)
            continue

        worker = Thread(
            target=start,
            args=(app, options),
            daemon=True,
            name='service-worker-%d' % counter)
        worker.start()
        counter += 1

    LOG.debug('Started %d services', counter)

    signal.pause()  # wait ...
