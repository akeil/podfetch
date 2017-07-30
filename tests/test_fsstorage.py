#-*- coding: utf-8 -*-
'''
[Module Documentation here]
'''
import logging


LOG = logging.getLogger(__name__)


# TODO: fixtures
# - sub as in test_model


def DISABLED_test_save(tmpdir, sub):
    sub.max_episodes = 123
    sub.filename_template = 'template'
    sub.title = 'subscription-title'
    sub.content_dir = 'my-content-dir'
    sub.save()
    filename = os.path.join(sub.config_dir, 'name')
    with open(filename) as f:
        lines = f.readlines()

    text = ''.join(lines)
    assert 'http://example.com' in text
    assert '123' in text
    assert 'template' in text
    assert 'subscription-title' in text
    assert 'my-content-dir' in text
    assert 'yes' in text  # from enabled=True


def DISABLED_test_url_escape(tmpdir):
    '''url encodes character (e.g. "%20") conflict with ConfigParser's interpolation
    syntax.'''
    config_dir = str(tmpdir.mkdir('config'))
    index_dir = str(tmpdir.mkdir('index'))
    content_dir = str(tmpdir.mkdir('content_dir'))
    cache_dir = str(tmpdir.mkdir('cache_dir'))

    url = 'http://example.com/foo%20bar'
    sub = Subscription('name', url,
        config_dir, index_dir, content_dir, cache_dir,
        supported_content=SUPPORTED_CONTENT
    )
    assert sub.feed_url == url  # url unchanged, as set

    sub.save()  # should not fail

    filename = os.path.join(sub.config_dir, sub.name)
    reloaded = Subscription.from_file(filename, index_dir, content_dir, cache_dir)
    assert reloaded.feed_url == url
