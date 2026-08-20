from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Material(Base):
    __tablename__ = 'razberi_materials'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    telegram_file_id: Mapped[str | None] = mapped_column(String(512))
    file_unique_id: Mapped[str | None] = mapped_column(String(512), index=True)
    local_path: Mapped[str | None] = mapped_column(String(1000))
    extracted_text: Mapped[str] = mapped_column(Text, default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(32), default='ready', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class MaterialChunk(Base):
    __tablename__ = 'razberi_material_chunks'
    __table_args__ = (UniqueConstraint('material_id', 'chunk_index', name='uq_razberi_material_chunk'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey('razberi_materials.id', ondelete='CASCADE'), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Project(Base):
    __tablename__ = 'razberi_projects'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ProjectMaterial(Base):
    __tablename__ = 'razberi_project_materials'
    __table_args__ = (UniqueConstraint('project_id', 'material_id', name='uq_razberi_project_material'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('razberi_projects.id', ondelete='CASCADE'), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey('razberi_materials.id', ondelete='CASCADE'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserStyle(Base):
    __tablename__ = 'razberi_user_styles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True)
    profile: Mapped[str] = mapped_column(Text, default='')
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ConversationState(Base):
    __tablename__ = 'clarify_conversation_states'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AIUsage(Base):
    __tablename__ = 'razberi_ai_usage'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(64), default='openai-compatible')
    model: Mapped[str] = mapped_column(String(255), default='')
    feature: Mapped[str] = mapped_column(String(64), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Reminder(Base):
    __tablename__ = 'razberi_reminders'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class RazberiSubscription(Base):
    __tablename__ = 'razberi_subscriptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    telegram_charge_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default='active', index=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RazberiPayment(Base):
    __tablename__ = 'razberi_payments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    telegram_charge_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), default='XTR')
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default='paid', index=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Metric(Base):
    __tablename__ = 'razberi_metrics'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    value: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ErrorLog(Base):
    __tablename__ = 'razberi_errors'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    feature: Mapped[str] = mapped_column(String(64), index=True)
    error_type: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
