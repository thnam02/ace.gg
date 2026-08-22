from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Player(Base):
    """Persisted player record. Seeded later; mock data is used for now."""

    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    riot_id: Mapped[str] = mapped_column(String(128), unique=True)
    team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str] = mapped_column(String(16))
    rank: Mapped[str] = mapped_column(String(32))
