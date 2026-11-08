"""Explicit operation definitions and JSON boundary validation."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import re
from string import Formatter
from urllib.parse import quote

from requ import HTTPStatusError, JSONValue, Response, encode_json

MISSING = object()
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]*\Z')
_FIELD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_METHOD = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
type Validator = Callable[[JSONValue], None]


class ValidationError(ValueError):
    """A selected input/output validator rejected a value."""


class InvalidResponseError(ValueError):
    def __init__(self, message: str, response: Response):
        self.response = response
        super().__init__(message)


class APIStatusError(HTTPStatusError):
    """An API operation returned a non-2xx status, including redirects."""


def path_fields(path: str) -> tuple[str, ...]:
    if not isinstance(path, str):
        raise TypeError('operation path must be a string')
    if path.startswith('//') or any(c in path for c in ('?', '#', '\\', '%')) or any(ord(c) <= 32 or ord(c) == 127 for c in path):
        raise ValueError('path must be an unencoded relative endpoint without query or fragment')
    if '://' in path or any(part in {'.', '..'} for part in path.split('/')):
        raise ValueError('absolute URLs and dot path segments are forbidden')
    fields = []
    for _, name, spec, conversion in Formatter().parse(path):
        if name is not None:
            if not _FIELD.fullmatch(name) or spec or conversion:
                raise ValueError('path fields must be simple names without formatting')
            fields.append(name)
    return tuple(dict.fromkeys(fields))


def endpoint(base: str, path: str, values: Mapping | None = None) -> str:
    fields = path_fields(path)
    values = dict(values or {})
    if set(values) != set(fields):
        raise ValueError('path parameters must exactly match the operation fields')
    quoted = {}
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise TypeError('path values must be strings or integers')
        text = str(value)
        if not text or text in {'.', '..'}:
            raise ValueError('empty and dot path values are forbidden')
        quoted[name] = quote(text, safe='')
    pieces = []
    for literal, name, _, _ in Formatter().parse(path):
        pieces.append(quote(literal, safe="/:@-._~!$&'()*+,;="))
        if name is not None:
            pieces.append(quoted[name])
    suffix = ''.join(pieces).lstrip('/')
    return base + ('/' + suffix if suffix else '')


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    method: str
    path: str
    description: str = ''
    input_validator: Validator | None = field(default=None, repr=False, compare=False)
    output_validator: Validator | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError('operation name must be a simple nonempty identifier')
        if not isinstance(self.method, str) or not _METHOD.fullmatch(self.method) or self.method.upper() in {'CONNECT', 'TRACE'}:
            raise ValueError('unsupported operation method')
        object.__setattr__(self, 'method', self.method.upper())
        path_fields(self.path)
        for validator in (self.input_validator, self.output_validator):
            if validator is not None and not callable(validator):
                raise TypeError('validators must be callable')

    def validate_input(self, value):
        if value is not MISSING:
            encode_json(value)
        if self.input_validator is not None:
            if value is MISSING:
                raise ValidationError('operation requires JSON input')
            validate(self.input_validator, value, 'input')


def validate(validator: Validator | None, value: JSONValue, direction: str) -> None:
    if validator is not None:
        try:
            validator(value)
        except Exception as error:
            raise ValidationError(f'operation {direction} validation failed') from error


def decode_response(response: Response) -> JSONValue:
    if not 200 <= response.status < 300:
        raise APIStatusError(response)
    if not response.body:
        return None
    media = (response.header('content-type') or '').split(';', 1)[0].strip().lower()
    if media != 'application/json' and not (media.startswith('application/') and media.endswith('+json')):
        raise InvalidResponseError('API response must declare a JSON media type', response)
    try:
        return response.json()
    except (ValueError, TypeError, RecursionError) as error:
        raise InvalidResponseError('API response contains invalid finite JSON', response) from error
