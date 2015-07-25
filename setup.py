#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

from distutils.core import setup
from setuptools.command.test import test as TestCommand


# remember __init__.py
VERSION = '0.4.6.dev2'

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

with open('requirements.txt') as f:
    requires = [line for line in f.readlines()]


class PyTest(TestCommand):

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest
        errcode = pytest.main(self.test_args)
        sys.exit(errcode)

setup(
    name='podfetch',
    version=VERSION,
    description='Fetch audio podcasts and store files locally.',
    long_description=readme + '\n\n' + history,
    author='Alexander Keil',
    author_email='alex@akeil.net',
    url='https://github.com/akeil/podfetch',
    packages=[
        'podfetch',
    ],
    package_dir={'podfetch': 'podfetch'},
    include_package_data=True,
    install_requires=requires,
    cmdclass={'test': PyTest,},
    tests_require=['pytest', 'mock'],
    extras_require={
        'testing': ['pytest', 'mock'],
    },
    license="BSD",
    zip_safe=False,
    keywords='podfetch',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'podfetch = podfetch.main:main',
        ],
    }
)
