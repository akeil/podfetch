#-*- coding: utf-8 -*-
'''
Podfetch Models

Format for subscription files::

    url = http://example.com/feed

'''
import os
try:
    import configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2

import feedparser


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



    @classmethod
    def from_file(cls, path):
        name = os.path.basename(path)
        cfg = configparser.ConfigParser()
        cfg.read(path)
        feed_url = cfg.get('default', 'url')

        return cls(name, feed_url)
