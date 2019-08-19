#-*- coding: utf-8 -*-
'''Podfetch daemon main module.'''
import logging

from podfetch.daemon.webapi import Web


LOG = logging.getLogger(__name__)


def run(app, options):

    daemon = Daemon(app, options)
    try:
        daemon.start()
    except KeyboardInterrupt:
        pass

    daemon.stop()


class Daemon:

    def __init__(self, app, options):
        self._app = app
        self._options = options
        self._services = [
            Web(app, options)
        ]

    def start(self):
        LOG.debug('daemon starts')
        for service in self._services:
            LOG.info('Starting service %r', service)
            service.startup()

    def stop(self):
        LOG.debug('daemon stops')
