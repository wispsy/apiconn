"""Explicit REST page/cursor strategies with finite request bounds."""

from dataclasses import dataclass


class PaginationError(ValueError):
    """A page shape, cursor or pagination policy is invalid."""


class PaginationLimitError(PaginationError):
    """The selected page count was exhausted before completion."""


def _configure(strategy):
    for name in ('items_key', 'parameter'):
        value = getattr(strategy, name)
        if not isinstance(value, str) or not value:
            raise ValueError('pagination keys must be nonempty strings')
    if isinstance(strategy.max_pages, bool) or not isinstance(strategy.max_pages, int) or strategy.max_pages < 1:
        raise ValueError('max_pages must be a positive integer')


def items(document, key: str) -> list:
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        raise PaginationError('page must contain the configured items array')
    return document[key]


@dataclass(frozen=True, slots=True)
class PagePagination:
    items_key: str = 'items'
    parameter: str = 'page'
    start: int = 1
    max_pages: int = 100

    def __post_init__(self):
        _configure(self)
        if isinstance(self.start, bool) or not isinstance(self.start, int) or self.start < 0:
            raise ValueError('start must be a nonnegative integer')

    def next(self, document, state):
        return state + 1 if items(document, self.items_key) else None


@dataclass(frozen=True, slots=True)
class CursorPagination:
    items_key: str = 'items'
    parameter: str = 'cursor'
    next_cursor_key: str = 'next_cursor'
    start: str | None = None
    max_pages: int = 100

    def __post_init__(self):
        _configure(self)
        if not isinstance(self.next_cursor_key, str) or not self.next_cursor_key:
            raise ValueError('next cursor key must be nonempty')
        if self.start is not None and (not isinstance(self.start, str) or not self.start):
            raise ValueError('start cursor must be a nonempty string or None')

    def next(self, document, state):
        if self.next_cursor_key not in document:
            raise PaginationError('page is missing its configured next cursor')
        cursor = document[self.next_cursor_key]
        if cursor is not None and (not isinstance(cursor, str) or not cursor):
            raise PaginationError('next cursor must be a nonempty string or null')
        return cursor


def parameters(strategy, params):
    if not isinstance(strategy, (PagePagination, CursorPagination)):
        raise TypeError('select a page or cursor pagination strategy')
    result = dict(params or {})
    if strategy.parameter in result:
        raise ValueError('pagination owns its configured query parameter')
    return result


def advance(strategy, document, state, seen):
    next_state = strategy.next(document, state)
    if next_state is not None and next_state in seen:
        raise PaginationError('pagination cursor cycle')
    seen.add(next_state)
    return next_state
