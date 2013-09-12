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

Python
######

To use PodFetch in a project::

    import podfetch
