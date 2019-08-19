#-*- coding: utf-8 -*-
'''HTTP API for podfetch.'''

import cherrypy

# maps URL patterns to class names
URLS = (
    '/api/app/update', '_Update',
    #'/api/subscriptions/(.+)', '_Subscription',
    #'/api/episodes/(.+)', '_Episode',
)

class Web:

    def __init__(self, app, options):
        self._podfetch = app

    def startup(self):
        # read config and find out which interface to listen to
        port = 8080

        # urls
        # /app
        # /subscriptions
        # /subscription/NAME

        conf = {'/':
            {
                'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            }
        }
        cherrypy.quickstart(_Root(self._podfetch), '/', conf)

    def shutdown(self):
        pass


@cherrypy.expose
class _Root:

    def __init__(self, podfetch):
        self.subscriptions = _Subscriptions(podfetch)
        self.subscription = _Subscription(podfetch)


@cherrypy.expose
class _Update:

    def POST(self):
        pass


@cherrypy.expose
class _Subscriptions:

    def __init__(self, podfetch):
        self._podfetch = podfetch

    #@cherrypy.tools.json_out()
    def GET(self):
        result = [s for s in self._podfetch.iter_subscriptions()]
        return str(result)  # TODO: JSON


@cherrypy.expose
class _Subscription:

    def __init__(self, podfetch):
        self._podfetch = podfetch

    #@cherrypy.tools.json_out()
    def GET(self, name):
        sub = self._podfetch.subscription_for_name(name)
        return str(sub)

    def POST(self, name):
        if not name:
            raise ValueError('Name must not be empty')

        params = {}  # TODO: read json
        update_now = True  # TODO: from param
        url = params.pop('url')  # required
        self._podfetch.add_subscription(
            url,
            name=name,
            **params  # content_dir, max_episodes, filename_template
        )
        # return 201

    def PUT(self, name):
        params = {}  # TODO: read json
        move_files = False  # TODO: from param

        # explicitly read every param from the params-dict
        # so that we will get an error if a param is missing.
        self._podfetch.edit(name,
            url=params['url'],
            title=params['title'],
            enabled=params['enabled'],
            max_episodes=params['max_episodes'],
            filename_template=params['filename_template'],
            content_dir=params['content_dir'],
            move_files=move_files
        )
        # return 204

    def PATCH(self, name):
        params = {}  # TODO: read json
        # TODO: maybe clean params and complain if invalid
        allowed = ('name', 'url', 'title', 'enabled', 'max_episodes',
            'filename_template', 'content_dir')
        # do not allow name change through Rest API
        try:
            del params['name']
        except KeyError:
            pass

        move_files = False  # TODO: from param
        params['move_files'] = move_files
        self._podfetch.edit(name, **params)
        #TODO return 204

    def DELETE(self, name):
        delete_content = False  # TODO: param
        #self._podfetch.remove_subscription(name, delete_content=delete_content)
        #TODO return 204


@cherrypy.expose
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
