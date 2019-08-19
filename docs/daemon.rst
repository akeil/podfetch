######
Daemon
######

.. note:: as of Version 0.6.2 this is **NOT IMPLEMENTED**

Podfetch can be run in daemon mode.
This means, podfetch will run "forever" and periodically check for updated
feeds.

There are two possible scenarios:

:User Session:
    podfetch is started from within a users (desktop) session.
    The app will run in the background and will connect to the user's session
    bus (DBus).
    Additionally, a socket-based interface can be used to interact with the
    daemon.
:Systemwide:
    podfetch is run in a system wide instance.
    In this case, it will not connect to DBus but is still reachable
    over the network based interface.

Network
#######
The networked interface is HTTP based.
It can be made available over a "normal" TCP connection
or over a Unix domain socket.
The interface is ReST based
and additionally offers push funcionality over WebSockets.


Resources
=========


App
---

URLs::
    /app/update
    /app/update/{NAME}
    /app/purge

:POST: trigger the app-function

Parameters:
:force: yes/no; forced update


Subscription
------------

URL: ``/subscription/{NAME}``

:GET: subscription details
:POST: create (option: update y/n)
:PUT: update
:PATCH: partial update
:DELETE: permanently delete

Parameters:

:no-move: do not move existing files after changing filename template
    for PUT and PATCH.
:delete-episodes: yes/no, delete downloaded episodes
    for DELETE


Subscriptions (List)
--------------------

URL: ``/subscriptions``

:GET: list subscriptions

List params:
since DATE
until DATE
newest N
all (y/n)


Episode
-------
:GET: details
:PATCH: update partially (e.g. "read/unread")


DBus
####
Intended for use with "applets" or other desktop related mini-apps.


Components
##########
The daemon functionality is made up of the collowing components:

Daemon
initialized on startup, manages the lifecycle of the app
(which is startup and shutdown - and possibly "reload")

sets up all required services and interfaces
and shuts them down again.

web
the web API with submodules REST and WebSocket

DBus
the DBus interface
