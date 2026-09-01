from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.player_map_stats import PlayerMapStats


class Agent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))

    map_stats: Mapped[list[PlayerMapStats]] = relationship(
        "PlayerMapStats",
        back_populates="agent",
    )
