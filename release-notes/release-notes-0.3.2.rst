.. date: 2014/11/23 00:00:00

##############
podfetch 0.3.2
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


The **add** command supports a (filename-) ``template`` parameter.
It has the same effect as the ``filename_template`` setting in the
configuration files.

.. code:: shell-session

    $ podfetch add http://example.com/podcast --template '{title}-{id}.{ext}'


The **purge** command is improved:
 - select episodes by date published (was: filename)
 - simulation mode
 - correctly handle episodes with multiple files

