"""Exercise REST and GraphQL without external accounts or credentials."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from apiconn import API, AsyncAPI


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.reply({'id': 123, 'name': 'Ash'})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.reply({'data': {'user': {'name': 'Ash'}}} if self.path == '/graphql' else body)

    def reply(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


async def query(base):
    async with AsyncAPI.graphql(base + '/graphql') as api:
        result = await api.query('query { user { name } }')
        assert result == {'user': {'name': 'Ash'}}
        print(result)


def main():
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with API.rest(base) as api:
                assert api.resource('users').get(123) == {'id': 123, 'name': 'Ash'}
                assert api.resource('users').create(name='Ella') == {'name': 'Ella'}
            asyncio.run(query(base))
        finally:
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    main()
