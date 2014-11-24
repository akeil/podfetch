##############
podfetch 0.4.0
##############
Changes in **podfetch 0.4.0**:

The *ls* was now outputs episodes in reverse chronological order.
The most recently published episodes are listed first.
Episodes are sorted by date, even if episodes from multiple
subscriptions are shown.

When no subscription name is specified, ``ls`` will now list
episodes from *all* subscriptions.
In previous versions, ``ls`` would output the list of subscriptions
in this case.

Additional parameters were added:

--newest / -n
    To control the number of episodes shown

--all / -a
    To *not* limit the number of episodes shown

**Examples**

List the 10 (default) most recent episodes:

.. code:: shell-session

    $ podfetch ls


List up to 20 episodes:

.. code:: shell-session

    $ podfetch ls -n 20

List the 10 (default) most recent episodes
from subscriptions "foo" and "bar":

.. code:: shell-session

    $ podfetch ls foo bar

Show all episodes from subscription "foo":

.. code:: shell-session

    $ podfetch ls -a foo 
