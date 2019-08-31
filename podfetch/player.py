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


class PlayerError(PodfetchError):
    pass


class UnsupportedCommandError(PlayerError):
    '''Raised when a player implementation does not support a given command.'''
    pass

class Player:

    def play(self, episode, wait=False):
        raise UnsupportedCommandError

    def stop(self):
        raise UnsupportedCommandError

    def pause(self):
        raise UnsupportedCommandError


class CmdPlayer(Player):

    def __init__(self, cmd):
        self._cmd = cmd
        self._proc = None

    def play(self, episode, wait=False):
        LOG.debug('Play %r', self)
        self.stop()
        # files: (url, content-type, local)
        files = [f[2] for f in episode.files if Path(f[2]).is_file()]
        if not files:
            raise PlayerError('Episode %r has no local files' % episode)

        args = [self._cmd, ] + files
        # check if files actually exist?
        LOG.debug('Player: %r', ' '.join(args))
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
