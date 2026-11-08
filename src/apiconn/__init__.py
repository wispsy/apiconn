"""Operation-first API connections over requ."""

from .auth import Auth, BasicAuth, BearerAuth, HeaderAuth
from .client import API, Connector
from .operations import APIStatusError, InvalidResponseError, Operation, ValidationError
from .resources import Resource

__version__ = '0.1.0'
__all__ = ['API', 'Connector', 'Operation', 'Resource', 'Auth', 'BasicAuth', 'BearerAuth',
           'HeaderAuth', 'APIStatusError', 'InvalidResponseError', 'ValidationError']
