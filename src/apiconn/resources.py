"""REST resource conveniences implemented through ordinary operations."""

from dataclasses import dataclass
from .operations import MISSING, Operation, path_fields


def fields_body(json, fields):
    if json is not MISSING and fields:
        raise ValueError('select json or keyword fields, not both')
    return fields if json is MISSING else json


@dataclass(frozen=True, slots=True)
class Resource:
    api: object
    path: str

    def __post_init__(self):
        if path_fields(self.path):
            raise ValueError('resource collection path cannot contain fields')
        if not self.path.strip('/'):
            raise ValueError('resource collection path must be nonempty')

    def list(self, *, params=None):
        return self.api._execute(Operation('list', 'GET', self.path), params=params)

    def get(self, identifier, *, params=None):
        return self.api._execute(Operation('get', 'GET', self.path.rstrip('/') + '/{id}'), id=identifier, params=params)

    def create(self, *, json=MISSING, **fields):
        return self.api._execute(Operation('create', 'POST', self.path), json=fields_body(json, fields))

    def update(self, identifier, *, json=MISSING, **fields):
        return self.api._execute(Operation('update', 'PATCH', self.path.rstrip('/') + '/{id}'), id=identifier, json=fields_body(json, fields))

    def delete(self, identifier):
        return self.api._execute(Operation('delete', 'DELETE', self.path.rstrip('/') + '/{id}'), id=identifier)
