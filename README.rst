########
podfetch
########
Fetch audio or video podcasts and store files locally.

Features
########
- Manage subscriptions through the command line
  or by editing configuration files.
- Download all podcasts with a single command,
  e.g. as a cron-job.
- Hooks to execute additional commands after downloading new episodes.


Configuration
#############
The central configuration files are
* ``/etc/podfetch.conf`` for system-wide settings
* ``~/.config/podfetch/podfetch.conf`` for user based settings

Configuration options are:

.. code:: ini

    [default]
    # where to store downloaded episodes
    content_dir = ~/Documents/Podcasts

    # filenames for downloaded episodes
    filename_template = {pub_date}-{title}

    # number of threads for parallel downloads
    update_threads = 8


Subscriptions
=============
Subscriptions are kept as ini-files under ``~/.config/podfetch/subscriptions``
with one file per feed.
The files look like this (``url`` is the only mandatory setting):

.. code:: ini

    [subscription]
    url = http://www.example.com/podcast

    # maximum number of episodes to keep
    max_episodes = 30

    # display title
    title = My Podcast

    # override application wide template for this subscription
    filename_template = {title}

    # override application config for this subscription
    content_dir = /path/to/episodes

    # set this to False to stop fetching updates for this subscription
    enabled = True


Interesting Directories
=======================
``~/.config/podfetch``
    Contains the user-specific config file
    and the ``subscriptions/`` subdirectory with settings for
    individual podcasts.
    Can also contain *hooks*.

``~/.local/share/podfetch``
    The default location for downloaded episodes
    and *index files* where episode details are stored.

``~/.cache/podfetch``
    Recent values from *etag* and *last-modified* HTTP headers
    for each subscription.
