#######
Cronjob
#######
Podfetch is intended to run periodically and fetch new podcast episodes as
they are published.

Preparations
############
Install podfetch in a virtual environment::

    $ mkdir ~/.virtualenvs
    $ cd ~/.virtualenvs
    $ virtualenv podfetch
    $ cd podfetch
    $ source bin/activate
    (podfetch)$ pip install podfetch

Podfetch comes with a script to access the command line interface.
The script can be found at ``VIRTUALENV/bin/podfetch``.
If podfetch was installed as described above, the script is at
``~/.virtualenvs/podfetch/bin/podfetch``.

Normal Cronjob
##############
One can set up a ``cronjob`` to do this like so::

    $ crontab -e

Will open the user-specific crontab in an editor. Add an entry for podfetch
like this::

    7 20 * * * $HOME/.virtualenvs/podfetch/bin/podfetch --quiet update

This will update all subscriptions every day at 20:07 - *if* the system
is running at that time.
If the computer is turned off at the specified time, the job is missed.

Anacron
#######
``anacron`` can be used to run commands at a specified interval
(*daily*, *weekly*, *monthly*) and it will "catch up" if the job did not run.

To schedule a daily update of all podcasts, create a mini script like this::

    podfetch-update-all.sh
    --------------------------------------------------------
    ~/.virtualenvs/podfetch/bin/podfetch --quiet update

...and symlink it to ``cron.daily``
(you need to be root to write in ``cron.daily``)::

    $ sudo ln -s /path/to/podfetch-update-all.sh /etc/cron.daily

.. todo::

    By default, ``anacron`` will be run as ``root``.
    To change this...

User Specific Anacron
=====================
There is an alternative with some configuration work.
Create a per-user anacron.

Taken from
http://www.it.uc3m.es/marcos/doc/miniHOWTOs/miniHOWTO-Use_anacron_as_non-root_user.html

Assuming that ``anacron`` is already installed.

``anacron`` will require write access to ``/var/spool/anacron``.
By default, only ``root`` has permissions on that directory.

The first step is to create a group *anacron*, give members of that group
access to the spool-directory and add "normal" users to that group.
As root::

    # groupadd anacron
    # chown root:anacron /var/spool/anacron
    # chmod g+w /var/spool/anacron
    # useradd USERNAME anacron

Next, create a user-specific anacron file.
Copy the system-wide file to some place in your home directory::

    $ cp /etc/anacrontab ~/.anacrontab

Edit the file to look like this::

    ~/.anacrontab
    -------------------------------------------------------------------
    SHELL=/bin/sh
    PATH=/sbin:/bin:/usr/sbin:/usr/bin

    # period delay job-identifier command
    1   5   USERNAME.cron.daily    nice run-parts --report HOME/.cron.daily
    7   10  USERNAME.cron.weekly   nice run-parts --report HOME/.cron.weekly
    30  15  USERNAME.cron.monthly  nice run-parts --report HOME/.cron.monthly

Replace ``USERNAME`` with your user name and ``HOME`` with the path to your
home directory.
We have added the username to the job identifier.
And instead of running scripts from ``/etc/cron.xxx``,
we run them from a user-specific location.

Remember to place/symlink the podfetch script in your ``cron.daily`` directory.

With the configuration in place, you must still tell anacron to
actually start and run your jobs.

For example, to run when you log in, edit your ``.bash_profile``::

    ~/.bash_profile
    ---------------------------------------
    /usr/sbin/anacron -t $HOME/.anacrontab


Gnome Schedule
##############
A GUI tool to configure scheduled jobs.
https://wiki.gnome.org/Schedule
http://gnome-schedule.sourceforge.net/
