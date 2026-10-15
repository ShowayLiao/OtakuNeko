"""Portable bindings for existing UTC timestamps stored without timezone."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCNaiveDateTime(TypeDecorator[datetime]):
    """Normalize aware inputs to UTC while retaining the existing naive schema."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
