from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB


class BTrack(Base):
  __tablename__ = "btracks"

  id: Mapped[UUID] = mapped_column(
    PGUUID(as_uuid=True),
    primary_key=True,
    default=uuid4,
    index=True,
  )

  # user id
  reporter_id: Mapped[UUID] = mapped_column(
    PGUUID(as_uuid=True),
    nullable=False,
    index=True,
  )

  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
    nullable=False,
  )

  steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

  generation_prompt: Mapped[str] = mapped_column(Text, nullable=False)

  errors: Mapped[str] = mapped_column(Text, nullable=False)

  thread_turn_id: Mapped[UUID] = mapped_column(
    PGUUID(as_uuid=True),
    nullable=False,
  )

  cause: Mapped[str] = mapped_column(Text, nullable=True)

  fixed: Mapped[bool] = mapped_column(nullable=False, default=False)