#-*- coding: utf-8 -*-
'''DBus API for podfetch.

pip install dbus-python
'''
import itertools
import logging

import dbus
from dbus import service
from dbus.mainloop.glib import DBusGMainLoop

from podfetch.predicate import Filter


LOG = logging.getLogger(__name__)

_IFACE = 'de.akeil.Podfetch'
_OBJECT_PATH = '/de/akeil/Podfetch'


class DBus:

    def __init__(self, app, options):
        self._podfetch = app
        self._mainloop = None

    def run(self):
        # start event loop *before* connecting to bus
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        # this makes us visible under de.akeil.PodfetchService
        # NOTE: only works, if we assign it to a variable (???)
        _ = dbus.service.BusName('de.akeil.PodfetchService', bus)
        LOG.debug('DBus bus-name: %r', bus.get_unique_name())
        # export our service
        service = _DBusPodfetch(bus, _OBJECT_PATH, self._podfetch)

        from gi.repository import GLib
        self._mainloop = GLib.MainLoop()
        self._mainloop.run()

    def stop(self):
        if self._mainloop:
            self._mainloop.quit()

    def __repr__(self):
        return '<DBus>'



class _DBusPodfetch(dbus.service.Object):

    def __init__(self, bus, path, podfetch):
        super().__init__(bus, path)
        self._podfetch = podfetch

    @dbus.service.method(_IFACE, in_signature='', out_signature='')
    def Update(self):
        self._podfetch.update()

    @dbus.service.method(_IFACE, in_signature='s', out_signature='a{ss}')
    def Show(self, name):
        sub = self._podfetch.subscription_for_name(name)
        return {
            'name': sub.name,
            'title': sub.title,
        }

    @dbus.service.method(_IFACE, in_signature='i', out_signature='a(sss(iiiiii)a(sss))')
    def Episodes(self, limit):
        # TODO: check limit > 0
        accept = Filter()

        # fetch ALL episodes
        episodes = [
            e for e in itertools.chain(*[
                s.episodes for s in self._podfetch.iter_subscriptions()
            ])
            if accept(e)
        ]

        # sort by date and fetch n newest
        episodes.sort(key=lambda e: e.pubdate, reverse=True)
        episodes = episodes[:limit]

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
