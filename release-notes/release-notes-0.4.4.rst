.. date: 2015/03/29 00:00:00

##############
podfetch 0.4.4
##############
Changes in **podfetch 0.4.4**:

New parameters for the ``ls`` command to list only episodes
``--since`` and/or ``--until`` a given date:

.. code:: shell-session

    $ podfetch ls --since yesterday
    [yesterday and today]

    $ podfetch ls --since 4d
    [last 4 days]

    $ podfetch ls --since 2weeks --until 1week
    [last week]

    $ podfetch ls --since '2 weeks' --until yesterday
    [last two weeks but not today]

Timespecs are always "backwards", i.e. ``2 weeks``
means "two weeks ago".
