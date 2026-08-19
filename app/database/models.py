from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default='Europe/Moscow')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_until: Mapped[datetime | None] = mapped_column(DateTime)
    free_limit: Mapped[int | None] = mapped_column(Integer)
    notification_settings: Mapped[str | None] = mapped_column(Text)
    watches: Mapped[list['Watch']] = relationship(back_populates='user', cascade='all, delete-orphan')


class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    source: Mapped[str] = mapped_column(String(255), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(12))
    seller: Mapped[str | None] = mapped_column(String(255))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    availability: Mapped[str] = mapped_column(String(32), default='unknown')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=720)
    check_status: Mapped[str] = mapped_column(String(32), default='pending')
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    watches: Mapped[list['Watch']] = relationship(back_populates='product', cascade='all, delete-orphan')
    history: Mapped[list['PriceHistory']] = relationship(back_populates='product', cascade='all, delete-orphan')


class Watch(Base):
    __tablename__ = 'watches'
    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='uq_watch_user_product'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    baseline_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notify_any_drop: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_new_low: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_in_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    user: Mapped[User] = relationship(back_populates='watches')
    product: Mapped[Product] = relationship(back_populates='watches')
    notifications: Mapped[list['Notification']] = relationship(back_populates='watch', cascade='all, delete-orphan')


class PriceHistory(Base):
    __tablename__ = 'price_history'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    availability: Mapped[str] = mapped_column(String(32), default='unknown')
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    product: Mapped[Product] = relationship(back_populates='history')


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey('watches.id', ondelete='CASCADE'), index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    watch: Mapped[Watch] = relationship(back_populates='notifications')


class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(255), unique=True)
    stars_amount: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default='active')


class ProviderError(Base):
    __tablename__ = 'provider_errors'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), index=True)
    url_host: Mapped[str] = mapped_column(String(255))
    error: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class MetricEvent(Base):
    __tablename__ = 'metric_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
