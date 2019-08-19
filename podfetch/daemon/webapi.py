#-*- coding: utf-8 -*-
'''HTTP API for podfetch.'''

import web

# maps URL patterns to class names
URLS = (
    '/api/app/update', '_Update',
    '/api/subscriptions/(.+)', '_Subscription',
    '/api/episodes/(.+)', '_Episode',
)

class Web:

    def __init__(self, app):
        self._podfetch = app

    def startup(self):
        # read config and find out which interface to listen to

        # setting the port
        # seems a little underdocumented,
        # but web.py will look for an environment variable PORT
        # this might be nice to set that variable ourselves(?)
        import os
        port = 8080
        if 'PORT' not in os.environ:
            os.environ['PORT'] = str(port)
        # start server and start listening
        webapp = web.application(URLS, globals())
        webapp.add_processor(self._inject_app)
        webapp.run()  # TODO: needs threading?

    def _inject_app(self, handler):
        web.ctx.podfetch = self._podfetch
        return hendler()

    def shutdown(self):
        pass


class _Update:

    def POST(self):
        pass


class _Subscriptions:

    def GET(self):
        app = web.ctx.podfetch
        result = [s for s in app.iter_subscriptions()]
        return str(result)  # TODO: JSON


class _Subscription:

    def GET(self, name):
        pass

    def POST(self, name):
        pass

    def PUT(self, name):
        pass

    def PATCH(self, name):
        pass

    def DELETE(self, name):
        pass


class _Episode:

    def __init__(self):
        pass

    def GET(self, id):
        pass

    def POST(self, id):
        pass

    def PUT(self, id):
        pass

    def PATCH(self, id):
        pass

    def DELETE(self, id):
        pass
