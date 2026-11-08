# apiconn

Operation-first REST and GraphQL API connections over
[requ](https://github.com/wispsy/requ). Python 3.14+, MIT.

```sh
pip install apiconn
```

```python
from apiconn import API

with API.rest('https://api.example.com/v1', token='selected-token') as api:
    users = api.resource('users')
    user = users.get(123)
    users.update(123, name='Ash')

    api.operation('activate_user', method='POST', path='users/{id}/activate')
    result = api.call('activate_user', id=123, json={'active': True})
```

```python
from apiconn import AsyncAPI

async def user_name():
    async with AsyncAPI.graphql('https://api.example.com/graphql') as api:
        data = await api.query('query { user { name } }')
        return data['user']['name']
```

- Explicit discoverable operations, optional input/output validators and Connector
  protocols. REST resource CRUD is a convenience over operations.
- Native GraphQL documents/variables, with partial data and errors preserved.
- Selected bearer/basic/header credentials, confined endpoints and finite JSON.
- Bounded page/cursor iteration with cycle detection and no automatic next-URL fetch.
- Sync and async interfaces with explicit owned/borrowed transport lifecycle.

HTTP methods, TLS, pooling, headers, timeouts and request/response bytes belong to
requ. Its async I/O runs in worker threads; canceling an await does not undo a
request already sent. Mutations are never automatically retried. No OAuth,
provider discovery, caching or persistence is installed implicitly.

See [the API contract](docs/api.md) for examples, bounds and error semantics.
Run [the local service example](examples/local_service.py) without external
credentials. `expose_api` serves APIs; apiconn consumes them. Other Wispsy packages
are optional consumers, not core dependencies.

Development: `uv sync`, then
`uv run python -W error::ResourceWarning -m unittest discover -s tests -v`.
Verify exact archives and independent installations with
`uv run python scripts/check_distribution.py`.
