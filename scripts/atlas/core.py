"""Compatibility facade for the pre-0.4 persistence import path.

New code imports :mod:`atlas.infrastructure.store`. This module remains so old
integrations and cached extractor commands keep working during the migration.
"""

from .infrastructure.store import (  # noqa: F401
    Lock,
    SCHEMA,
    VERSION,
    Store,
    atomic,
    digest,
    encoded,
    envelope,
    filehash,
    payload,
    read,
    write,
)

__all__ = [
    "Lock", "SCHEMA", "VERSION", "Store", "atomic", "digest", "encoded",
    "envelope", "filehash", "payload", "read", "write",
]
