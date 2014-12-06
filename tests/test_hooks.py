#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Tests for podfetch hooks.
'''
import os
import stat

import pytest

from podfetch.application import HookManager
from podfetch.application import EVENTS


@pytest.fixture
def hookman(tmpdir):
    hm = HookManager(str(tmpdir))
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

    return hm


def test_hook_discovery(hookman):
    for event in EVENTS:
        hooks = [h for h in hookman.discover_hooks(event)]
        assert len(hooks) == 3


def test_hook_execution(hookman):
    for event in EVENTS:
        marker = os.path.join(
            os.path.dirname(hookman.hook_dirs[event]),
            '{}.done'.format(event)
        )
        args_marker = os.path.join(
            os.path.dirname(hookman.hook_dirs[event]),
            '{}.used_args'.format(event)
        )
        assert not os.path.exists(marker)
        arg1 = 'arg\' {1'
        arg2 = 2
        hookman.run_hooks(event, arg1, arg2)
        assert os.path.exists(marker)
        assert os.path.exists(args_marker)
        with open(args_marker) as f:
            assert f.read().strip() == '{} {}'.format(arg1, arg2)


def test_execute_with_args(hookman):
    pass

if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
