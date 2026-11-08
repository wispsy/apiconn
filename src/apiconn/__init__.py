"""Operation-first API connections over requ."""

from .auth import Auth, BasicAuth, BearerAuth, HeaderAuth
from .client import API, AsyncAPI, AsyncConnector, Connector
from .operations import APIStatusError, InvalidResponseError, Operation, ValidationError
from .resources import AsyncResource, Resource
from .graphql import GraphQLError
from .pagination import CursorPagination, PagePagination, PaginationError, PaginationLimitError

__version__ = '0.1.0'
__all__ = ['AsyncAPI', 'AsyncConnector', 'AsyncResource', 'GraphQLError', 'PagePagination',
           'CursorPagination', 'PaginationError', 'PaginationLimitError', 'API', 'Connector', 'Operation', 'Resource', 'Auth', 'BasicAuth', 'BearerAuth',
           'HeaderAuth', 'APIStatusError', 'InvalidResponseError', 'ValidationError']
