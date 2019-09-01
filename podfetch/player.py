#-*- coding: utf-8 -*-
'''
Player module for podfetch
'''
import logging
from pathlib import Path
from subprocess import DEVNULL
from subprocess import Popen

from podfetch.exceptions import PodfetchError


LOG = logging.getLogger(__name__)


def Player(app, options):
    # TODO choose player implementation
    factory = CmdPlayer
    #factory = DBusPlayer

    return factory(app, options)


class PlayerError(PodfetchError):
    pass


class UnsupportedCommandError(PlayerError):
    '''Raised when a player implementation does not support a given command.'''
    pass


class BasePlayer:

    def play(self, episode, wait=False):
        LOG.debug('Play %r', self)
        self.stop()
        # files: (url, content-type, local)
        files = [f[2] for f in episode.files if Path(f[2]).is_file()]
        if not files:
            raise PlayerError('Episode %r has no local files' % episode)

        self.do_play(*files, wait=wait)

    def do_play(self, *files, wait=False):
        raise UnsupportedCommandError

    def stop(self):
        raise UnsupportedCommandError

    def pause(self):
        raise UnsupportedCommandError


class CmdPlayer(BasePlayer):

    def __init__(self, app, options):
        self._cmd = options.player.command
        self._proc = None

    def do_play(self, *files, wait=False):
        args = [self._cmd, ] + list(files)
        LOG.debug('Exec %r', ' '.join(args))
        self._proc = Popen(
            args,
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL
        )

        if wait:
            try:
                self._proc.wait()
            except Exception:
                # mark episode as listened if we have listened for at least *n* minutes
                self.stop()
                raise

            LOG.debug('%r exited with code %s', self, self._proc.returncode)
            #TODO marks episode as "listened"

    def stop(self):
        if self._proc:
            LOG.debug('Stopping %r', self)
            self._proc.terminate()
            self._proc = None

    def __repr__(self):
        return '<CmdPlayer %r>' % self._cmd


import dbus
import dbus.mainloop.glib
from dbus.exceptions import DBusException
from gi.repository import GLib


_PLAYER_PATH = '/org/mpris/MediaPlayer2'
_MPRIS_IFACE = 'org.mpris.MediaPlayer2'
_PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player'
_TRACKLIST_IFACE = 'org.mpris.MediaPlayer2.TrackList'
_PROPS_IFACE = 'org.freedesktop.DBus.Properties'

_EXC_INVALID_ARGS = 'org.freedesktop.DBus.Error.InvalidArgs'
_EXC_UNKNOWN_METHOD = 'org.freedesktop.DBus.Error.UnknownMethod'

_BEGINNING = dbus.ObjectPath('/org/mpris/MediaPlayer2/TrackList/NoTrack')


class DBusPlayer(BasePlayer):

    def __init__(self, app, options):
        # start the main loop
        self._blacklist = ['vlc', ]
        self._bus = None
        self._players = []
        self._active_player = None

        self._connect()
        self._list_players()

    def _connect(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        loop = GLib.MainLoop()
        self._bus = dbus.SessionBus()
        self._bus.add_signal_receiver(self._on_name_owner_changed, 'NameOwnerChanged')

    def _on_name_owner_changed(self,  bus_name, old_owner, new_owner):
        LOG.debug('NameOwnerChanged for %r', bus_name)
        if not _is_mpris_player(bus_name):
            return
        if self._is_blacklisted(bus_name):
            return

        if old_owner and not new_owner:
            # player disappeared
            self._remove_player(bus_name)
        elif not old_owner and new_owner:
            # new player appeared
            self._add_player(bus_name)
        elif old_owner and new_owner:
            # owner changed
            self._change_owner(bus_name)

    def _remove_player(self, bus_name):
        try:
            self._players.remove(bus_name)
        except ValueError:
            pass  # was not in list

    def _add_player(self, bus_name):
        if bus_name not in self._players:
            self._players.append(bus_name)

    def _change_owner(bus_name):
        pass

    def _is_blacklisted(self, bus_name):
        simple_name = _extract_player_name(bus_name)
        return simple_name in self._blacklist

    def _list_players(self):
        names = [
            n for n in self._bus.list_names()
            if _is_mpris_player(n) and not self._is_blacklisted(n)
        ]
        self._players = names
        for name in names:
            LOG.debug(name)

    def _select_player(self):
        if not self._players:
            raise ValueError('No players discovered')

        bus_name = self._players[0]

        proxy = self._bus.get_object(bus_name, _PLAYER_PATH)
        player_iface = dbus.Interface(proxy, dbus_interface=_PLAYER_IFACE)
        tracklist_iface = dbus.Interface(proxy, dbus_interface=_TRACKLIST_IFACE)
        props_iface = dbus.Interface(proxy, _PROPS_IFACE)
        return player_iface, tracklist_iface, props_iface

    def _open_uri(self, p, uri):
        try:
            p.OpenUri(uri)
        except DBusException as exc:
            LOG.debug(exc, exc_info=True)
            name = exc.get_dbus_name()
            if name == _EXC_UNKNOWN_METHOD:
                raise UnsupportedCommandError
            else:
                raise PlayerError(str(exc))

    def _add_track(self, tracklist, props, uri, play_now):
        can_edit = False
        try:
            can_edit = props.Get(_TRACKLIST_IFACE, 'CanEditTracks')
        except DBusException as exc:
            name = exc.get_dbus_name()
            # will be raised if the player does not support the interface
            if name == _EXC_INVALID_ARGS:
                raise UnsupportedCommandError
            else:
                raise PlayerError(str(exc))

        if not can_edit:
            raise UnsupportedCommandError

        after = None
        tracks = props.Get(_TRACKLIST_IFACE, 'Tracks')
        if tracks:
            after = tracks[-1]
        else:
            after = _BEGINNING

        tracklist.AddTrack(uri, after, play_now)

    def do_play(self, *files, wait=False):
        uris = ['file://%s' % file for file in files]
        player, tracklist, props = self._select_player()

        try:
            first = True
            for uri in uris:
                self._add_track(tracklist, props, uri, first)
                first = False
        except UnsupportedCommandError:
            self._open_uri(player, uris[0])

        self._active_player = player

    def stop(self):
        if self._active_player:
            self._active_player.Stop()

    def __repr__(self):
        return '<DBusPlayer>'


def _is_mpris_player(bus_name):
    return bus_name.startswith(_MPRIS_IFACE)


def _extract_player_name(bus_name):
    '''Extracts a player name from a bus name.
    E.g. "vlc" from "org.mpris.MediaPlayer2.vlc".
    Note that players with multiple instance are named like this:
    "org.mpris.MediaPlayer2.vlc.instance1234"

    see:
    https://specifications.freedesktop.org/mpris-spec/latest/#Bus-Name-Policy
    '''
    return bus_name.split('.')[3]
