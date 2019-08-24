#-*- coding: utf-8 -*-
'''DBus API for podfetch.

pip install dbus-python
'''
import itertools
import logging

import dbus
from dbus import service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from podfetch.exceptions import NoSubscriptionError
from podfetch.predicate import NameFilter


LOG = logging.getLogger(__name__)

_IFACE = 'de.akeil.Podfetch'
_OBJECT_PATH = '/de/akeil/Podfetch'

_mainloop = None


def start(app, options):
    # start event loop *before* connecting to bus
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    # this makes us visible under de.akeil.PodfetchService
    # NOTE: only works, if we assign it to a variable (???)
    _ = dbus.service.BusName('de.akeil.PodfetchService', bus,
        allow_replacement=True,
        replace_existing=True,
    )

    # export our service
    service = _DBusPodfetch(bus, _OBJECT_PATH, app)

    global _mainloop
    _mainloop = GLib.MainLoop()
    _mainloop.run()


def stop():
    _mainloop.quit()


class NotFoundException(dbus.DBusException):
    _dbus_error_name = 'de.akeil.Podfetch.NotFoundException'


class InvalidArgumentException(dbus.DBusException):
    _dbus_error_name = 'de.akeil.Podfetch.InvalidArgumentException'


class _DBusPodfetch(dbus.service.Object):

    def __init__(self, bus, path, podfetch):
        super().__init__(bus, path)
        self._podfetch = podfetch

    @dbus.service.method(_IFACE)
    def Update(self):
        '''Trigger an update for all subscriptions.'''
        self._podfetch.update()

    @dbus.service.method(_IFACE, in_signature='s')
    def UpdateOne(self, name):
        '''Trigger an update for a single subscription.'''
        predicate = NameFilter(name)
        self._podfetch.update(predicate=predicate)

    @dbus.service.method(_IFACE, in_signature='s', out_signature='a{ss}')
    def ShowSubscription(self, name):
        '''Show details for a subscription.'''
        try:
            sub = self._podfetch.subscription_for_name(name)
        except NoSubscriptionError:
            raise NotFoundException

        return {
            'name': sub.name,
            'title': sub.title,
        }

    @dbus.service.method(_IFACE, in_signature='ss', out_signature='a{ss}')
    def AddSubscription(self, url, name):
        '''Subscribe to a new podcast.'''
        try:
            sub = self._podfetch.add_subscription(url, name=name)
        except NoSubscriptionError:
            raise NotFoundException

        return {
            'name': sub.name,
            'title': sub.title,
        }

    @dbus.service.method(_IFACE, in_signature='sb')
    def RemoveSubscription(self, name, delete_content):
        '''Unsubscribe from a podcast
        and optionally delete downloaded episodes.'''
        try:
            self._podfetch.remove_subscription(name,
                delete_content=delete_content)
        except NoSubscriptionError:
            raise NotFoundException

    @dbus.service.method(_IFACE, in_signature='s')
    def EnableSubscription(self, name):
        '''Set a subscription *enabled*.'''
        try:
            self._podfetch.edit(name, enabled=True)
        except NoSubscriptionError:
            raise NotFoundException

    @dbus.service.method(_IFACE, in_signature='s')
    def DisableSubscription(self, name):
        '''Disable a subscription.'''
        try:
            self._podfetch.edit(name, enabled=False)
        except NoSubscriptionError:
            raise NotFoundException

    @dbus.service.method(_IFACE, in_signature='i', out_signature='a(sss(iiiiii)a(sss))')
    def Episodes(self, limit):
        '''Show ``limit`` recent episodes.'''
        episodes = self._podfetch.list_episodes(limit=limit)

        # marshal to tuple (struct)
        # signature: a(sss(iiiiii)a(sss))
        #            ^ ^  ^       ^
        #            | |  |       `-- array with file-structs, three strings
        #            | |  `---------- timetuple with six ints
        #            | `------------- three string attributes
        #            `--------------- array of structs
        return [(
            e.id,
            e.subscription.name,
            e.title,
            tuple(e.pubdate[0:6]) if e.pubdate else (0, 0, 0, 0, 0, 0),
            e.files or []
        ) for e in episodes]
