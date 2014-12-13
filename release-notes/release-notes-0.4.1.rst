.. date: 2014/12/13 00:00:00

##############
podfetch 0.4.1
##############
Changes in **podfetch 0.4.1**:

The **ls command** accepts an additional parameter ``--path/-p`` to print
the *paths* of downloaded files instead of episode titles:

.. code:: shell-session

    $ podfetch ls -p
    $ podfetch ls -p foo bar


Improved error handling for invalid subscription files.
