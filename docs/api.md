# API contract

`API.rest(base_url, *, token=None, auth=None, headers=None, client=None)` selects a
synchronous REST connection. `API.graphql(endpoint_url, ...)` selects a GraphQL
endpoint. `AsyncAPI.rest` / `AsyncAPI.graphql` use `requ.AsyncClient`; their call,
request, query, mutate and resource methods are awaited. Pagination uses `async for`.
Python 3.14+ is required. The only runtime dependency is `requ>=0.1.0,<0.2.0`.

## Transport ownership

Contexts close transports they create. Supplied `requ.Client` / `AsyncClient`
instances remain caller-owned. Closing an API prevents new operations even when
its borrowed transport remains open. Sync APIs use `with` / `close`; async APIs
use `async with` / `await aclose()`.

To configure HTTP limits, supply an explicitly configured requ client:

```python
from apiconn import API
from requ import Client

with Client(timeout=5, max_bytes=1_000_000, max_connections=4) as transport:
    with API.rest('https://api.example.com/v1', client=transport) as api:
        result = api.resource('users').get(123)
```

requ owns TLS, pooling, query encoding, headers, byte/JSON bodies, framing and
transport errors. Its socket timeout is not a DNS or total deadline. Async I/O runs
in worker threads; cancellation stops waiting but a dispatched mutation can still
complete. There is no implicit retry, replay or rate-limit sleep. Reconcile remote
state before explicitly retrying any uncertain mutation.

## Operations and REST resources

`api.operation(name, *, method, path, description='', input_validator=None,
output_validator=None)` registers a frozen `Operation`. Duplicate names fail;
`api.operations` returns an ordered tuple. `Connector` / `AsyncConnector` are small
structural protocols exposing this inventory and `call`.

```python
api.operation('activate_user', method='POST', path='users/{id}/activate')
value = api.call('activate_user', id=123, json={'active': True})
```

`call(name, *, path_params=None, params=None, json=..., headers=None, **path_values)`
uses only a registered operation. Path values may be supplied as keywords or a
mapping, without duplicates. Names must exactly match simple template fields;
attribute access, formatting, empty/dot values and non-string/non-integer values
are rejected. Each value is URL quoted as a path component. `params` is passed to
requ and supports repeated keys. `json=None` sends JSON null; omitting JSON sends
no JSON body. `request(method, path, ...)` performs an explicit unregistered action.

Leading `/` on an endpoint is relative to the configured base path. Absolute URLs,
network paths, query/fragment text, backslashes, encoded template text and dot
segments fail. Static endpoint text is encoded automatically. Base URLs cannot
contain credentials, query strings or fragments. Cross-origin redirect clients
are rejected; requ also rejects HTTP downgrade. Redirects for mutation methods
remain non-2xx errors. These rules select an API origin, not an SSRF/network policy.

`api.resource('users')` provides:

| Method | Request |
| --- | --- |
| list(params=None) | GET users |
| get(identifier, params=None) | GET users/{id} |
| create(json=..., **fields) | POST users |
| update(identifier, json=..., **fields) | PATCH users/{id} |
| delete(identifier) | DELETE users/{id} |

Select either explicit JSON or keyword fields for create/update. Resource methods
return finite JSON, or None for an empty response. PUT and other conventions use
explicit operations. GraphQL has no generic resource CRUD interface.

Validators are `Callable[[JSONValue], None]`: return normally to accept, raise to
reject. Input validation occurs before dispatch; output validation follows JSON
parsing. No model/schema framework is required. Validators do not transform data.
Applications can compose frozen operation metadata with their own typed contracts.

## Credentials

Select `token='...'` as shorthand for `BearerAuth`, or pass `auth=BearerAuth(...)`,
`BasicAuth(username, password)` (UTF-8), or `HeaderAuth(name, value)`. Representations
redact credential values. An `Auth` protocol permits explicitly supplied policies
whose `headers()` returns a mapping. There is no environment credential lookup,
OAuth negotiation, token refresh or credential persistence. Common headers are
copied; per-call headers may override common headers case-insensitively, but cannot
override selected credential headers. requ reserves transport/framing headers.
Credentials travel in headers to the selected API origin. Use HTTPS for external
services. HTTP remains available for local services and deliberately selected APIs.

## GraphQL

```python
with API.graphql('https://api.example.com/graphql', token='selected-token') as api:
    data = api.query('query User($id: ID!) { user(id: $id) { name } }',
                     variables={'id': '123'}, operation_name='User')
```

`query(document, *, variables=None, operation_name=None)` and `mutate(...)` POST
the native GraphQL envelope. The document, not the method name, determines query
or mutation semantics; apiconn does not rewrite or parse GraphQL syntax. Variables
must contain finite JSON; operation names are GraphQL names. Successful calls
return `data` (object or null). Errors raise `GraphQLError` with `.errors`, optional
partial `.data`, and `.response`. HTTP failures stay `APIStatusError`; malformed
finite JSON or GraphQL envelopes raise `InvalidResponseError`.

## Explicit bounded pagination

Register a GET operation, then iterate items:

```python
from apiconn import CursorPagination, PagePagination

api.operation('users.list', method='GET', path='users')
for user in api.paginate('users.list', pagination=PagePagination(max_pages=20)):
    print(user)
```

`PagePagination(items_key='items', parameter='page', start=1, max_pages=100)`
expects an object containing an items array and stops on an empty array. It may
need one extra empty request after the last nonempty page. `CursorPagination(
items_key='items', parameter='cursor', next_cursor_key='next_cursor', start=None,
max_pages=100)` requires a next cursor string or explicit null on every page and
stops on null. Cursors are opaque query values, never navigable URLs. Repeated
cursors fail before another request. API-specific keys/initial state are explicit.

`paginate(name, *, pagination, params=None, **call_options)` owns its strategy's
query parameter; passing that same key in params fails. Strategies use top-level
JSON keys. Every page is bounded by requ; items are yielded without aggregating
all pages. A page-limit error may follow already yielded items. Limits cause an
error rather than silently claiming a complete collection. Only GET operations
are paginated in this release; GraphQL connections use explicit query calls.

## Errors

| Error | Meaning |
| --- | --- |
| APIStatusError (requ.HTTPStatusError) | Any non-2xx API status, including redirects; response preserved |
| InvalidResponseError (ValueError) | Invalid JSON media type, finite JSON or GraphQL envelope; response preserved |
| ValidationError (ValueError) | Selected input/output validator rejected the value; original error chained |
| GraphQLError (RuntimeError) | Native GraphQL errors, preserving partial data and response |
| PaginationError / PaginationLimitError (ValueError) | Invalid page, cursor cycle or exhausted bound |
| requ transport/limit/lifecycle errors | Propagate unchanged; inspect requ's contract |

Nonempty API responses must declare application/json or application/*+json.
Unknown operation names raise KeyError; invalid configuration/paths raise
TypeError or ValueError. No error automatically triggers another request.

## Extension scope

A Connector can expose explicit operations for a provider without importing other
Wispsy frameworks. Provider discovery, OpenAPI import, OAuth refresh, explicit retry
policies, model relationships, persistence and framework adapters remain future
work. This release does not claim universal third-party schema compatibility.
