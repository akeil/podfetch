.. date: 2015/03/29 00:00:00

##############
podfetch 0.4.3
##############
Changes in **podfetch 0.4.3**:

The ``ls`` and ``update`` commands accept shell wildcards
for subscription names:

.. code:: shell-session

    $ podfetch ls f?o ba*

Lists subscriptions *foo*, *bar* and *baz*
but not *something-else*.


If the subscriptions directory contains files that are not podfetch
subscriptions, a **new config option** ``ignore`` can be used to tell podfetch
to ignore these:

.. code:: ini

    [podfetch]
    ignore = .* *.bak

The option expects a whitespace separated list of patterns
that should be ignored.
