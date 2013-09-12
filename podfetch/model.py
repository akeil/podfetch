#-*- coding: utf-8 -*-
'''
Podfetch Models

Format for subscription files::

    url = http://example.com/feed

'''
import os
import logging
try:
    import configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2

import feedparser

from podfetch.exceptions import NoSubscriptionError


log = logging.getLogger(__name__)


class Subscription(object):

    def __init__(self, name, feed_url):
        self.name = name
        self.feed_url = feed_url

    @property
    def content_dir(self):
        return os.path.join(self.content_root, self.name)

    def update(self):
        feed = feedparser.parse(self.feed_url)
        self.update_episodes(feed)

    def update_episodes(self, feed):
        for entry in feed.entries:
            self.process_one_entry(entry)

    def process_one_entry(self, entry):
        for index, enclosure in enumerate(entry.enclosures):
            if self.is_downloaded(enclosure):
                continue

            dst_path = os.path.join(self.content_root, filename)

    def save(self, dirname):
        '''Save this subscription to an ini-file in the given
        directory. The filename will be the ``name`` of this subscription.

        :param str dirname:
            The directory in which the ini-file is placed.
        '''
        cfg = configparser.ConfigParser()
        cfg.add_section('subscription')
        cfg.set('subscription', 'url', self.feed_url)
        filename = os.path.join(dirname, self.name)
        log.debug('Save Subscription {!r} to {!r}.'.format(self.name, filename))
        with open(filename, 'w') as fp:
            cfg.write(fp)

    @classmethod
    def from_file(cls, path):
        '''Load a ``Subscription`` from its config file.

        :rtype object:
            A Subscription instance.
        :raises:
            NoSubscriptionError if no config file exists.
        '''
        cfg = configparser.ConfigParser()
        read_from = cfg.read(path)
        if not read_from:
            raise NoSubscriptionError(
                'No config file exists at {!r}.'.format(path))

        log.debug('Read subscription from {!r}.'.format(path))
        name = os.path.basename(path)
        feed_url = cfg.get('subscription', 'url')
        return cls(name, feed_url)
