#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Tests for podfetch hooks.
'''
import os
import stat

import pytest

from podfetch.application import HookManager


EVENTS = ('item_downloaded', 'subscription_updated')

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
        import shutil
        shutil.copy(str(hook_file), '/home/akeil/event')

    return hm


def test_hook_discovery(hookman):
    for event in EVENTS:
        hooks = [h for h in hookman.discover_hooks(event)]
        assert len(hooks) == 1


def test_hook_execution(hookman):
    for event in EVENTS:
        marker = os.path.join(
            os.path.dirname(hookman.hook_dirs[event]),
            '{}.done'.format(event)
        )
        assert not os.path.exists(marker)
        hookman.run_hooks(event)
        assert os.path.exists(marker)

if __name__ == '__main__':
    pytest.main(__file__)
