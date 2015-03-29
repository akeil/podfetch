#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Tests for filters
'''
import pytest
import os

from podfetch.application import Filter
from podfetch.application import WildcardFilter


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
