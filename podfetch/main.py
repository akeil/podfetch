#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
Main entry point as defined in setup.py.

Sets up the argument parser,
configures logging
and runs the program.
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
    if argv is None:
        argv = sys.argv[1:]

    parser = setup_argparser()
    args = parser.parse_args(argv)
    cfg = read_config()
    configure_logging(
        verbose=args.verbose,
        quiet=args.quiet,
        logfile=args.logfile,
        log_level=args.log_level,
    )

    log.info('Starting.')
    try:
        run(args, cfg)
        rv = EXIT_OK
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
    pass


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
        default=DEFAULT_LOG_LEVEL,
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
    extra = extra_config_paths or []
    paths = [DEFAULT_CONFIG_PATH,] + extra
    cfg = configparser.ConfigParser()
    read_from = cfg.read(*paths)
    if not read_from and require:
        raise ValueError(('No configuration file found.'
            ' Searchpath: {!r}.').format(':'.join(paths)))

    log.info('Read configuration from: {}.'.format(':'.join(read_from)))
    return cfg


def configure_logging(quiet=False, verbose=False,
    logfile=None, log_level=DEFAULT_LOG_LEVEL):
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
            logfile_hdl = handlers.SyslogHandler(address='/dev/log')
            logfile_hdl.setFormatter(logging.Formatter(SYSLOG_FMT))
        else:
            logfile_hdl = handlers.RotatingFileHandler(logfile)
            logfile_hdl.setFormatter(logging.Formatter(LOGFILE_FMT))
        logfile_hdl.setLevel(log_level)
        rootlog.addHandler(logfile_hdl)


if __name__ == '__main__':
    sys.exit(main())