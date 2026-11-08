import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

from requ import AsyncClient, ClientClosedError, TransportError
from apiconn import (API, AsyncAPI, AsyncConnector, APIStatusError, CursorPagination,
                     GraphQLError, InvalidResponseError, PagePagination, PaginationError,
                     PaginationLimitError)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.respond()

    do_POST = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET

    def respond(self):
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        size = int(self.headers.get('Content-Length', 0))
        payload = json.loads(self.rfile.read(size)) if size else None
        self.server.calls.append((self.command, parts.path, query, payload))
        status = 200
        if parts.path == '/graphql':
            document = payload['query']
            if document == 'disconnect':
                self.close_connection = True
                return
            if document == 'partial':
                value = {'data': {'user': None}, 'errors': [{'message': 'denied', 'path': ['user']}]}
            elif document == 'invalid':
                value = {'data': []}
            elif document == 'bad-errors':
                value = {'errors': []}
            elif document == 'missing':
                value = {}
            else:
                value = {'data': {'echo': payload}}
            if document == 'http-error':
                status = 429
        elif parts.path == '/pages':
            page = int(query['page'][0])
            value = {'items': [page] if page < 3 else []}
        elif parts.path == '/endless':
            value = {'items': [1]}
        elif parts.path in {'/cursor', '/cycle', '/url-cursor'}:
            current = query.get('cursor', [None])[0]
            next_cursor = 'https://unselected.invalid/private' if parts.path == '/url-cursor' else 'two'
            value = {'items': [current], 'next_cursor': next_cursor if current is None or parts.path == '/cycle' else None}
        elif parts.path == '/bad-page':
            value = {'items': 'bad', 'next_cursor': None}
        elif parts.path == '/missing-cursor':
            value = {'items': []}
        else:
            value = {'method': self.command, 'body': payload, 'path': parts.path}
        body = b'' if self.command == 'DELETE' else json.dumps(value).encode()
        self.send_response(204 if self.command == 'DELETE' else status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Service:
    def start(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.calls = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)


class GraphQLPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = Service()
        cls.service.start()
        cls.base = cls.service.base

    @classmethod
    def tearDownClass(cls):
        cls.service.close()

    def test_graphql_native_documents_variables_and_partial_errors(self):
        with API.graphql(self.base + '/graphql', token='selected') as api:
            result = api.query('query User($id: ID!) { user(id: $id) { name } }', variables={'id': '123'}, operation_name='User')
            self.assertEqual(result['echo']['variables'], {'id': '123'})
            self.assertEqual(result['echo']['operationName'], 'User')
            self.assertEqual(api.mutate('mutation { activate }')['echo']['query'], 'mutation { activate }')
            with self.assertRaises(GraphQLError) as raised:
                api.query('partial')
            self.assertEqual(raised.exception.data, {'user': None})
            self.assertEqual(raised.exception.errors[0]['message'], 'denied')
            self.assertEqual(raised.exception.response.status, 200)
            with self.assertRaises(APIStatusError) as raised:
                api.query('http-error')
            self.assertEqual(raised.exception.response.status, 429)
            for document in ('invalid', 'bad-errors', 'missing'):
                with self.assertRaises(InvalidResponseError):
                    api.query(document)
            with self.assertRaises(ValueError):
                api.resource('users')
            with self.assertRaises(ValueError):
                api.query('')
            with self.assertRaises(ValueError):
                api.query('query { x }', variables={'x': float('nan')})
        with API(self.base) as api, self.assertRaises(ValueError):
            api.query('query { x }')

    def test_page_and_cursor_boundaries(self):
        with API(self.base) as api:
            for name in ('pages', 'cursor', 'cycle', 'endless', 'bad-page', 'missing-cursor', 'url-cursor'):
                api.operation(name, method='GET', path=name)
            self.assertEqual(list(api.paginate('pages', pagination=PagePagination(max_pages=3))), [1, 2])
            self.assertEqual(list(api.paginate('cursor', pagination=CursorPagination(max_pages=2))), [None, 'two'])
            before = len(self.service.server.calls)
            self.assertEqual(list(api.paginate('url-cursor', pagination=CursorPagination())), [None, 'https://unselected.invalid/private'])
            self.assertTrue(all(call[1] == '/url-cursor' for call in self.service.server.calls[before:]))
            before = len(self.service.server.calls)
            with self.assertRaises(PaginationLimitError):
                list(api.paginate('endless', pagination=PagePagination(max_pages=2)))
            self.assertEqual(len(self.service.server.calls) - before, 2)
            for name, strategy in [('cycle', CursorPagination()), ('bad-page', PagePagination()), ('missing-cursor', CursorPagination())]:
                with self.assertRaises(PaginationError):
                    list(api.paginate(name, pagination=strategy))
            with self.assertRaises(ValueError):
                list(api.paginate('pages', pagination=PagePagination(), params={'page': 9}))
            api.operation('mutation', method='POST', path='pages')
            with self.assertRaises(ValueError):
                list(api.paginate('mutation', pagination=PagePagination()))
        for options in ({'max_pages': 0}, {'max_pages': True}, {'start': -1}):
            with self.assertRaises(ValueError):
                PagePagination(**options)

    def test_graphql_failure_is_never_replayed(self):
        before = len(self.service.server.calls)
        with API.graphql(self.base + '/graphql') as api, self.assertRaises(TransportError):
            api.mutate('disconnect')
        self.assertEqual(len(self.service.server.calls) - before, 1)


class AsyncAPITests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = Service()
        cls.service.start()
        cls.base = cls.service.base

    @classmethod
    def tearDownClass(cls):
        cls.service.close()

    async def test_async_resources_actions_pagination_and_borrowed_lifecycle(self):
        async with AsyncClient(max_connections=1) as client:
            async with AsyncAPI.rest(self.base, client=client) as api:
                self.assertIsInstance(api, AsyncConnector)
                users = api.resource('users')
                self.assertEqual((await users.list())['method'], 'GET')
                self.assertEqual((await users.get('a/b'))['path'], '/users/a%2Fb')
                self.assertEqual((await users.create(name='Ash'))['body'], {'name': 'Ash'})
                self.assertEqual((await users.update(1, name='Ella'))['method'], 'PATCH')
                self.assertIsNone(await users.delete(1))
                api.operation('pages', method='GET', path='pages')
                result = [item async for item in api.paginate('pages', pagination=PagePagination(max_pages=3))]
                self.assertEqual(result, [1, 2])
                api.operation('cursor', method='GET', path='cursor')
                self.assertEqual([item async for item in api.paginate('cursor', pagination=CursorPagination())], [None, 'two'])
            with self.assertRaises(ClientClosedError):
                await api.request('GET', 'users')
            self.assertEqual((await client.get(self.base)).status, 200)
        async with AsyncAPI.rest(self.base) as owned:
            self.assertEqual((await owned.request('GET', 'users'))['method'], 'GET')
        with self.assertRaises(ClientClosedError):
            await owned._client.get(self.base)
        async with AsyncClient(allow_cross_origin_redirects=True) as client:
            with self.assertRaises(ValueError):
                AsyncAPI(self.base, client=client)

    async def test_async_graphql_errors_and_no_replay(self):
        async with AsyncAPI.graphql(self.base + '/graphql') as api:
            self.assertEqual((await api.query('query { x }'))['echo']['query'], 'query { x }')
            self.assertEqual((await api.mutate('mutation { x }'))['echo']['query'], 'mutation { x }')
            with self.assertRaises(GraphQLError):
                await api.query('partial')
            before = len(self.service.server.calls)
            with self.assertRaises(TransportError):
                await api.mutate('disconnect')
            self.assertEqual(len(self.service.server.calls) - before, 1)


if __name__ == '__main__':
    unittest.main()
