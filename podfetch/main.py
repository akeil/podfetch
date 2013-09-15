#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
The command line interface for Podfetch.
'''
import sys
import os
import logging
from logging import handlers
import argparse
try:
    import configparser  # python 3
except ImportError:
    import ConfigParser as configparser  # python 2

import podfetch
from podfetch import application


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

DEFAULT_CONFIG_PATH = os.path.expanduser(
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

    try:
        rv = run(args, cfg)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log.error(e)
        rv = EXIT_ERROR
    finally:
        # TODO perform cleanup
        pass

    log.info('Exit with return code: {}.'.format(rv))
    return rv


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
    return args.func(app, args)


def _create_app(cfg):
    try:
        config_dir = cfg.get('default', 'config_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        config_dir = os.path.expanduser( os.path.join(
            '~', '.config', 'podfetch'))

    try:
        content_dir = cfg.get('default', 'content_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        content_dir = os.path.expanduser( os.path.join(
            '~', '.local', 'share', 'podfetch', 'content'))

    try:
        cache_dir = cfg.get('default', 'cache_dir')
    except (configparser.NoOptionError, configparser.NoSectionError):
        cache_dir = os.path.expanduser( os.path.join(
            '~', '.cache', 'podfetch'))

    log.info('Looking for subscriptions and hooks in {!r}.'.format(config_dir))
    log.info('Download audio files to {!r}.'.format(content_dir))
    log.info('Cache directory is {!r}.'.format(cache_dir))
    return application.Podfetch(config_dir, content_dir, cache_dir)


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
    subs = parent_parser.add_subparsers()

    # update-------------------------------------------------------------------
    fetch = subs.add_parser(
        'update',
        help='Update subscriptions.'
    )

    fetch.add_argument(
        'subscription_name',
        nargs='*',
        help=('The names of the subscriptions to be updated.'
            ' If no name is given, all subscriptions are updated.'),
    )

    def do_update(app, args):
        if not args.subscription_name:
            return app.update_all()
        else:
            for name in args.subscription_name:
                app.update_one(name)
            # TODO rv
            return 0
    fetch.set_defaults(func=do_update)

    # list --------------------------------------------------------------------
    ls = subs.add_parser(
        'ls',
        help='List subscriptions and downloaded files.'
    )

    ls.add_argument(
        'subscription_name',
        nargs='?',
        help=('The names of the subscriptions to be listed.'
            ' If one or more names are given, lists downloaded files.'
            ' If no name is given, prints a list of all subscriptions'
            ' and no files.'),
    )

    def do_ls(app, args):
        out = sys.stdout
        header = 'Podfetch Subscriptions'
        out.write('{}\n'.format(header))
        out.write('{}\n'.format('-' * len(header)))
        if not args.subscription_name:
            for subscription in app.iter_subscriptions():
                out.write('{}\n'.format(subscription.name))
        else:
            for subscription in app.iter_subscriptions():
                if subscription.name in args.subscription_name:
                    out.write('{}\n'.format(subscription.name))
                    # TODO list downloaded episodes

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
        '--no-update',
        action='store_true',
        help='Do not immediately fetch content for the new subscription.',
    )

    def do_add(app, args):
        sub = app.add_subscription(args.url,
            name=args.name,
            max_episodes=args.max_episodes
        )
        if not args.no_update:
            app.update_one(sub.name)
        return 0
    add.set_defaults(func=do_add)

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

    def do_purge(app, args):
        if not args.subscription_names:
            for subscription in app.iter_subscriptions():
                app.purge_one(subscription.name)
        else:
            for subscription in app.iter_subscriptions():
                if subscription.name in args.subscription_names:
                    app.purge_one(subscription.name)

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
    paths = [DEFAULT_CONFIG_PATH,] + extra
    cfg = configparser.ConfigParser()
    read_from = cfg.read(paths)
    if not read_from and require:
        raise ValueError(('No configuration file found.'
            ' Searchpath: {!r}.').format(':'.join(paths)))

    log.info('Read configuration from: {}.'.format(':'.join(read_from)))
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
