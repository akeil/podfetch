#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Tests for filters
'''
import pytest
import os
from datetime import date

from podfetch.application import Filter
from podfetch.application import WildcardFilter
from podfetch.application import PubdateAfter
from podfetch.application import PubdateBefore

def test_basic():
    predicate = Filter()
    for candidate in ['matches', 'anything']:
        assert predicate(candidate)


def test_wildcards():
    predicate = WildcardFilter('*.txt', 'h*o', 'f?o', 'ba[rz]')
    assert predicate('somefile.txt')  # *.txt
    assert not predicate('somefile.ext')
    assert predicate('hello')  # h*o
    assert not predicate('hell')
    assert predicate('foo')  # f?o
    assert not predicate('fooo')
    assert predicate('bar')  # ba[rz]
    assert predicate('baz')  # ba[rz]
    assert not predicate('bax')
    assert not predicate('anything-else')


class _Dummy:

    def __init__(self, y, m, d):
        self.pubdate = [y, m, d]


def test_pubdate_after():
    predicate = PubdateAfter(date(2015, 4, 1))
    assert not predicate(_Dummy(2015, 3, 31))  # before
    assert predicate(_Dummy(2015, 4, 1))  # on
    assert predicate(_Dummy(2015, 4, 2))  # after


def test_pubdate_before():
    predicate = PubdateBefore(date(2015, 4, 1))
    assert predicate(_Dummy(2015, 3, 31))  # before
    assert predicate(_Dummy(2015, 4, 1))  # on
    assert not predicate(_Dummy(2015, 4, 2))  # after


def test_chain_or():
    foo = WildcardFilter('foo')
    bar = WildcardFilter('bar')
    predicate = foo.or_is(bar)
    assert predicate('foo')
    assert predicate('bar')
    assert not predicate('baz')


def test_chain_or_not():
    foo = WildcardFilter('foo')
    bar = WildcardFilter('bar')
    predicate = foo.or_not(bar)
    assert predicate('foo')
    assert not predicate('bar')
    assert predicate('baz')


def test_chain_and():
    foo = WildcardFilter('foo*')
    bar = WildcardFilter('*bar')
    predicate = foo.and_is(bar)
    assert predicate('foobar')
    assert not predicate('foo')
    assert not predicate('bar')


def test_chain_and_not():
    foo = WildcardFilter('foo*')
    bar = WildcardFilter('*bar')
    predicate = foo.and_not(bar)
    assert not predicate('foobar')
    assert predicate('foo')
    assert predicate('foobaz')


def test_invert():
    foo = WildcardFilter('foo')
    not_foo = foo.is_not()
    assert foo('foo')
    assert not not_foo('foo')
