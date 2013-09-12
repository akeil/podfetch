#####
Usage
#####

Command line
#############

Update all podcasts::

    $ podfetch fetch

Update selected podcasts::

    $ podfetch fetch podcast_name

or::

    $ podfetch fetch podcast_name another_podcast

If used as a **cron job**::

    podfetch --quiet --logfile syslog fetch

Managing Subscriptions
======================

To add a new podcast::

    $ podfetch add http://example.com/rss

Will create a podcast named "example".
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

episode downloaded
------------------
Invoked after a single episode has been downloaded successfully.

    Context:
    name
    content_dir
    filename

subscription updated
--------------------
Runs after one ore more episodes were downloaded for a subscription.

    Context:
    name
    content_dir
    filenames

Python
######

To use PodFetch in a project::

    import podfetch
