import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from requ import Client, ClientClosedError
from apiconn import API, APIStatusError, BasicAuth, BearerAuth, Connector, HeaderAuth, InvalidResponseError, ValidationError


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        self.respond()

    do_POST = do_GET
    do_PATCH = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET

    def respond(self):
        path = urlsplit(self.path).path
        size = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(size)) if size else None
        self.server.calls.append((self.command, path, payload, dict(self.headers)))
        if path == '/v1/cross':
            self.send_response(302)
            self.send_header('Location', f'http://localhost:{self.server.server_port}/v1/users')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        status = 404 if path == '/v1/missing' else 307 if path == '/v1/redirect' else 204 if self.command == 'DELETE' else 200
        result = {'method': self.command, 'path': path, 'body': payload,
                  'query': parse_qs(urlsplit(self.path).query), 'auth': self.headers.get('Authorization'),
                  'key': self.headers.get('X-Key')}
        body = b'' if status == 204 else b'not-json' if path == '/v1/bad-json' else json.dumps(result).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html' if path == '/v1/html' else 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.calls = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}/v1'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)

    def test_resource_crud_and_explicit_action(self):
        with API.rest(self.base, token='test-token') as api:
            self.assertIsInstance(api, Connector)
            users = api.resource('users')
            self.assertEqual(users.list(params={'q': 'a&é'})['query'], {'q': ['a&é']})
            self.assertEqual(users.get('a/b')['path'], '/v1/users/a%2Fb')
            self.assertEqual(users.create(name='Ash')['body'], {'name': 'Ash'})
            self.assertEqual(users.update(123, name='Ella')['method'], 'PATCH')
            self.assertIsNone(users.delete(123))
            operation = api.operation('activate_user', method='POST', path='/users/{id}/activate')
            self.assertEqual(api.operations, (operation,))
            result = api.call('activate_user', id=123, json={'active': True})
            self.assertEqual(result['path'], '/v1/users/123/activate')
            self.assertEqual(result['auth'], 'Bearer test-token')
            with self.assertRaises(ValueError):
                api.operation('activate_user', method='POST', path='x')
        with self.assertRaises(ClientClosedError):
            users.list()

    def test_auth_is_explicit_redacted_and_cannot_be_overridden(self):
        auths = [BearerAuth('test-token'), BasicAuth('user', 'password'), HeaderAuth('X-Key', 'private-value')]
        for auth in auths:
            self.assertNotIn('test-token', repr(auth))
            self.assertNotIn('password', repr(auth))
            self.assertNotIn('private-value', repr(auth))
            with API(self.base, auth=auth) as api:
                value = api.resource('users').get(1)
                if isinstance(auth, BasicAuth):
                    self.assertEqual(value['auth'], 'Basic ' + base64.b64encode(b'user:password').decode())
                elif isinstance(auth, HeaderAuth):
                    self.assertEqual(value['key'], 'private-value')
                else:
                    with self.assertRaises(ValueError):
                        api.request('GET', 'users', headers={'authorization': 'override'})
        with self.assertRaises(ValueError):
            BearerAuth('bad\r\ntoken')
        with self.assertRaises(ValueError):
            API(self.base, token='x', auth=auths[0])

    def test_paths_fail_before_network_and_preserve_origin(self):
        with API(self.base) as api, patch.object(api._client.__class__, 'request') as request:
            for path in ('https://evil.test/x', '//evil.test', '../admin', '/a/../b', '%2e%2e/admin', 'x?token=y', 'x#y', 'x\\y', '/{id.x}', '/{id!r}'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    api.request('GET', path)
            for value in ('.', '..', '', True, None):
                with self.assertRaises((TypeError, ValueError)):
                    api.request('GET', 'users/{id}', id=value)
            with self.assertRaises(ValueError):
                api.request('GET', 'users/{id}', other=1)
            request.assert_not_called()
        from requ import RedirectError
        with API(self.base, token='test-token') as api, self.assertRaises(RedirectError):
            api.request('GET', 'cross')
        with Client(allow_cross_origin_redirects=True) as client, self.assertRaises(ValueError):
            API(self.base, client=client)
        for base in ('file:///tmp', 'http://user:pass@example.test', self.base+'?x=1', self.base+'#fragment', self.base+'/../admin'):
            with self.assertRaises(ValueError):
                API(base)

    def test_status_and_invalid_json_preserve_response(self):
        with API(self.base) as api:
            for path, status in (('missing', 404), ('redirect', 307)):
                with self.assertRaises(APIStatusError) as raised:
                    api.request('POST', path, json={})
                self.assertEqual(raised.exception.response.status, status)
            for path in ('bad-json', 'html'):
                with self.assertRaises(InvalidResponseError) as raised:
                    api.request('GET', path)
                self.assertEqual(raised.exception.response.status, 200)

    def test_input_output_contracts_and_borrowed_client(self):
        def needs_name(value):
            if not isinstance(value, dict) or not isinstance(value.get('name'), str):
                raise ValueError('name required')
        with Client() as client:
            with API(self.base, client=client) as api:
                api.operation('create', method='POST', path='users', input_validator=needs_name)
                before = len(self.server.calls)
                for kwargs in ({}, {'json': {}}, {'json': {'name': 4}}):
                    with self.assertRaises(ValidationError):
                        api.call('create', **kwargs)
                self.assertEqual(len(self.server.calls), before)
                self.assertEqual(api.call('create', json={'name': 'Ash'})['body'], {'name': 'Ash'})
                api.operation('bad_output', method='GET', path='users', output_validator=needs_name)
                with self.assertRaises(ValidationError):
                    api.call('bad_output')
            self.assertEqual(client.get(self.base + '/users').status, 200)


if __name__ == '__main__':
    unittest.main()
