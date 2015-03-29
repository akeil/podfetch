#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
The command line interface for Podfetch.
'''
import sys
import os
import logging
from logging import handlers
from textwrap import wrap
import argparse
try:
    import configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2

import podfetch
from podfetch import application
from podfetch.exceptions import NoSubscriptionError
from podfetch.exceptions import UserError


PROG_NAME = 'podfetch'
VERSION = podfetch.__version__
DESCRIPTION = 'Fetch audio podcasts and store files locally.'
AUTHOR = podfetch.__author__
AUTHOR_MAIL = podfetch.__email__

# logging config
CONSOLE_FMT = '%(levelname)s: %(message)s'
SYSLOG_FMT = '%(levelname)s [%(name)s]: %(message)s'
LOGFILE_FMT = '%(asctime)s %(levelname)s [%(name)s]: %(message)s'
DEFAULT_LOG_LEVEL = 'warning'

CFG_DEFAULT_SECTION = 'default'
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
    and runs the program by invoking :function:`run()`, passing the parsed arguments
    and configuration.

    :param list argv:
        Command line arguments.
        If *None* (the default), ``sys.argv`` is used.
    '''
    if argv is None:
        argv = sys.argv[1:]

    parser = setup_argparser()
    setup_command_parsers(parser)
    args = parser.parse_args(argv)
    configure_logging(
        verbose=args.verbose,
        quiet=args.quiet,
        logfile=args.logfile,
        log_level=args.log_level,
    )
    cfg = read_config(extra_config_paths=[args.config,])
    log.debug('Parsed args: {}'.format(args))
    try:
        rv = run(args, cfg)
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

    log.debug('Exit with return code: {}.'.format(rv))
    return rv or EXIT_OK  # converts None|False -> 0


def run(args, cfg):
    '''Run podfetch with the given command line args and config.

    :param object args:
        The ``Namespace`` with parsed command line arguments.
    :param object cfg:
        A ``ConfigParser`` instance with values parsed from the config file(s).
    :rtype int:
        The *Return Code* of the application-run.
    '''
    app = _create_app(cfg)
    try:
        func = args.func
    except AttributeError:
        raise UserError('No subcommand specified.')
    return func(app, args)


