#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
Command line interface for podfetch
'''
import argparse
import hashlib
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from datetime import timedelta
from logging import handlers
from pkg_resources import resource_stream
from textwrap import wrap

try:
    import configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2

import podfetch
from podfetch import application
import podfetch.daemon
from podfetch.player import Player
from podfetch.predicate import Filter
from podfetch.predicate import WildcardFilter
from podfetch.predicate import NameFilter
from podfetch.exceptions import NoSubscriptionError
from podfetch.exceptions import UserError
from podfetch.model import Subscription


PROG_NAME = 'podfetch'
VERSION = podfetch.__version__
DESCRIPTION = 'Fetch podcasts and store files locally'
AUTHOR = podfetch.__author__
AUTHOR_MAIL = podfetch.__email__

# logging config
CONSOLE_FMT = '%(levelname)s: %(message)s'
SYSLOG_FMT = '%(levelname)s [%(name)s]: %(message)s'
LOGFILE_FMT = '%(asctime)s %(levelname)s [%(name)s]: %(message)s'
DEFAULT_LOG_LEVEL = 'warning'

CFG_DEFAULT_SECTION = 'podfetch'
SYSTEM_CONFIG_PATH = '/etc/podfetch.conf'
DEFAULT_USER_CONFIG_PATH = os.path.expanduser(
    '~/.config/podfetch/podfetch.conf')

EXIT_OK = 0
EXIT_ERROR = 1


log = logging.getLogger(PROG_NAME)


def main(argv=None):
    '''Main entry point as defined in setup.py.

    Sets up the argument parser,
    reads configuration,
    configures logging
    and runs the program by invoking :function:`run()`,
    passing the parsed arguments
    and configuration.

    :param list argv:
        Command line arguments.
        If *None* (the default), ``sys.argv`` is used.
    :rtype int:
        Returns an exit code (0=Success, 1=Error).
    '''
    options = read_config()
    parser = setup_argparser()
    argv = argv or sys.argv[1:]
    parser.parse_args(args=argv, namespace=options)
    configure_logging(options)

    log.debug('Commandline: {}'.format(' '.join(argv)))
    log.debug('Options: {}'.format(options))

    try:
        rv = run(options)
    except KeyboardInterrupt:
        log.info('Keyboard Interrupt.')
        raise
    except Exception as e:
        log.error(e)
        log.debug(e, exc_info=True)
        rv = EXIT_ERROR
    finally:
        # TODO perform cleanup
        pass

    rv = rv or EXIT_OK  # converts None|False -> 0
    log.debug('Exit with return code: {}.'.format(rv))
    return rv


def run(options):
    '''Run podfetch with the given options.

    :param object options:
        The ``Namespace`` with parsed command line arguments
        and config settings.
    :rtype int:
        The *Return Code* of the application-run.
    '''
    app = _create_app(options)
    try:
        func = options.func
    except AttributeError:
        raise UserError('No subcommand specified.')
    return func(app, options)


def _create_app(options):
    '''set up the application instance using the given config

    :param Namspace options:
        A ``Namsepace`` instance containing the configuration values
        to be used.
    :rtype object:
        An :class:`application.Podfetch` instance.
    '''
    return application.Podfetch(
        options.config_dir,
        options.index_dir,
        options.content_dir,
        options.cache_dir,
        filename_template=options.filename_template,
        update_threads=options.update_threads,
        ignore=options.ignore,
        supported_content=options.content_types
    )


def setup_argparser():
    '''Create an configure the ``ArgumentParser`` used to interpret
    command line arguments.

    :rtype object ArgumentParser:
        The configured ArgumentParser instance.
    '''
    parser = argparse.ArgumentParser(
        prog=PROG_NAME,
        description=DESCRIPTION,
        epilog='{p} Version {v} -- {author} <{mail}>'.format(
            p=PROG_NAME, v=VERSION,
            author=AUTHOR, mail=AUTHOR_MAIL
        )
    )
    parser.add_argument(
        '--version',
        action='version',
        version='{p} {v}'.format(p=PROG_NAME, v=VERSION),
        help='Print version number and exit'
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Increase console output',
    )
    common.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Write nothing to stdout',
    )
    common.add_argument(
        '-l', '--logfile',
        #type=_path,  cannot use because of 'syslog'
        help=('Write logs to the specified file. Use LOGFILE="syslog"'
            ' to write logging output to syslog.')
    )

    loglevels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL,
    }

    class LogLevelAction(argparse.Action):

        def __call__(self, parser, namespace, values, option_string=None):
            level = loglevels[values]
            setattr(namespace, self.dest, level)

    common.add_argument(
        '--log-level',
        action=LogLevelAction,
        default=logging.WARNING,
        choices=loglevels.keys(),
        help=('Controls the log-level for LOGFILE;'
            ' defaults to {default}').format(default=DEFAULT_LOG_LEVEL),
    )

    # subparsers for individual commands
    subs = parser.add_subparsers()
    _update(subs, common)
    _list(subs, common)
    _add(subs, common)
    _edit(subs, common)
    _show(subs, common)
    _del(subs, common)
    _purge(subs, common)
    _play(subs, common)
    _daemon(subs, common)

    return parser


def _path(argstr):
    path = os.path.expanduser(argstr)
    path = os.path.normpath(path)
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    return path


DATE_PATTERNS = (
    (
        '^(y|yester|yesterday)$',
        lambda g: date.today() - timedelta(days=1)
    ),
    (
        '^yy$',
        lambda g: date.today() - timedelta(days=2)
    ),
    (
        '^(t|today)$',
        lambda g: date.today()
    ),
    (
        '^([0-9]+)?\s?(d|day|days)$',
        lambda g: date.today() - timedelta(days=int(g.group(1) or 1))
    ),
    (
        '^([0-9]+)?\s?(w|week|weeks)$',
        lambda g: date.today() - timedelta(weeks=int(g.group(1) or 1))
    ),
    (
        '^([0-9]{4})-?([0-9]{2})-?([0-9]{2})$',
        lambda g: date(int(g.group(1)), int(g.group(2)), int(g.group(3)))
    )
)


def datearg(s):
    refdate = None
    for pattern, factory in DATE_PATTERNS:
        m = re.match(pattern, s)
        if m:
            refdate = factory(m)  # may raise ValueError
    if refdate is None:
        raise argparse.ArgumentTypeError
    else:
        return refdate


def _update(subs, common):
    fetch = subs.add_parser(
        'update',
        parents=[common,],
        help='Update subscriptions'
    )

    fetch.add_argument(
        'patterns',
        nargs='*',
        metavar='NAME',
        help=('The names of the subscriptions to be updated.'
            ' If no name is given, all subscriptions are updated.'),
    )

    fetch.add_argument(
        '--force',
        action='store_true',
        help=('Force update even if feed is not modified.'
            ' Re-downloads episodes and overwrites existing files.'),
    )

    def do_update(app, args):
        return app.update(
            predicate=WildcardFilter(*args.patterns),
            force=args.force
        )

    fetch.set_defaults(func=do_update)


def _list(subs, common):
    ls = subs.add_parser(
        'ls',
        parents=[common,],
        help='List Episodes by date'
    )

    ls.add_argument(
        'patterns',
        metavar='NAME',
        nargs='*',
        help=('Names of subscriptions from which episodes are listed. If'
            ' NAME(S) are given, episodes from these podcasts are shown.'
            ' Allows wildcards.'
            ' If no name is given list episodes from all podcasts.'),
    )

    ls.add_argument(
        '--since', '-s',
        metavar='DATE',
        type=datearg,
        help=('Show only episodes downloaded SINCE the given date;'
            ' implies the -a option')
    )

    ls.add_argument(
        '--until', '-u',
        metavar='DATE',
        type=datearg,
        help=('Show only episodes downloaded UNTIL the given date;'
            ' implies the -a option')
    )

    ls.add_argument(
        '--path', '-p',
        action='store_true',
        help='Print paths instead of titles',
    )

    n_control = ls.add_mutually_exclusive_group()
    n_control.add_argument(
        '--newest', '-n',
        metavar='N',
        type=int,
        help=('Control the number of episodes shown;'
            ' excludes the --all option'),
    )
    n_control.add_argument(
        '--all', '-a',
        action='store_true',
        help=('Do not limit the number of episodes shown;'
            ' excludes the --newest option'),
    )

    def do_ls(app, options):
        out = sys.stdout

        if not options.path:
            header = 'Podfetch Episodes'
            out.write('{}\n'.format(header))
            out.write('{}\n'.format('-' * len(header)))

        if options.since or options.until:
            limit = None
        else:
            limit = options.newest or options.ls_limit

        episodes = app.list_episodes(*options.patterns,
            since=options.since,
            until=options.until,
            limit=limit)

        # write episodes
        lastdate = None
        for episode in episodes:
            curdate = '{:0>4}-{:0>2}-{:0>2}'.format(
                episode.pubdate[0],
                episode.pubdate[1],
                episode.pubdate[2],
            )
            if options.path:
                for __, __, local in episode.files:
                    out.write(local)
                    out.write('\n')
            else:
                if lastdate is None or lastdate != curdate:
                    out.write('{}:\n'.format(curdate))
                    lastdate = curdate

                out.write('\n     '.join(
                    wrap('[{}] {}'.format(
                        episode.subscription.title,
                        episode.title,
                    ),
                    70,
                    initial_indent=' - ',
                )))
                out.write('\n')

        return EXIT_OK

    ls.set_defaults(func=do_ls)


def _add(subs, common):
    add = subs.add_parser(
        'add',
        parents=[common,],
        help='Add a new subscription'
    )

    add.add_argument(
        'url',
        help='The feed URL'
    )
    add.add_argument(
        '-n', '--name',
        help=('A name for the subscription;'
            ' if none is given, the name will be derived from the URL'),
    )
    add.add_argument(
        '-m', '--max-episodes',
        type=int,
        default=-1,
        help=('The maximum number of downloaded episodes to keep;'
            ' default is "-1" (unlimited)'),
    )
    add.add_argument(
        '-t', '--template',
        help=('Filename template for this subscription,'
            ' overrides application default.'
            'Variables: {title}, {subscription_name}, {pubdate}, {id}, ...'
            ' see README for complete list.'),
    )
    add.add_argument(
        '-d', '--directory',
        help=('Download episodes to the given directory.'
            ' If omitted, the application default and a '
            ' subdirectory with the subscription name.'
        )
    )
    add.add_argument(
        '--no-update',
        action='store_true',
        help='Do not immediately fetch content for the new subscription',
    )

    def do_add(app, args):
        sub = app.add_subscription(args.url,
            name=args.name,
            content_dir=args.directory,
            max_episodes=args.max_episodes,
            filename_template=args.template,
        )
        if not args.no_update:
            app.update(predicate=NameFilter(sub.name))
        return 0

    add.set_defaults(func=do_add)


def _show(subs, common):
    show = subs.add_parser(
        'show',
        parents=[common,],
        help='View subscription details',
    )
    show.add_argument(
        'subscription_names',
        metavar='NAME',
        nargs='*',
        help=('Name(s) of subscriptions to show;'
            ' if not given, show all'),
    )

    out = sys.stdout

    def render(s):
        out.write('{:<15}: {}\n'.format('Title', s.title))
        out.write('{:<15}: {}\n'.format('URL', s.feed_url))
        out.write('{:<15}: {}\n'.format('Directory', s.content_dir))
        out.write('{:<15}: {}\n'.format(
            'Max Episodes',
            s.max_episodes if s.max_episodes > 0 else 'unlimited'

        ))
        out.write('{:<15}: {}\n'.format(
            'Template',
            s.filename_template or '[default] {}'.format(s.app_filename_template)
        ))
        out.write('{:<15}: {}/{}\n'.format('Config File', s.config_dir, s.name))
        out.write('\n')

    def do_show(app, args):
        if args.subscription_names:
            for name in args.subscription_names:
                try:
                    render(app.subscription_for_name(name))
                except NoSubscriptionError:
                    log.warning('No subscription named {!r}.\n'.format(name))
        else:
            for subscription in app.iter_subscriptions():
                render(subscription)

        return EXIT_OK

    show.set_defaults(func=do_show)


def _del(subs, common):
    dele = subs.add_parser(
        'del',
        parents=[common,],
        help='Delete subscriptions',
    )
    dele.add_argument(
        'subscription_names',
        metavar='NAME',
        nargs='+',
        help='Name(s) of subscription(s) to delete'
    )
    dele.add_argument(
        '--episodes', '-e',
        action='store_true',
        help=('Also delete downloaded episodes;'
            ' default is to keep episodes'),
    )

    def do_dele(app, args):
        for name in args.subscription_names:
            try:
                app.remove_subscription(name, delete_content=args.episodes)
            except NoSubscriptionError:
                log.warning('No subscription named {!r}.\n'.format(name))

        return EXIT_OK

    dele.set_defaults(func=do_dele)


def _purge(subs, common):
    purge = subs.add_parser(
        'purge',
        parents=[common,],
        help='Remove old downloaded episodes'
    )
    purge.add_argument(
        'subscription_name',
        nargs='*',
        help=('The names of the subscriptions for which old files'
            ' should be removed. If no name is given, all subscriptions'
            ' are purged.'),
    )
    purge.add_argument(
        '-s', '--simulate',
        action='store_true',
        help='List filenames, do not delete'
    )

    def do_purge(app, args):
        result = []
        if not args.subscription_name:
            result += app.purge_all(simulate=args.simulate)
        else:
            for name in args.subscription_name:
                result += app.purge_one(
                    name, simulate=args.simulate
                )

        log.info('Purged {} files...'.format(len(result)))
        for filename in result:
            log.info('Purged {!r}'.format(filename))
        if result and args.simulate:
            log.warning('Simulation - no files were deleted.')

    purge.set_defaults(func=do_purge)


def _edit(subs, common):
    edit = subs.add_parser(
        'edit',
        parents=[common,],
        help='Edit subscription properties'
    )

    edit.add_argument(
        'subscription_name',
        metavar='NAME',
        help='Name of the subscription to edit'
    )

    edit.add_argument(
        '-n', '--name',
        help='Set a new name'
    )

    edit.add_argument(
        '-u', '--url',
        help='Set a new source URL'
    )

    edit.add_argument(
        '-t', '--title',
        help='Set a new display title'
    )

    edit.add_argument(
        '-k', '--keep',
        type=int,
        help='Set the number of episodes to keep'
    )

    edit.add_argument(
        '-f', '--filename',
        help='Set a new filename template'
    )

    edit.add_argument(
        '-d', '--directory',
        help='base directory to store downloaded episodes'
    )

    enabled_group = edit.add_mutually_exclusive_group()
    enabled_group.add_argument(
        '--enable',
        action='store_true',
        help='Enable the feed'
    )

    enabled_group.add_argument(
        '--disable',
        action='store_true',
        help='Disable the feed'
    )

    edit.add_argument(
        '--no-move',
        action='store_false',
        dest='move_files',
        help='Do not rename downloaded episode files'
    )

    def do_edit(app, args):

        # test if we want to open the editor
        # or just set fields
        open_editor = (
                args.name is None
            and args.url is None
            and args.title is None
            and args.keep is None
            and args.filename is None
            and args.directory is None
            and not args.enable
            and not args.disable
        )
        log.debug('open in editor {}'.format(open_editor))

        if open_editor:
            _editor(app, args)
        else:
            app.edit(args.subscription_name,
                name=args.name,
                url=args.url,
                title=args.title,
                max_episodes=args.keep,
                filename_template=args.filename,
                enabled=args.enable or not args.disable,
                move_files=args.move_files
            )

    edit.set_defaults(func=do_edit)


def _play(subs, common):
    play = subs.add_parser(
        'play',
        parents=[common, ],
        help='Play episodes'
    )

    play.add_argument(
        'subscription_name',
        metavar='NAME',
        nargs='?',
        default='*',
        help='Optional name of the subscription to choose from'
    )

    play.add_argument(
        '--wait',
        action='store_true',
        help='Wait for the player to finish.'
    )

    out = sys.stdout

    def choose_episode(app, options):
        limit = options.ls_limit
        names = [options.subscription_name]
        episodes = app.list_episodes(*names, limit=limit)

        if not episodes:
            out.write('No episodes found for {!r}.\n'.format(options.subscription_name))
            return

        out.write('Select Episode\n')
        for index, episode in enumerate(episodes):
            number = index + 1
            out.write('{: >2d} | '.format(number))
            out.write('{: <16s} | {}'.format(
                episode.subscription.title[:16],
                episode.title[:55]
            ))
            out.write('\n')

        return capture_episode(episodes)

    def capture_episode(episodes):
        selected = input('Play episode <number>: ')
        if not selected:
            out.write('No episode selected, exit.\n')
            return

        try:
            selected_index = int(selected) - 1
            return episodes[selected_index]
        except (ValueError, IndexError):
            out.write('Error: Invalid episode number {!r}'.format(selected))
            out.write('\n')
            return capture_episode(episodes)

    def do_play(app, options):
        episode = choose_episode(app, options)
        if not episode:
            return EXIT_OK

        out.write('*** Playing ***\n')
        out.write('Podcast:   {}\n'.format(episode.subscription.title))
        out.write('Episode:   {}\n'.format(episode.title))
        if episode.published:
            out.write('Published: {}\n'.format(episode.published.strftime('%Y-%m-%d')))

        player = Player(app, options)
        player.play(episode, wait=options.wait)
        return EXIT_OK

    play.set_defaults(func=do_play)


def _daemon(subs, common):
    daemon = subs.add_parser(
        'daemon',
        parents=[common,],
        help='Start podfetch as a daemon'
    )

    def do_daemon(app, options):
        return podfetch.daemon.run(app, options)

    daemon.set_defaults(func=do_daemon)


all_keys = [
 'url', 'title', 'enabled',
 'filename_template', 'content_dir', 'max_episodes'
]

comments = {
    'url': (
        'The source URL for this podcast.',
        'Example: http://example.com/podcast',
    ),
    'max_episodes': (
        'Maximum number of episodes to keep.',
        'Relevant when using the `purge` command.',
        'Use `-1` to keep an unlimited number of files.',
    ),
    'filename_template': (
        'Template for filenames of downloaded episodes.',
        'Template parameters:',
        '  subscription_name  name of the parent subscription',
        '  pub_date           publication date, yyyy-mm-dd',
        '  year               year from pub_date',
        '  month              month from pub_date',
        '  day                day from pub_date',
        '  hour               hour from pub_date',
        '  minute             minute from pub_date',
        '  second             second from pub_date',
        '  title              episode title',
        '  feed_title         title of the parent feed',
        '  id                 episode id',
        '  ext                file extension, optional',
        '  kind               one of video or audio',
    ),
    'content_dir': (
        'The directory where downloaded episodes are stored.',
        'Default is to use the directory from app config.',
        'from application config.'
    ),
    'title': (
        'A Display Title for the subscription.',
    ),
    'enabled': (
        'If set to `no`, no new episodes will be downloaded.',
    ),
}


def _checksum(path):
    hash = hashlib.md5()
    with open(path, 'rb') as f:
        hash.update(f.read())
    return hash.hexdigest()


def _read_props(path):
    '''read all lines that contain values which are already set.'''
    values = {}
    with open(path) as f:
        for line in f.readlines():
            # either "key = value"  or "key: value"
            key = line.split('=')[0].split(':')[0].strip()
            values[key] = line

    return values


def _write_props(path, values):
    '''Write an ini file with subscription properties to the given path.
    In addition to the given values, write ...
    - all keys
    - in fixed order
    - comments for each key
    '''
    with open(path, 'w') as f:
        f.write('# Subscription properties')
        f.write('\n')
        f.write('[subscription]')
        f.write('\n')

        for key in all_keys:
            f.write('\n')
            f.write('# {s}'.format(s='-' * 77))
            f.write('\n')
            if key in comments:
                for comment in comments[key]:
                    f.write('# {s}'.format(s=comment))
                    f.write('\n')
                f.write('\n')

            if key in values:
                f.write(values[key])
            else:
                f.write('# {k} = '.format(k=key))
                f.write('\n')

        f.write('\n')


def _open_in_editor(path):
    before = _checksum(path)
    # TODO: read editor from cfg
    for candidate in ('EDITOR', 'VISUAL'):
        editor = os.environ.get(candidate)
        if editor:
            break

    if not editor:
        raise ValueError('No editor found')
    else:
        log.debug('Open {p!r} with {e!r}'.format(p=path, e=editor))
        subprocess.check_call([editor, path] )
    after = _checksum(path)
    log.debug('Checksum before: {c!r}'.format(c=before))
    log.debug('Checksum after:  {c!r}'.format(c=after))
    return before != after


def _editor(app, args):
    '''Write properties of the feed to a temporary file,
    open that file in $EDITOR and apply changes made in the editor.'''
    sub = app.subscription_for_name(args.subscription_name)
    unused, tmp = tempfile.mkstemp()

    try:
        # TODO: use FileSystemStorage and save to temp
        sub.save(path=tmp)
        _write_props(tmp, _read_props(tmp))
        changes_made = _open_in_editor(tmp)
        if changes_made:
            log.info('Apply changes')
            # TODO: use FileSystemStorage and load from temp
            changed = Subscription.from_file(
                tmp,
                sub.index_dir,
                app.content_dir,
                sub.cache_dir,
            )
            app.edit(sub.name,
                url = changed.feed_url or None,
                title = changed.title or None,
                max_episodes=changed.max_episodes or None,
                filename_template=changed.filename_template or None,
                content_dir=changed._content_dir or None,
                enabled=changed.enabled,
                move_files=args.move_files
            )
        else:
            log.warning('No changes were made.')

    finally:
        os.unlink(tmp)


def _boolean(strval):
    if strval is None:
        return False
    elif strval.lower() in ('1', 'y', 'yes', 'true', 'on'):
        return True
    elif strval.lower() in ('0', 'n', 'no', 'false', 'off'):
        return False
    else:
        return bool(strval)


def _whitespace_list(strval):
    if strval is None:
        return []
    else:
        return strval.split()


def _whitespace_dict(strval):
    if strval is None:
        return {}
    else:
        return {
            k.strip(): v.strip() for k, v in [
                i.split() for i in strval.splitlines()
            ]
        }


CFG_TYPES = {
    CFG_DEFAULT_SECTION: {
        'verbose': _boolean,
        'quiet': _boolean,
        'update_threads': int,
        'config_dir': _path,
        'index_dir': _path,
        'content_dir': _path,
        'cache_dir': _path,
        'ignore': _whitespace_list,
        'content_types': _whitespace_dict,
        'ls_limit': int,
    },
    'daemon': {
        'update_interval': int,
        'pidfile': _path,
    },
    'player': {
        'command': str,
    },
}


def read_config():
    '''Read configuration from the ``DEFAULT_CONFIG_PATH and
    optionally supplied ``extra_config_paths``.

    :param bool require:
        If *True*, raise an error if no config file was found.
        Defaults to *False*.
    :rtype ConfigParser:
        A ``ConfigParser`` with the values read from the
        configuration file(s).
    :raises:
        ``ValueError`` is raised if ``require`` is *True*
        and if no config-file was found.
    '''
    root = argparse.Namespace()
    cfg = configparser.ConfigParser()

    # default config from package
    try:  # py 3.x
        cfg.readfp(io.TextIOWrapper(
            resource_stream('podfetch', 'default.conf'))
        )
    except AttributeError:
        # py 2.x - return of resource_stream does not support `readable()`
        #          which is required by TextIOWrapper.
        #          Thus, read all bytes from it an wrap into BytesIO
        cfg.readfp(io.TextIOWrapper(
            io.BytesIO(
                resource_stream('podfetch', 'default.conf').read()
            )
        ))

    # system + user config from file(s)
    paths = [SYSTEM_CONFIG_PATH, DEFAULT_USER_CONFIG_PATH,]
    read_from = cfg.read(paths)

    def ns(name):
        rv = None
        if name == CFG_DEFAULT_SECTION:
            rv = root
        else:
            try:
                rv = getattr(root, name)
            except AttributeError:
                rv = argparse.Namespace()
                setattr(root, name, rv)
        return rv

    # transfer config values to namespace(s)
    identity = lambda x: x
    for section in cfg.sections():
        for option in cfg.options(section):
            value = cfg.get(section, option)
            try:
                conv = CFG_TYPES.get(section, {}).get(option, identity)
                setattr(ns(section), option, conv(value))
            except (TypeError, ValueError) as e:
                log.error('Failed to coerce value {v!r} for {s}.{o}'.format(
                    v=value,
                    s=section,
                    o=option
                ))
                log.exception(e)

    return root


def configure_logging(options):
    '''Configure log-level and logging handlers.

    :param Namespace options:
        a ``Namespace`` instance with the following options:

        :option bool quiet:
            If *True*, do not configure a console handler.
            Defaults to *False*.
        :option bool verbose:
            If *True*, set the log-level for the console handler
            to DEBUG. Has no effect if ``quiet`` is *True*.
            Defaults to *False*.
        :option str logfile:
            If given, set up a RotatingFileHandler to receive logging output.
            Should be the absolute path to the desired logfile
            or special value "syslog".
            Defaults to *None* (no logfile).
        :option int log_level:
            Level to use for ``logfile``.
            Must be one of the constants defined in the ``logging`` module
            (e.g. DEBUG, INFO, ...).
            Has no effect if ``logfile`` is not given.
    '''
    rootlog = logging.getLogger()
    rootlog.setLevel(logging.DEBUG)

    if not options.quiet:
        console_hdl = logging.StreamHandler()
        console_level = logging.DEBUG if options.verbose else logging.INFO
        console_hdl.setLevel(console_level)
        console_hdl.setFormatter(logging.Formatter(CONSOLE_FMT))
        rootlog.addHandler(console_hdl)

    if options.logfile:
        if options.logfile == 'syslog':
            logfile_hdl = handlers.SysLogHandler(address='/dev/log')
            logfile_hdl.setFormatter(logging.Formatter(SYSLOG_FMT))
        else:
            logfile_hdl = handlers.RotatingFileHandler(options.logfile)
            logfile_hdl.setFormatter(logging.Formatter(LOGFILE_FMT))
        logfile_hdl.setLevel(options.log_level)
        rootlog.addHandler(logfile_hdl)


if __name__ == '__main__':
    sys.exit(main())
