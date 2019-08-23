#-*- coding: utf-8 -*-
'''HTTP API for podfetch.'''
import itertools
import json
from json import JSONEncoder
import logging

import cherrypy

from podfetch.exceptions import NoSubscriptionError
from podfetch.model import Episode
from podfetch.model import Subscription
from podfetch.predicate import Filter


LOG = logging.getLogger(__name__)


# taken from cherrypy's default _json_inner_handler
# https://github.com/cherrypy/cherrypy/blob/master/cherrypy/lib/jsontools.py
def _json_encoder(*args, **kwargs):
    value = cherrypy.serving.request._json_inner_handler(*args, **kwargs)
    encoder = _PodfetchEncoder()
    for chunk in encoder.iterencode(value):
        yield chunk.encode('utf-8')


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
        cherrypy.config['tools.json_out.handler'] = _json_encoder
        cherrypy.quickstart(_Root(self._podfetch), '/', conf)

    def shutdown(self):
        pass


@cherrypy.expose
class _Root:

    def __init__(self, podfetch):
        self.subscriptions = _Subscriptions(podfetch)
        self.subscription = _Subscription(podfetch)
        self.episodes = _Episodes(podfetch)


@cherrypy.expose
class _Update:

    def POST(self):
        pass


@cherrypy.expose
class _Subscriptions:

    def __init__(self, podfetch):
        self._podfetch = podfetch

    @cherrypy.tools.json_out()
    def GET(self):
        result = [s for s in self._podfetch.iter_subscriptions()]
        return result


@cherrypy.expose
class _Subscription:

    def __init__(self, podfetch):
        self._podfetch = podfetch

    @cherrypy.tools.json_out(handler=_json_encoder)
    def GET(self, name):
        name = name.strip()

        with _APIError.handle(NoSubscriptionError, 404, 'Subscription not found'):
            return self._podfetch.subscription_for_name(name)

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, name):
        name = name.strip()
        params = cherrypy.request.json

        if not name:
            raise _APIError(400, 'Name must not be empty')

        with _APIError.handle(KeyError, 400, 'URL is required'):
            url = params.pop('url')  # required

        # name must be unique
        try:
            existing = self._podfetch.subscription_for_name(name)
            if existing:
                raise _APIError(409, 'Subscription %r already exists' % name)
        except NoSubscriptionError:
            pass

        with _APIError.handle(Exception, 400, 'Invalid parameters'):
            sub = self._podfetch.add_subscription(
                url,
                name=name,
                **params  # content_dir, max_episodes, filename_template
            )
            cherrypy.response.status = "201 Created"
            # TODO: this has no effect.
            # apparanetly, json_out sets the status code (back) to 200 Ok
            return sub

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PUT(self, name):
        name = name.strip()
        params = cherrypy.request.json

        if not name:
            raise _APIError(400, 'Name must not be empty')

        move_files = False  # TODO: from request param(?)

        with _APIError.handle(NoSubscriptionError, 404, 'Subscription not found'):
            # explicitly read every param from the params-dict
            # so that we will get an error if a param is missing.
            self._podfetch.edit(name,
                url=params['feed_url'],
                title=params['title'],
                enabled=params['enabled'],
                max_episodes=params['max_episodes'],
                filename_template=params['filename_template'],
                content_dir=params['content_dir'],
                move_files=move_files
            )

        return self._podfetch.subscription_for_name(name)

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PATCH(self, name):
        name = name.strip()
        params = cherrypy.request.json

        if not name:
            raise _APIError(400, 'Name must not be empty')

        # do not allow name change through Rest API
        try:
            del params['name']
        except KeyError:
            pass

        move_files = False  # TODO: from param
        params['move_files'] = move_files
        with _APIError.handle(NoSubscriptionError, 404, 'Subscription not found'):
            self._podfetch.edit(name, **params)

        return self._podfetch.subscription_for_name(name)

    def DELETE(self, name):
        delete_content = False  # TODO: param
        with _APIError.handle(NoSubscriptionError, 404, 'Subscription not found'):
            self._podfetch.remove_subscription(name, delete_content=delete_content)
        cherrypy.response.status = 204


@cherrypy.expose
class _Episodes:

    _DEFAULT_LIMIT = 10

    def __init__(self, podfetch):
        self._podfetch = podfetch

    @cherrypy.tools.json_out()
    def GET(self, limit=10):
        if limit:
            with _APIError.handle(TypeError, 400, 'Invalid value for limit'):
                limit = int(limit)
        else:
            limit = self._DEFAULT_LIMIT

        accept = Filter()

        # fetch ALL episodes
        episodes = [
            e for e in itertools.chain(*[
                s.episodes for s in self._podfetch.iter_subscriptions()
            ])
            if accept(e)
        ]

        # sort by date and fetch n newest
        episodes.sort(key=lambda e: e.pubdate, reverse=True)
        episodes = episodes[:limit]

        return episodes


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


class _APIError(cherrypy.HTTPError):
    # see
    # https://stackoverflow.com/questions/42816264/cherrypy-httperror-custom-response-handling-not-html
    # https://github.com/cherrypy/cherrypy/blob/master/cherrypy/_cperror.py

    def __init__(self, status, message=None):
        super().__init__(status=status, message=message)

    def set_response(self):
        response = cherrypy.serving.response
        response.status = self.status
        response.headers.pop('Content-Length', None)
        response.body = json.dumps({'message': self._message}).encode('utf-8')


class _PodfetchEncoder(JSONEncoder):

    _DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'

    def default(self, obj):
        LOG.debug('default: %r', obj)
        if isinstance(obj, Subscription):
            return self._encode_subscription(obj)
        elif isinstance(obj, Episode):
            return self._encode_episode(obj)
        else:
            return JSONEncoder.default(self, obj)

    def _encode_subscription(self, sub):
        return {
            'name': sub.name,
            'feed_url': sub.feed_url,
            'title': sub.title,
            'max_episodes': sub.max_episodes,
            'content_dir': sub.content_dir,
            'enabled': sub.enabled,
            'filename_template': sub.filename_template,
        }

    def _encode_episode(self, episode):
        data = {
            'id': episode.id,
            'subscription_name': episode.subscription.name,
            'title': episode.title,
            'description': episode.description,
            'files': episode.files,
        }
        if episode.published:
            data['pubdate'] = episode.published.strftime(_PodfetchEncoder._DATE_FORMAT)

        return data
