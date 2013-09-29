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

    # This application-wide setting tells podfetch
    # how to construct filenames for downloaded episodes.
    # The following variables are supported:
    #   {subscription_name}: Subscription Name
    #   {pub_date}:     Date in format yyyy-mm-dd
    #   {year}:         Year from Pub-Date in 4-digit format
    #   {month}:        Month from Pub-Date in 2-digit format
    #   {day}:          Day from Pub-Date in 2-digit format
    #   {hour}:         Hour from Pub-Date in 2-digit format
    #   {minute}:       Minute from Pub-Date in 2-digit format
    #   {second}:       Second from Pub-Date in 2-digit format
    #   {title}:        Entry (Episode) title
    #   {feed_title}:   Feed title
    #   {id}:           Id for the Episode
    #   {ext}:          File extension.
    #   {kind}:         audio or video
    # Specifying an extension ub the template is optional; missing extension
    # is added automatically
    filename_template = {pub_date}-{title}

**You do not have to create a config file if the defaults are ok.**