def _create_app(cfg):
    '''set up the application instance using the given config

    :param ConfigParser cfg:
        A ConfigParser instance containing the configuration values
        to be used.
    :rtype object:
        An :class:`application.Podfetch` instance.
    '''
    try:
        config_dir = cfg.get(CFG_DEFAULT_SECTION, 'config_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        config_dir = os.path.expanduser( os.path.join(
            '~', '.config', 'podfetch'))

    try:
        index_dir = cfg.get(CFG_DEFAULT_SECTION, 'index_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        index_dir = os.path.expanduser( os.path.join(
            '~', '.local', 'share', 'podfetch'))

    try:
        content_dir = cfg.get(CFG_DEFAULT_SECTION, 'content_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        content_dir = os.path.expanduser( os.path.join(
            '~', '.local', 'share', 'podfetch', 'content'))

    try:
        cache_dir = cfg.get(CFG_DEFAULT_SECTION, 'cache_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        cache_dir = os.path.expanduser( os.path.join(
            '~', '.cache', 'podfetch'))

    try:
        filename_template = cfg.get(CFG_DEFAULT_SECTION, 'filename_template')
    except (configparser.NoOptionError, configparser.NoSectionError):
        filename_template = None

    update_threads = None
    try:
        update_threads_str = cfg.get(CFG_DEFAULT_SECTION, 'update_threads')
        try:
            update_threads = int(update_threads_str)
        except (ValueError, TypeError):
            log.warning('Ignoring invalid value {!r} for {!r}.'.format(
                update_threads_str, 'update_threads'))
    except (configparser.NoOptionError, configparser.NoSectionError):
        pass

    return application.Podfetch(
        config_dir, index_dir, content_dir, cache_dir,
        filename_template=filename_template,
        update_threads=update_threads,
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
        help='Print version number and exit.'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Increase console output.',
    )

    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Write nothing to stdout.',
    )

    parser.add_argument(
        '-l', '--logfile',
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

    parser.add_argument(
        '--log-level',
        action=LogLevelAction,
        default=logging.WARNING,
        choices=loglevels.keys(),
        help=('Controls the log-level for LOGFILE.'
            ' Defaults to {default}.').format(default=DEFAULT_LOG_LEVEL),
    )

    def path(argstr):
        path = os.path.expanduser(argstr)
        path = os.path.normpath(path)
        if not os.path.isabs(path):
            path = os.path.joion(os.getcwd(), path)
        return path

    parser.add_argument(
        '--config',
        type=path,
        help='Read configuration from the specified file.',
    )

    return parser


def setup_command_parsers(parent_parser):
    '''Set up the sub-parsers for the "action-commands":
      - update
      - list
      - add
      - purge
    Parsers for these commands will be added to the given ``parent_parser``.

    :param ArgumentParser parent_parser:
        The parent parser.
    '''
    subs = parent_parser.add_subparsers()

    # update-------------------------------------------------------------------
    fetch = subs.add_parser(
        'update',
        help='Update subscriptions.'
    )

    fetch.add_argument(
        'subscription_names',
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
        rv = app.update(args.subscription_names, force=args.force)
        return rv
    fetch.set_defaults(func=do_update)

    # list --------------------------------------------------------------------
    ls = subs.add_parser(
        'ls',
        help='List Episodes by date.'
    )

    ls.add_argument(
        'subscription_name',
        metavar='NAME',
        nargs='*',
        help=('Names of subscriptions from which episodes are listed. If'
            ' NAME(S) are given, episodes from these podcasts are shown.'
            ' Allows wildcards.'
            ' If no name is given list episodes from all podcasts.'),
    )

    ls.add_argument(
        '--path', '-p',
        action='store_true',
        help='Print paths instead of titles.',
    )

    n_control = ls.add_mutually_exclusive_group()
    n_control.add_argument(
        '--newest', '-n',
        metavar='N',
        type=int,
        help=('Control the number of episodes shown.'
            ' Excludes the --all option.'),
    )
    n_control.add_argument(
        '--all', '-a',
        action='store_true',
        help=('Do not limit the number of episodes shown.'
            ' Excludes the --newest option.'),
    )

    def do_ls(app, args):
        out = sys.stdout

        if not args.path:
            header = 'Podfetch Episodes'
            out.write('{}\n'.format(header))
            out.write('{}\n'.format('-' * len(header)))

        episodes = []

        if not args.subscription_name:
            # no name is specified - list episodes from all subscriptions
            for subscription in app.iter_subscriptions():
                episodes += subscription.episodes
        else:
            # names specified - list episodes from selected subscriptions
            for name in args.subscription_name:
                try:
                    sub = app.subscription_for_name(name)
                    episodes += sub.episodes
                except NoSubscriptionError:
                    log.warning('No subscription named {!r}.\n'.format(name))

        # sort all selected episodes by date, then reduce to N items
        episodes.sort(key=lambda e: e.pubdate, reverse=True)
        if not args.all:
            limit = args.newest or 10  # arbritrary default
            if limit < 0:
                raise ValueError(('Invalid limit {} for ls.'
                    ' Expected a positive integer').format(limit))

            episodes = episodes[:limit]

        # write episodes
        lastdate = None
        for episode in episodes:
            curdate = '{:0>4}-{:0>2}-{:0>2}'.format(
                episode.pubdate[0],
                episode.pubdate[1],
                episode.pubdate[2],
            )
            if args.path:
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

    # add ---------------------------------------------------------------------
    add = subs.add_parser(
        'add',
        help='Add a new subscription.'
    )

    add.add_argument(
        'url',
        help='The feed URL.'
    )
    add.add_argument(
        '-n', '--name',
        help=('A name for the subscription.'
            ' If none is given, the name will be derived from the URL.'),
    )
    add.add_argument(
        '-m', '--max-episodes',
        type=int,
        default=-1,
        help=('The maximum number of downloaded episodes to keep.'
            ' Default is "-1" (unlimited).'),
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
        dest='content_dir',
        help=('Download episodes to the given directory.'
            ' If omitted, the application default and a '
            ' subdirectory with the subscription name.'
        )
    )
    add.add_argument(
        '--no-update',
        action='store_true',
        help='Do not immediately fetch content for the new subscription.',
    )

    def do_add(app, args):
        sub = app.add_subscription(args.url,
            name=args.name,
            content_dir=args.content_dir,
            max_episodes=args.max_episodes,
            filename_template=args.template,
        )
        if not args.no_update:
            app.update(sub.name)
        return 0
    add.set_defaults(func=do_add)

    # show ---------------------------------------------------------------------
    show = subs.add_parser(
        'show',
        help='View subscription details.',
    )
    show.add_argument(
        'subscription_names',
        metavar='NAME',
        nargs='*',
        help=('Name(s) of subscriptions to show.'
            ' If not given, show all.'),
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

    # del ----------------------------------------------------------------------
    dele = subs.add_parser(
        'del',
        help='Delete subscriptions.',
    )
    dele.add_argument(
        'subscription_names',
        metavar='NAME',
        nargs='+',
        help='Name(s) of subscription(s) to delete.'
    )
    dele.add_argument(
        '--episodes', '-e',
        action='store_true',
        help=('Also delete downloaded episodes.'
            ' Default is to keep episodes.'),
    )

    def do_dele(app, args):
        for name in args.subscription_names:
            try:
                app.remove_subscription(name, delete_content=args.episodes)
            except NoSubscriptionError:
                log.warning('No subscription named {!r}.\n'.format(name))

        return EXIT_OK

    dele.set_defaults(func=do_dele)

    # purge --------------------------------------------------------------------
    purge = subs.add_parser(
        'purge',
        help='Remove old downloaded episodes.'
    )
    purge.add_argument(
        'subscription_name',
        nargs='?',
        help=('The names of the subscriptions for which old files'
            ' should be removed. If no name is given, all subscriptions'
            ' are purged.'),
    )
    purge.add_argument(
        '-s', '--simulate',
        action='store_true',
        help='List filenames, do not delete.'
    )

    def do_purge(app, args):
        result = []
        if not args.subscription_name:
            result += app.purge_all(simulate=args.simulate)
        else:
            for name in args.subscription_name:
                result += app.purge_one(
                    subscription.name, simulate=args.simulate
                )

        log.info('Purged {} files...'.format(len(result)))
        for filename in result:
            log.info('Purged {!r}'.format(filename))
        if result and args.simulate:
            log.warning('Simulation - no files were deleted.')

    purge.set_defaults(func=do_purge)


def read_config(extra_config_paths=None, require=False):
    '''Read configuration from the ``DEFAULT_CONFIG_PATH and
    optionally supplied ``extra_config_paths``.

    :param list extra_config_paths:
        Additional locations to be scanned for config files.
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
    extra = [p for p in extra_config_paths if p]
    paths = [SYSTEM_CONFIG_PATH, DEFAULT_USER_CONFIG_PATH,] + extra
    # TODO remove duplicate path entries
    cfg = configparser.ConfigParser()
    read_from = cfg.read(paths)
    if not read_from and require:
        raise ValueError(('No configuration file found.'
            ' Searchpath: {!r}.').format(':'.join(paths)))

    log.debug('Read configuration from: {!r}.'.format(':'.join(read_from)))
    return cfg


def configure_logging(quiet=False, verbose=False,
    logfile=None, log_level=logging.WARNING):
    '''Configure log-level and logging handlers.

    :param bool quiet:
        If *True*, do not configure a console handler.
        Defaults to *False*.
    :param bool verbose:
        If *True*, set the log-level for the console handler
        to DEBUG. Has no effect if ``quiet`` is *True*.
        Defaults to *False*.
    :param str logfile:
        If given, set up a RotatingFileHandler to receive logging output.
        Should be the absolute path to the desired logfile
        or special value "syslog".
        Defaults to *None* (no logfile).
    :param int log_level:
        Level to use for ``logfile``.
        Must be one of the constants defined in the ``logging`` module
        (e.g. DEBUG, INFO, ...).
        Has no effect if ``logfile`` is not given.
    '''
    rootlog = logging.getLogger()
    rootlog.setLevel(logging.DEBUG)

    if not quiet:
        console_hdl = logging.StreamHandler()
        console_level = logging.DEBUG if verbose else logging.INFO
        console_hdl.setLevel(console_level)
        console_hdl.setFormatter(logging.Formatter(CONSOLE_FMT))
        rootlog.addHandler(console_hdl)

    if logfile:
        if logfile == 'syslog':
            logfile_hdl = handlers.SysLogHandler(address='/dev/log')
            logfile_hdl.setFormatter(logging.Formatter(SYSLOG_FMT))
        else:
            logfile_hdl = handlers.RotatingFileHandler(logfile)
            logfile_hdl.setFormatter(logging.Formatter(LOGFILE_FMT))
        logfile_hdl.setLevel(log_level)
        rootlog.addHandler(logfile_hdl)


if __name__ == '__main__':
    sys.exit(main())
