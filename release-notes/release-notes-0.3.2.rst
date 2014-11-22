##############
Podfetch 0.3.2
##############
Changes in **podfetch 0.3.2**:

Index files are now kept under ``~/.local/share/podfetch/``
instead of ``~/.cache/podfetch/``.

Subscriptions may define an individual ``content_dir`` where episodes
are stored.

.. code:: ini

    [subscription]
    url = http://example.com/podcast
    title = Some Name
    content_dir = /path/to/episodes

.. code:: shell-session

    $ podfetch add http://example.com/podcast -d /path/to/episodes
