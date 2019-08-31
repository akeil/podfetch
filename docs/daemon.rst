######
Daemon
######

Podfetch can be run in daemon mode by using:

.. code-block:: shell-session

    $ podfetch daemon

This means, podfetch will run "forever" and periodically check for updated
feeds.


Systemd Service
###############
To configure a podfetch daemon with systemd,
create a ``podfetch-daemon.service`` file in the user directory for systemd
(``~/.config/systemd/user/podfetch-daemon.service``).

.. code-block:: ini

    [Unit]
    Description=Download podcasts with podfetch
    After=network.target

    [Service]
    ExecStart=%h/.local/bin/podfetch daemon

    [Install]
    WantedBy=default.target

Then start and enable with:

.. code-block:: shell-session

    $ systemd --user enable podfetch-daemon.service
    $ systemd --user start podfetch-daemon.service


Configuration
#############


Update Schedule
===============
The podfetch daemon will update all enabled feeds periodically.
The update schedule can be configured in the ``daemon`` section
of the config file like this:

.. code-block:: ini

    [podfetch]
    ...

    [daemon]
    update_interval = 60


Pidfile
=======
The daemon uses a pidfile to detect if another instance of podfetch is already
running. The daemon is intended to be run with one instance per user.
The location of the pidfile can be configured like this:

.. code-block:: ini

    [podfetch]
    ...

    [daemon]
    pidfile = ~/.podfetch.pid


Plugins
#######
By default, the daemon mode will only have the periodic update feature.
This can be extended with *plugins*.

The daemon will load plugins from entry points under ``podfetch.service``.

:start: A plugin must implement the entry point named ``start``
        which must refer to a callable that accepts a podfetch instance
        and parsed options (as returned from *ConfigParser*):

        .. code-block:: python

            start(app, options)

        Each plugin is started in a separate thread.
:stop:  A plugin *can* implement a ``stop`` entry point
        which if present must refer to a callable that receives
        *no arguments*:

        .. code-block:: python

            stop()

        The ``stop()`` function will be called before the daemon exits.
        ``stop()`` is called from the **Main Thread**.

Here is an example for the built-in scheduler plugin from ``setup.py``:

.. code-block:: python

    setup(
        # ...
        entry_points={
            # ...
            'podfetch.service': [
                'start = podfetch.scheduler:start',
                'stop = podfetch.scheduler:stop',
            ],
        }
    )
