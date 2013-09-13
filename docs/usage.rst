#####
Usage
#####

Command line
#############

Update all podcasts::

    $ podfetch update

Update a selected podcast::

    $ podfetch update podcast_name

or more than one::

    $ podfetch update podcast_name another_podcast

When used as a **cron job**::

    podfetch --quiet --logfile=syslog update

Managing Subscriptions
======================

To add a new podcast::

    $ podfetch add http://example.com/rss

Will create a podcast named "example" (from example.com).
To specify the name explicitly::

    $ podfetch add http://example.com/rss --name my_name

To remove a subscription::

    $podfetch remove podcast_name

To see a list of all subscriptions::

    $ podfetch ls

Hooks
=====
*Hooks* are executable files (scripts) placed in specific directories.
The hooks are executed on specific events:

:updates_complete:
    After a successful update of *all* subscriptions,
    i.e. after ``podfetch update`` was invoked *without* arguments
    and there was no error.
:subscription_updated:
    After a single subscription was updated successfully,
    i.e. after ``podfetch update`` was invoked with or without arguments,
    once for each podcast feed.
    This hook receives two positional command line arguments:

     #) the name of the subscription
     #) the absolute path to the content directory for this subscription

    See examples below on how to access the arguments.

:subscription_added:
    Runs after a new subscription was added
    using the ``podfetch add`` command.
    Receives the same positional arguments as *subscription_updated*.
:subscription_removed:
    Runs after a new subscription was deleted
    using the ``podfetch remove`` command.
    Receives the same positional arguments as *subscription_updated*.

By default, the hook directories are::

    ~/.config/podfetch/
        subscription_added/
        subscription_removed/
        subscription_updated/
        updates_complete/

Hooks are created by placing an executable file in any of these directories.

Handling Errors
---------------
If a hook-script returns a non-zero exit status,
this will be written to the logfile as an ``ERROR``.

Hooks Examples
--------------

Update MPD (**LINK**) after new episodes have been downloaded::

    ~/.config/podfetch/updates_complete/mpd-update.sh
    --------------------------------------------------------
    mpc update

Sync downloaded episodes to some other location::

    ~/.config/podfetch/subscription_updated/sync.sh
    --------------------------------------------------------
    rsync $2 /some/other/location


Python
######

To use PodFetch in a project::

    import podfetch
