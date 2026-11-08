"""Operation-first API connections with explicit transport ownership."""

from collections.abc import Mapping
import re
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from requ import Client, ClientClosedError, JSONValue

from .auth import Auth, BearerAuth
from .operations import MISSING, Operation, decode_response, endpoint, path_fields, validate

_HEADER = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")


def base_url(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError('base URL must be a string')
    if not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError('base URL must be ASCII without whitespace or controls')
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError('absolute HTTP(S) base URL without credentials required')
    if parts.query or parts.fragment or '\\' in parts.netloc or '%' in parts.netloc:
        raise ValueError('base URL cannot contain query, fragment or invalid authority')
    if parts.port is not None and not 1 <= parts.port <= 65535:
        raise ValueError('invalid base URL port')
    path_fields(parts.path)
    if '{' in parts.path or '}' in parts.path:
        raise ValueError('base URL cannot contain path parameters')
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip('/'), '', ''))


def merge_headers(*sources: Mapping[str, str] | None) -> dict[str, str]:
    result = {}
    for source in sources:
        if source is None:
            continue
        if not isinstance(source, Mapping):
            raise TypeError('headers must be mappings')
        seen = set()
        for name, value in source.items():
            if not isinstance(name, str) or not _HEADER.fullmatch(name) or not isinstance(value, str):
                raise ValueError('invalid header name or value')
            if any(ord(c) < 32 or ord(c) == 127 or ord(c) > 255 for c in value):
                raise ValueError('invalid header value')
            key = name.lower()
            if key in seen:
                raise ValueError('duplicate case-insensitive header')
            seen.add(key)
            result[key] = value
    return result


@runtime_checkable
class Connector(Protocol):
    @property
    def operations(self) -> tuple[Operation, ...]: ...

    def call(self, name: str, **kwargs) -> JSONValue: ...


class API:
    """Configured API origin; owns its client unless one is explicitly supplied."""

    def __init__(self, url: str, *, client: Client | None = None, auth: Auth | None = None,
                 token: str | None = None, headers: Mapping[str, str] | None = None):
        self._base = base_url(url)
        if token is not None:
            if auth is not None:
                raise ValueError('select auth or token, not both')
            auth = BearerAuth(token)
        self._auth = auth
        self._headers = merge_headers(headers)
        self._operations: dict[str, Operation] = {}
        self._owned = client is None
        self._client = Client() if client is None else client
        if self._client.allow_cross_origin_redirects:
            raise ValueError('API clients must forbid cross-origin redirects')
        self._closed = False

    @classmethod
    def rest(cls, url: str, **kwargs):
        return cls(url, **kwargs)

    @property
    def operations(self) -> tuple[Operation, ...]:
        return tuple(self._operations.values())

    def operation(self, name: str, *, method: str, path: str, **kwargs) -> Operation:
        operation = Operation(name, method, path, **kwargs)
        if name in self._operations:
            raise ValueError('operation is already registered')
        self._operations[name] = operation
        return operation

    def resource(self, path: str):
        from .resources import Resource
        return Resource(self, path)

    def _prepare(self, operation: Operation, *, path_params=None, params=None,
                 json=MISSING, headers=None, **path_values):
        if self._closed:
            raise ClientClosedError('API is closed')
        values = dict(path_params or {})
        if set(values) & set(path_values):
            raise ValueError('duplicate path parameter')
        values.update(path_values)
        url = endpoint(self._base, operation.path, values)
        operation.validate_input(json)
        selected = merge_headers(self._headers, headers)
        if self._auth is not None:
            credentials = merge_headers(self._auth.headers())
            if set(credentials) & set(selected):
                raise ValueError('credential headers cannot be overridden')
            selected.update(credentials)
        options = {'headers': selected, 'params': params}
        if json is not MISSING:
            options['json'] = json
        return operation.method, url, options

    def _execute(self, operation: Operation, **kwargs) -> JSONValue:
        method, url, options = self._prepare(operation, **kwargs)
        response = self._client.request(method, url, **options)
        value = decode_response(response)
        validate(operation.output_validator, value, 'output')
        return value

    def call(self, name: str, **kwargs) -> JSONValue:
        return self._execute(self._operations[name], **kwargs)

    def request(self, method: str, path: str, **kwargs) -> JSONValue:
        return self._execute(Operation('request', method, path), **kwargs)

    def close(self) -> None:
        self._closed = True
        if self._owned:
            self._client.close()

    def __enter__(self):
        if self._closed:
            raise ClientClosedError('API is closed')
        return self

    def __exit__(self, *exc) -> None:
        self.close()
