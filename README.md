# apiconn

Operation-first API connections over [requ](https://github.com/wispsy/requ).
Python 3.14+, MIT. HTTP transport stays in requ; connection authentication,
operations and REST resource conveniences live here.

```python
from apiconn import API

with API.rest('https://api.example.com/v1', token='selected-token') as api:
    users = api.resource('users')
    user = users.get(123)
    users.update(123, name='Ash')
    api.operation('activate_user', method='POST', path='users/{id}/activate')
    result = api.call('activate_user', id=123, json={'active': True})
```

Operation definitions are discoverable through `api.operations`, and `Connector`
is a small structural protocol. Input/output validators are optional callables
that raise on rejection. Values are finite JSON; there is no model framework or
provider discovery requirement. REST endpoints stay under the selected base URL.

Use `BearerAuth`, `BasicAuth` or `HeaderAuth` for explicit credentials. Clients
reject cross-origin redirects and never automatically retry mutations. Contexts
close owned transports; explicitly supplied requ clients remain caller-owned.
