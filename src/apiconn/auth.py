"""Explicit credential policies; no ambient lookup or token refresh."""

import base64
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class Auth(Protocol):
    def headers(self) -> Mapping[str, str]: ...


@dataclass(frozen=True, slots=True)
class BearerAuth:
    token: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.token, str) or not self.token or not self.token.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in self.token):
            raise ValueError('bearer token must be nonempty ASCII without whitespace or controls')

    def headers(self) -> Mapping[str, str]:
        return {'Authorization': 'Bearer ' + self.token}


@dataclass(frozen=True, slots=True)
class BasicAuth:
    username: str = field(repr=False)
    password: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.username, str) or not isinstance(self.password, str):
            raise TypeError('basic credentials must be strings')
        if ':' in self.username or any(ord(c) < 32 or ord(c) == 127 for c in self.username + self.password):
            raise ValueError('invalid basic credentials')

    def headers(self) -> Mapping[str, str]:
        token = base64.b64encode(f'{self.username}:{self.password}'.encode('utf-8')).decode('ascii')
        return {'Authorization': 'Basic ' + token}


@dataclass(frozen=True, slots=True)
class HeaderAuth:
    name: str
    value: str = field(repr=False)

    def headers(self) -> Mapping[str, str]:
        return {self.name: self.value}
