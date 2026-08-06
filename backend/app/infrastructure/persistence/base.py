from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, DateTime, func
from uuid import uuid4


def _now():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=_now, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=True)


class DeclarativeBase(DeclarativeBase):
    pass
