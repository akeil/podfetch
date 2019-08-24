#-*- coding: utf-8 -*-
'''Podfetch scheduler service'''
from threading import Timer


_timer = None


def start(app, options):
    interval = options.daemon.update_interval * 60.0  # minutes to seconds

    def schedule():
        global _timer
        _timer = Timer(interval, tick)
        _timer.daemon = True
        _timer.start()

    def tick():
        app.update()
        schedule()

    schedule()


def stop():
    if _timer:
        _timer.cancel()
