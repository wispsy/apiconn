"""Native GraphQL request envelopes and explicit partial-error results."""

from collections.abc import Mapping
import re
from requ import JSONValue, Response
from .operations import InvalidResponseError, decode_response


class GraphQLError(RuntimeError):
    """A valid GraphQL error result; partial data and response are preserved."""

    def __init__(self, errors: list, data: JSONValue, response: Response):
        self.errors = errors
        self.data = data
        self.response = response
        super().__init__(f'GraphQL returned {len(errors)} error(s)')


def payload(document: str, variables: Mapping | None, operation_name: str | None) -> dict:
    if not isinstance(document, str) or not document.strip():
        raise ValueError('GraphQL document must be a nonempty string')
    result = {'query': document}
    if variables is not None:
        if not isinstance(variables, Mapping):
            raise TypeError('GraphQL variables must be a mapping')
        result['variables'] = dict(variables)
    if operation_name is not None:
        if not isinstance(operation_name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', operation_name):
            raise ValueError('invalid GraphQL operation name')
        result['operationName'] = operation_name
    return result


def result(response: Response) -> JSONValue:
    value = decode_response(response)
    if not isinstance(value, dict) or not ({'data', 'errors'} & value.keys()):
        raise InvalidResponseError('invalid GraphQL response envelope', response)
    if 'data' in value and value['data'] is not None and not isinstance(value['data'], dict):
        raise InvalidResponseError('GraphQL data must be an object or null', response)
    if 'errors' in value:
        errors = value['errors']
        if not isinstance(errors, list) or not errors or any(not isinstance(e, dict) or not isinstance(e.get('message'), str) for e in errors):
            raise InvalidResponseError('invalid GraphQL errors', response)
        raise GraphQLError(errors, value.get('data'), response)
    return value['data']
