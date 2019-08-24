#-*- coding: utf-8 -*-
'''Podfetch daemon main module.'''
import logging
import os
from pathlib import Path
from pkg_resources import iter_entry_points
import signal
from threading import Thread

from podfetch.exceptions import PodfetchError


LOG = logging.getLogger(__name__)

EP_SERVICE_START = 'podfetch.service.start'
EP_SERVICE_STOP = 'podfetch.service.stop'


def run(app, options):
    '''Run a podfetch instance in daemon mode.

    Will start all registered services and wait for SIGINT.
    On SIGINT, services will be shutdown and the daemon stops.
    '''
    def on_sigint(unused_sig, unused_frame):
        _stop_services()

    signal.signal(signal.SIGINT, on_sigint)

    _write_pidfile(options)
    try:
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
    finally:
        _remove_pidfile(options)


def _stop_services():
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


def read_pid(options):
    '''Read the process id of a running Podfetch daemon.
    Returns the PID or None, if no daemon is running.
    '''
    path = Path(options.daemon.pidfile)
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def _write_pidfile(options):
    '''Write the pidfile.
    Raises PodfetchError if a pid already exists.
    '''
    existing_pid = read_pid(options)
    if existing_pid:
        raise PodfetchError('Daemon already running with PID %s' % existing_pid)

    pid = os.getpid()
    Path(options.daemon.pidfile).write_text(str(pid))


def _remove_pidfile(options):
    '''Delete the pidfile.'''
    path = Path(options.daemon.pidfile)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
