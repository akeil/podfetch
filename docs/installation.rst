############
Installation
############

Install
#######

At the command line::

    $ easy_install podfetch

Or, if you have virtualenvwrapper installed::

    $ mkvirtualenv podfetch
    $ pip install podfetch

Configure
#########

The configuration file is expected in
``~/.config/podfetch/podfetch.conf``,
alternative locations can be specified on the command line
using the ``--config`` option.

The configuration file looks like this::

    [default]
    # The directory where the configuration files for subscriptions
    # are stored. Contains a single file for each subscription.
    subscriptions_dir = /path/to/subscriptions

    # The base directory for storing downloaded audio files.
    # podfetch will create a subdirectory for each subscription
    content_dir = /path/to/content
