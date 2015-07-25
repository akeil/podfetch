#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
test_main
---------

Tests for `main` module (command line interface).
'''
try:
    import configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2
import argparse

import pytest
import mock
from mock import call
import feedparser

from podfetch.application import Podfetch
from podfetch import main
from podfetch import model

from tests import common


@pytest.fixture(scope='function')
def mock_app(tmpdir):
    config_dir = tmpdir.mkdir('config')
    index_dir = tmpdir.mkdir('index')
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    app = Podfetch(
        str(config_dir), str(index_dir),
        str(content_dir), str(cache_dir)
    )

    app.update = mock.MagicMock()
    app.add_subscription = mock.MagicMock()
    app.remove_subscription = mock.MagicMock()
    app.subscription_for_name = mock.MagicMock()
    app.purge_all = mock.MagicMock()
    app.purge_one = mock.MagicMock()

    return app


def with_mock_app(monkeypatch, app):

    def mock_app(cfg):
        return app

    monkeypatch.setattr(main, '_create_app', mock_app)


# update ---------------------------------------------------------------------


def test_update(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update']
    main.main(argv=argv)
    mock_app.update.assert_called_once()


def test_forced_update(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update', '--force']
    main.main(argv=argv)
    mock_app.update.assert_called_once()


def test_update_one(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update', 'subscription-name']
    main.main(argv=argv)
    mock_app.update.assert_called_once()


def test_update_many(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update', 'subscription-1', 'subscription-2']
    main.main(argv=argv)
    mock_app.update.assert_called_once()


# add ------------------------------------------------------------------------


def test_add(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    url = 'http://example.com'
    name = 'new-subscription'
    content_dir = 'my-content-dir'
    max_epis = 10
    argv = [
        'add', url,
        '--name', name,
        '--directory', content_dir,
        '--max-episodes', str(max_epis)
    ]
    main.main(argv=argv)
    mock_app.add_subscription.assert_called_once_with(
        url, name=name,
        content_dir=content_dir,
        filename_template=None,
        max_episodes=max_epis
    )
    assert mock_app.update.called


def test_add_no_update(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    url = 'http://example.com'
    name = 'new-subscription'
    max_epis = 10
    argv = ['add', url, '--name', name, '--max-episodes', str(max_epis),
        '--no-update']
    main.main(argv=argv)
    mock_app.add_subscription.assert_called_once_with(
        url, name=name,
        content_dir=None,
        filename_template=None,
        max_episodes=max_epis)
    assert not mock_app.update.called


# remove ---------------------------------------------------------------------


def test_remove(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    name = 'my-subscription'
    argv = ['del', name]
    main.main(argv=argv)
    mock_app.remove_subscription.assert_called_once_with(
        name,
        delete_content=False
    )


def test_remove_content(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    name = 'my-subscription'
    argv = ['del', name, '--episodes']
    main.main(argv=argv)
    mock_app.remove_subscription.assert_called_once_with(
        name,
        delete_content=True
    )


# ls -------------------------------------------------------------------------


def test_ls():
    pass


# purge ----------------------------------------------------------------------


def test_purge():
    pass


# config ---------------------------------------------------------------------


def test_custom_config(monkeypatch):
    monkeypatch.setattr(main, 'read_config', mock.MagicMock())
    cfg_path = '/custom/config/file'
    argv = ['--config', cfg_path, 'update']

    main.main(argv=argv)

    main.read_config.assert_called_once()
    expected_call = call(extra_config_paths=[cfg_path])
    assert expected_call in main.read_config.mock_calls


def test_read_cfg(tmpdir, monkeypatch):
    '''Assert that a custom config (partially) overrides the default.'''
    system_wide_template = 'system-wide-template'
    default_cache_dir = '/default/cache/dir'
    override_content_dir = '/custom/content_dir'

    # control what's in the default files

    system_config_path = str(tmpdir.join('system.conf'))
    with open(system_config_path, 'w') as f:
        f.write('[default]\n')
        f.write('filename_template = {}\n'.format(system_wide_template))
        f.write('cache_dir = system-wide-cache-dir\n')
    monkeypatch.setattr(main, 'SYSTEM_CONFIG_PATH', system_config_path)

    default_config_path = str(tmpdir.join('default.conf'))
    with open(default_config_path, 'w') as f:
        f.write('[default]\n')
        f.write('content_dir = default_content_dir\n')
        f.write('cache_dir = {}\n'.format(default_cache_dir))
    monkeypatch.setattr(main, 'DEFAULT_USER_CONFIG_PATH', default_config_path)

    # the custom config, overrides _one_ setting
    cfg_path = str(tmpdir.join('custom.conf'))
    with open(cfg_path, 'w') as f:
        f.write('[default]\n')
        f.write('content_dir = {}\n'.format(override_content_dir))

    cfg = main.read_config(extra_config_paths=[cfg_path])

    assert cfg.get('default', 'content_dir') == override_content_dir
    assert cfg.get('default', 'cache_dir') == default_cache_dir
    assert cfg.get('default', 'filename_template') == system_wide_template


# helpers ---------------------------------------------------------------------

from datetime import date, timedelta
def test_parse_datearg():
    t = date.today()
    cases = (
        ('t', t),
        ('today', t),

        ('y', t - timedelta(days=1)),
        ('yy', t - timedelta(days=2)),
        ('yester', t - timedelta(days=1)),
        ('yesterday', t - timedelta(days=1)),

        ('d', t - timedelta(days=1)),
        ('day', t - timedelta(days=1)),
        ('days', t - timedelta(days=1)),

        ('2d', t - timedelta(days=2)),
        ('2day', t - timedelta(days=2)),
        ('2days', t - timedelta(days=2)),

        ('3 days', t - timedelta(days=3)),  # with space
        ('10 days', t - timedelta(days=10)),  # 2-digits
        ('100 days', t - timedelta(days=100)),  # more than one month

        ('w', t - timedelta(weeks=1)),
        ('week', t - timedelta(weeks=1)),
        ('weeks', t - timedelta(weeks=1)),

        ('2w', t - timedelta(weeks=2)),
        ('2week', t - timedelta(weeks=2)),
        ('2weeks', t - timedelta(weeks=2)),

        ('3 weeks', t - timedelta(weeks=3)),  # with space
        ('10 weeks', t - timedelta(weeks=10)),  # 2-digits

        ('2015-05-13', date(2015, 5, 13)),
        ('20150513', date(2015, 5, 13)),

    )
    for argstr, expected in cases:
        assert main.datearg(argstr) == expected

if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
