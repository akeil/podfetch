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
        index_dir, content_dir, cache_dir,
        supported_content=SUPPORTED_CONTENT
    )
    assert sub.feed_url == url  # url unchanged, as set

    sub.save()  # should not fail

    filename = os.path.join(sub.config_dir, sub.name)
    reloaded = Subscription.from_file(filename, index_dir, content_dir, cache_dir)
    assert reloaded.feed_url == url


def DISABLED_test_load_subscription_from_file(tmpdir):
    '''Load a subscription from its config file.'''
    load_from = tmpdir.join('the_name')
    load_from.write('\n'.join([
        '[subscription]',
        'url=http://example.com/feed',
        'max_episodes = 30',
        'filename_template = template',
        'title = the_title',
        'content_dir = subscription_content_dir',
        'enabled = False',
    ]))

    sub = Subscription.from_file(
        str(load_from), 'index_dir', 'content_dir', 'cache_dir'
    )

    assert sub.name == 'the_name'
    assert sub.feed_url == 'http://example.com/feed'
    assert sub.title == 'the_title'
    assert sub.max_episodes == 30
    assert sub.filename_template == 'template'
    assert sub.content_dir == 'subscription_content_dir'
    assert sub.enabled == False


def DISABLED_test_load_nonexisting_raises_error():
    '''Trying to load a Subscription from a non-existing config file
    must raise a NoSubscriptionError.'''
    with pytest.raises(NoSubscriptionError):
        sub = Subscription.from_file(
            'does-not-exist',
            'index_dir', 'content_dir', 'cache_dir'
        )


def DISABLED_test_load_invalid_raises_error(tmpdir):
    '''Loading a subscription from a file that is not in ini-format.'''
    invalid_file = tmpdir.join('invalid_file')
    invalid_file.write('something')
    with pytest.raises(NoSubscriptionError):
        Subscription.from_file(
            str(invalid_file),
            'index_dir', 'content_dir', 'cache_dir'
        )


def DISABLED_test_load_empty_raises_error(tmpdir):
    '''Loading a subscription from an empty file.'''
    empty_file = tmpdir.join('invalid_file')
    empty_file.write('')
    with pytest.raises(NoSubscriptionError):
        Subscription.from_file(
            str(empty_file),
            'index_dir', 'content_dir', 'cache_dir'
        )


def DISABLED_test_load_missing_url(tmpdir):
    '''Loading a subscription from ini file with required fields missing.'''
    invalid_file = tmpdir.join('invalid_file')
    invalid_file.write('[subscription]\nfield = value')
    with pytest.raises(NoSubscriptionError):
        Subscription.from_file(
            str(invalid_file),
            'index_dir', 'content_dir', 'cache_dir'
        )


def DISABLED_test_delete(sub, monkeypatch):
    '''Assert that after a subscription is deleted,
    content, index file and cached header files are deleted.'''
    with_dummy_feed(monkeypatch, return_etag='x', return_modified='x')
    with_mock_download(monkeypatch)

    sub.update()
    assert len(os.listdir(sub.content_dir)) > 0
    assert os.path.isfile(sub._cache_path('etag'))
    assert os.path.isfile(sub._cache_path('modified'))
    assert os.path.isfile(sub.index_file)

    sub.delete()
    assert not os.path.exists(sub.content_dir)
    assert not os.path.exists(sub._cache_path('etag'))
    assert not os.path.exists(sub._cache_path('modified'))
    assert not os.path.exists(sub.index_file)


def DISABLED_test_save_and_load_index(sub):
    '''Save the index of downloaded enclosures to disk and load it.'''
    for index in range(5):
        sub.episodes.append(
            Episode(sub, 'id.{}'.format(index), SUPPORTED_CONTENT)
        )

    sub._save_index()

    assert os.path.isfile(sub.index_file)

    reloaded_sub = Subscription('name', 'url',
        'index_dir', 'content_dir', sub.cache_dir)
    reloaded_sub._load_index()
    for index in range(5):
        id_ = 'id.{}'.format(index)
        episode = sub._episode_for_id(id_)
        assert episode is not None

    assert sub._episode_for_id('bogus') is None


def DISABLED_test_save_index_create_directory(sub, tmpdir):
    '''Assert that the directory for the index file is created
    if it does not exist.'''
    sub.index_dir = str(tmpdir.join('does-not-exist'))
    sub.name = 'name'
    sub.episodes.append(Episode(sub, 'id', SUPPORTED_CONTENT))
    sub._save_index()
    assert os.path.isfile(os.path.join(sub.index_dir, 'name.json'))


def DISABLED_test_write_read_cache(sub):
    '''Write to cache and retrieve correctly.'''
    data = {
        'foo': 'xyz',
        'bar': 'abc',
        'None': None,
    }
    for k, v in data.items():
        sub._cache_put(k, v)

    for k in data.keys():
        assert sub._cache_get(k) == data[k]


def DISABLED_test_write_read_cache_empty(sub):
    '''Reading non-existent key from cache should be None.'''
    assert sub._cache_get('does-not-exist') is None
