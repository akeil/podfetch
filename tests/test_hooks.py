#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Tests for podfetch hooks.
'''
import os
import stat

import pytest

from podfetch.hooks import _run_hooks
from podfetch.hooks import _discover_hooks
from podfetch.application import EVENTS


class DummyApp:

    config_dir = None


@pytest.fixture
def app(tmpdir):
    perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    for event in EVENTS:
        hook_dir = tmpdir.mkdir(event)
        hook_file = hook_dir.join('on_{}'.format(event))
        marker = tmpdir.join('{}.done'.format(event))
        hook_file.write('touch "{}"'.format(marker))
        os.chmod(str(hook_file), perms)

        ordinary = hook_dir.join('ordinary_file')
        ordinary.write('not a hook')

        failing = hook_dir.join('failing')
        failing.write('exit 1')
        os.chmod(str(failing), perms)

        args_marker = tmpdir.join('{}.used_args'.format(event))
        useargs = hook_dir.join('useargs')
        useargs.write('echo $1 $2 > {}'.format(args_marker))
        os.chmod(str(useargs), perms)

    dummy_app = DummyApp
    dummy_app.config_dir = str(tmpdir)
    return dummy_app


def test_hook_discovery(app):
    for event in EVENTS:
        hooks = [h for h in _discover_hooks(app.config_dir, event)]
        assert len(hooks) == 3


def test_hook_execution(app):
    for event in EVENTS:
        marker = os.path.join(
            os.path.dirname(os.path.join(app.config_dir, event)),
            '{}.done'.format(event)
        )
        args_marker = os.path.join(
            os.path.dirname(os.path.join(app.config_dir, event)),
            '{}.used_args'.format(event)
        )
        assert not os.path.exists(marker)
        arg1 = 'arg\' {1'
        arg2 = 2
        _run_hooks(app.config_dir, event, arg1, arg2)
        assert os.path.exists(marker)
        assert os.path.exists(args_marker)
        with open(args_marker) as f:
            assert f.read().strip() == '{} {}'.format(arg1, arg2)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
