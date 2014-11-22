########
podfetch
########
Fetch audio or video podcasts and store files locally.

Features
########
- Manage subscriptions through the command line
  or by editing coonfiguration files.
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
