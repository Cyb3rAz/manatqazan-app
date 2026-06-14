"""
ManatAds – SQLAlchemy ORM Models
=================================
Tables:
  • users          – Telegram user profiles + referral tracking.
  • watch_records  – Per-video reward ledger (audit trail).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ── helpers ─────────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Users ───────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("telegram_id", name="uq_users_telegram_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="az", server_default="az")

    # ── Economy ──
    balance_mc: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    total_earned_mc: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    videos_today: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_watch_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    welcome_bonus_claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    loyalty_bonus_claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # ── Sequential Cooldown Session Columns ──
    session_1_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    session_2_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    session_1_completion_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_notified: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # ── VIP Subscription ──
    # Values: "free" | "pro" | "elite" | "passive"
    vip_status: Mapped[str] = mapped_column(String(20), default="free", server_default="free")
    vip_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Passive Income Package ──
    passive_last_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    had_passive_vip: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # ── Referral ──
    referrer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=True, index=True
    )
    referral_earnings_mc: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    referral_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # ── Timestamps ──
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )

    # ── Relationships ──
    watch_records: Mapped[list["WatchRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="select"
    )
    user_tasks: Mapped[list["UserTask"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} balance={self.balance_mc:.2f} MC>"


# ── Watch Records ──────────────────────────────────────────────────────
class WatchRecord(Base):
    __tablename__ = "watch_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    reward_mc: Mapped[float] = mapped_column(Float, nullable=False)
    referrer_bonus_mc: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    referrer_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    adsgram_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # ── Relationships ──
    user: Mapped["User"] = relationship(back_populates="watch_records")

    def __repr__(self) -> str:
        return f"<WatchRecord user={self.telegram_id} reward={self.reward_mc} MC>"


# ── Tasks ──────────────────────────────────────────────────────────────
class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_url: Mapped[str] = mapped_column(String(255), nullable=False)
    reward_amount: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # ── Relationships ──
    user_tasks: Mapped[list["UserTask"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title} reward={self.reward_amount} MC>"


# ── User Tasks (Completion mapping) ────────────────────────────────────
class UserTask(Base):
    __tablename__ = "user_tasks"
    __table_args__ = (UniqueConstraint("user_id", "task_id", name="uq_user_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # ── Relationships ──
    user: Mapped["User"] = relationship(back_populates="user_tasks")
    task: Mapped["Task"] = relationship(back_populates="user_tasks")

    def __repr__(self) -> str:
        return f"<UserTask user_id={self.user_id} task_id={self.task_id}>"
