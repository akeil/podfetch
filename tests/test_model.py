#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
test_podfetch
----------------------------------

Tests for `podfetch` module.
'''
import os

import pytest

from podfetch.model import Subscription
from podfetch.exceptions import NoSubscriptionError


def test_load_subscription_from_file(tmpdir):
    load_from = tmpdir.join('the_name')
    load_from.write('\n'.join([
        '[subscription]',
        'url=http://example.com/feed',
    ]))

    sub = Subscription.from_file(str(load_from))

    assert sub.name == 'the_name'
    assert sub.feed_url == 'http://example.com/feed'


def test_nonexisting_raises_error():
    with pytest.raises(NoSubscriptionError):
        sub = Subscription.from_file('does-not-exist')


def test_save(tmpdir):
    sub = Subscription('name', 'the_url')
    sub.save(str(tmpdir))
    filename = os.path.join(str(tmpdir), 'name')
    with open(filename) as f:
        lines = f.readlines()

    assert 'the_url' in ''.join(lines)


if __name__ == '__main__':
    pytest.main(__file__)
