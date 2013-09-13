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

The configuration file looks like this (with default values)::

    [default]
    # The directory where the configuration files for subscriptions
    # are stored. Contains a single file for each subscription.
    config_dir = ~/.config/podfetch

    # The base directory for storing downloaded audio files.
    # podfetch will create a subdirectory for each subscription
    content_dir = ~/.local/share/podfetch

    # Podfetch will store the values  "Modified" and "ETAG" headers received
    # from RSS/Atom-Feeds here.
    cache_dir = ~/.cache/podfetch

**You do not have to create a config file if the defaults are ok.**
