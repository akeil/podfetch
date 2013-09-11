#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_podfetch
----------------------------------

Tests for `podfetch` module.
"""
import pytest

from podfetch.model import Subscription


def test_load_subscription_from_file(tmpdir):
    load_from = tmpdir.join('the_name')
    load_from.write('\n'.join([
        '[default]',
        'url=http://example.com/feed',
    ]))

    sub = Subscription.from_file(str(load_from))

    assert sub.name == 'the_name'
    assert sub.feed_url == 'http://example.com/feed'


if __name__ == '__main__':
    pytest.main(__file__)
