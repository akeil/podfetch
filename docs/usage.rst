#####
Usage
#####

Command line
#############

Update all podcasts::

    $ podfetch all

Update selected podcasts::

    $ podfetch podcast_name

or::

    $ podfetch podcast_name another_podcast

Add Podcasts
============

To add a new podcast::

    $ podfetch add http://example.com/rss

Will create a podcast named "example".
To specify the name explicitly::

    $ podfetch add http://example.com/rss --name my_name

More involved::

    $ podfetch add http://example.com/rss --name my_name --history 12

Keeps at most 12 episodes

To remove::

    $podfetch remove podcast_name

Python
######

To use PodFetch in a project::

    import podfetch
