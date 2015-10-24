#-*- coding: utf-8 -*-
'''
Builtin hooks for podfetch events.

This module runs scripts on events.
If an executable file with the same name as the event is found in the
application's config directory, it is run when the event occurs.
'''
import logging
import os
import subprocess

try:
    from shlex import quote as shlex_quote  # python 3.x
except ImportError:
    from pipes import quote as shlex_quote  # python 2.x


log = logging.getLogger(__name__)


# entry points for setup.py --------------------------------------------------


def on_subscription_updated(app, *args):
    _run_hooks(app.config_dir, 'subscription_updated', *args)


def on_updates_complete(app, *args):
    _run_hooks(app.config_dir, 'updates_complete', *args)


def on_subscription_added(app, *args):
    _run_hooks(app.config_dir, 'subscription_added', *args)


def on_subscription_removed(app, *args):
    _run_hooks(app.config_dir, 'subscription_removed', *args)


# implementation -------------------------------------------------------------


def _run_hooks(config_dir, event, *args):
    for executable in _discover_hooks(config_dir, event):
        _run_one_hook(event, executable, *args)


def _run_one_hook(event, executable, *args):
    try:
        devnull = subprocess.DEVNULL
    except AttributeError:  # python 2.x
        devnull = open(os.devnull, 'w')

    call_args = [shlex_quote(str(arg)) for arg in args]
    call_args.insert(0, executable)
    argstr = ' '.join(call_args)

    log.debug('Run hook: {s!r}'.format(s=argstr))
    exit_code = subprocess.call(argstr,
        shell=True,
        stdout=devnull,
        stderr=devnull,
    )

    name = os.path.basename(executable)
    if exit_code == 0:
        log.debug(('Successfully ran hook {!r}'
            ' on event {!r}.').format(name, event))
    else:
        log.error(('Hook {!r} exited with non-zero exit status ({})'
            ' on event {!r}.').format(name, exit_code, event))


def _discover_hooks(config_dir, event):
    hooks_dir = os.path.join(config_dir, event)
    try:
        hooks = os.listdir(hooks_dir)
    except OSError as e:
        if e.errno == os.errno.ENOENT:
            hooks = []
        else:
            raise

    def is_executable(path):
        # must check if it is a _file_
        # directories can also have an "executable" bit set
        return os.path.isfile(path) and os.access(path, os.X_OK)

    for name in hooks:
        path = os.path.join(hooks_dir, name)
        if is_executable(path):
            log.debug('Found hook {!r}.'.format(name))
            yield path
        else:
            log.warning((
                'File {!r} in hooks dir {!r} is not executable'
                ' and will not be run.').format(name, hooks_dir))
