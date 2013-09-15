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
    content_dir = tmpdir.mkdir('content')
    cache_dir = tmpdir.mkdir('cache')
    app = Podfetch(str(config_dir), str(content_dir), str(cache_dir))

    app.update_all = mock.MagicMock()
    app.update_one = mock.MagicMock()
    app.add_subscription = mock.MagicMock()
    app.remove_subscription = mock.MagicMock()
    app.purge_all = mock.MagicMock()
    app.purge_one = mock.MagicMock()

    return app


def with_mock_app(monkeypatch, app):

    def mock_app(cfg):
        return app

    monkeypatch.setattr(main, '_create_app', mock_app)


def test_update(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update']
    main.main(argv=argv)
    mock_app.update_all.assert_called_once_with()


def test_update_one(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update', 'subscription-name']
    main.main(argv=argv)
    mock_app.update_one.assert_called_once_with('subscription-name')


def test_update_many(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    argv = ['update', 'subscription-1', 'subscription-2']
    main.main(argv=argv)
    mock_app.update_one.assert_any_call('subscription-1')
    mock_app.update_one.assert_any_call('subscription-2')


def test_add(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    url = 'http://example.com'
    name = 'new-subscription'
    max_epis = 10
    argv = ['add', url, '--name', name, '--max-episodes', str(max_epis)]
    main.main(argv=argv)
    mock_app.add_subscription.assert_called_once_with(
        url, name=name, max_episodes=max_epis)
    assert mock_app.update_one.called

def test_add_no_update(monkeypatch, mock_app):
    with_mock_app(monkeypatch, mock_app)
    url = 'http://example.com'
    name = 'new-subscription'
    max_epis = 10
    argv = ['add', url, '--name', name, '--max-episodes', str(max_epis),
        '--no-update']
    main.main(argv=argv)
    mock_app.add_subscription.assert_called_once_with(
        url, name=name, max_episodes=max_epis)
    assert not mock_app.update_one.called


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
    default_cache_dir = '/default/cache/dir'
    override_content_dir = '/custom/content_dir'

    # control what's in the default file
    default_config_path = str(tmpdir.join('default.conf'))
    with open(default_config_path, 'w') as f:
        f.write('[default]\n')
        f.write('content_dir = default_content_dir\n')
        f.write('cache_dir = {}\n'.format(default_cache_dir))
    monkeypatch.setattr(main, 'DEFAULT_CONFIG_PATH', default_config_path)

    # the custom config, overrides _one_ setting
    cfg_path = str(tmpdir.join('custom.conf'))
    with open(cfg_path, 'w') as f:
        f.write('[default]\n')
        f.write('content_dir = {}\n'.format(override_content_dir))

    cfg = main.read_config(extra_config_paths=[cfg_path])

    assert cfg.get('default', 'content_dir') == override_content_dir
    assert cfg.get('default', 'cache_dir') == default_cache_dir


def test_remove():
    pass


def test_purge():
    pass


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main(__file__))
