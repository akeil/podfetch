.. date: 2015/05/01 00:00:00

##############
podfetch 0.5.1
##############
Changes in **podfetch 0.5.1** (covers change since *0.4.6*):

``podfetch`` now defines *entry points* for plugins.
Entry points are::

    podfetch.events
        subscription_updated
        updates_complete
        subscription_added
        subscription_removed

Plugins can provide *callables* for each of the above entry points.
The *callable* is invoked when the respective event occurs with the following
arguments:

- subscription_updated
    - name
    - content_dir

- updates_complete
    - None

- subscription_added
    - name
    - content_dir

- subscription_removed
    - name
    - content_dir
