#-*- coding: utf-8 -*-
'''
Helpers used by multiple modules.
'''
import logging
import os

LOG = logging.getLogger(__name__)


def require_directory(dirname):
    '''Create the given directory if it does not exist.'''
    try:
        os.makedirs(dirname)
    except FileExistsError:
        pass


def delete_if_exists(filename):
    '''Delete the given filename (absolute path) if it exists.'''
    try:
        os.unlink(filename)
    except FileNotFoundError:
        pass
