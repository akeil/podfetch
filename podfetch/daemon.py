#-*- coding: utf-8 -*-
'''Podfetch daemon main module.

Used when podfetch is started in daemon mode.

Starts and stops service plugins.
'''
import atexit
import logging
import os
from pathlib import Path
from pkg_resources import iter_entry_points
import signal
from threading import Thread

from podfetch.exceptions import PodfetchError


LOG = logging.getLogger(__name__)

EP_SERVICE = 'podfetch.service'


def run(app, options):
    '''Run a podfetch instance in daemon mode.

    Will start all registered services and wait for SIGINT.
    On SIGINT or SIGTERM, services will be shutdown and the daemon stops.
    '''
    signal.signal(signal.SIGINT, _stop_services)
    signal.signal(signal.SIGTERM, _stop_services)

    _write_pidfile(options)
    atexit.register(_remove_pidfile, options)

    _start_services(app, options)
    signal.pause()  # wait ...


# Services --------------------------------------------------------------------


def _start_services(app, options):
    LOG.info('Starting services.')
    counter = 0
    for ep in iter_entry_points(EP_SERVICE, name='start'):
        LOG.info('Starting service %r', ep)
        try:
            start = ep.load()
        except ImportError as e:
            LOG.error('Failed to load entry point %r', ep)
            continue

        Thread(
            target=start,
            args=(app, options),
            daemon=True,
            name='service-worker-%d' % counter).start()
        counter += 1

    LOG.debug('Started %d services', counter)


def _stop_services(*args):
    LOG.info('Stopping services.')
    for ep in iter_entry_points(EP_SERVICE, name='stop'):
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


# PID file --------------------------------------------------------------------


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
        LOG.warning('Attempt to remove non-existing pidfile.')
        pass
