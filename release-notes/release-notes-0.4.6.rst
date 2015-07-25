.. date: 2015/05/01 00:00:00

##############
podfetch 0.4.6
##############
Changes in **podfetch 0.4.6**:

New Command ``--edit`` to change subscription properties.
Can also be used to move/rename files for downloaded episodes.

Edit can either be used to set individual fields like this:

    $ podfetch edit subscription-name --title 'New Title'

Or by opening the config file in the ``$EDITOR``

    $ podfetch edit subscription-name

Opens the ini file for ``subscription-name`` in the preferred ``$EDITOR``.

In ``ls``, the ``--since`` and ``--until`` options imply the ``--all``
option. That is, all episodes from the given timespan are listed.
