from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select

from app.database.models import User
from app.database.razberi_models import (
    AIUsage,
    ErrorLog,
    Material,
    MaterialChunk,
    Metric,
    Project,
    ProjectMaterial,
    Reminder,
    UserStyle,
)
from app.processors.common import chunk_text, retrieve_chunks


def now_utc() -> datetime:
    return datetime.utcnow()


def is_active_pro(user: User) -> bool:
    return bool(user.is_pro and user.pro_until and user.pro_until > now_utc())


class UserService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    async def upsert(self, telegram_user):
        async with self.db.sessions() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == telegram_user.id))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name,
                    timezone=self.settings.default_timezone,
                )
                session.add(user)
            else:
                user.username = telegram_user.username
                user.first_name = telegram_user.first_name
                user.last_active_at = now_utc()
                if user.is_pro and user.pro_until and user.pro_until <= now_utc():
                    user.is_pro = False
            await session.commit()
            await session.refresh(user)
            return user

    async def by_telegram(self, telegram_id: int):
        async with self.db.sessions() as session:
            return (
                await session.execute(select(User).where(User.telegram_id == telegram_id))
            ).scalar_one_or_none()


class UsageService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    @staticmethod
    def _today_start() -> datetime:
        now = now_utc()
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def ai_count_today(self, user_id: int) -> int:
        async with self.db.sessions() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(AIUsage.id)).where(
                            AIUsage.user_id == user_id,
                            AIUsage.created_at >= self._today_start(),
                        )
                    )
                ).scalar_one()
            )

    async def feature_count_today(self, user_id: int, feature: str) -> int:
        async with self.db.sessions() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(AIUsage.id)).where(
                            AIUsage.user_id == user_id,
                            AIUsage.feature == feature,
                            AIUsage.created_at >= self._today_start(),
                        )
                    )
                ).scalar_one()
            )

    async def allowed(self, user: User, feature: str = 'ai') -> bool:
        del feature
        limit = self.settings.pro_daily_ai_limit if is_active_pro(user) else self.settings.free_daily_ai_limit
        return (await self.ai_count_today(user.id)) < limit

    async def record(self, user_id: int, model: str, feature: str, usage: dict | None = None):
        usage = usage or {}
        async with self.db.sessions() as session:
            session.add(
                AIUsage(
                    user_id=user_id,
                    model=(model or '')[:255],
                    feature=feature[:64],
                    input_tokens=int(usage.get('input', 0) or 0),
                    output_tokens=int(usage.get('output', 0) or 0),
                    estimated_cost=0.0,
                )
            )
            await session.commit()


class MaterialService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    async def create(
        self,
        user_id: int,
        type_: str,
        title: str,
        text: str,
        summary: str = '',
        telegram_file_id: str | None = None,
        file_unique_id: str | None = None,
        local_path: str | None = None,
    ):
        stored_text = (text or '')[: self.settings.max_material_chars]
        expires_at = now_utc() + timedelta(days=self.settings.material_ttl_days)
        async with self.db.sessions() as session:
            material = Material(
                user_id=user_id,
                type=type_[:32],
                title=(title or 'Материал')[:500],
                telegram_file_id=telegram_file_id,
                file_unique_id=file_unique_id,
                local_path=local_path,
                extracted_text=stored_text,
                summary=(summary or '')[:4000],
                expires_at=expires_at,
            )
            session.add(material)
            await session.flush()
            for index, chunk in enumerate(chunk_text(stored_text)):
                session.add(MaterialChunk(material_id=material.id, chunk_index=index, text=chunk))
            await session.commit()
            await session.refresh(material)
            return material

    async def get(self, user_id: int, material_id: int):
        async with self.db.sessions() as session:
            return (
                await session.execute(
                    select(Material).where(Material.id == material_id, Material.user_id == user_id)
                )
            ).scalar_one_or_none()

    async def by_file_unique(self, user_id: int, file_unique_id: str | None):
        if not file_unique_id:
            return None
        async with self.db.sessions() as session:
            return (
                await session.execute(
                    select(Material)
                    .where(Material.user_id == user_id, Material.file_unique_id == file_unique_id)
                    .order_by(Material.created_at.desc())
                )
            ).scalars().first()

    async def latest(self, user_id: int, limit: int = 10):
        async with self.db.sessions() as session:
            return list(
                (
                    await session.execute(
                        select(Material)
                        .where(Material.user_id == user_id)
                        .order_by(Material.created_at.desc())
                        .limit(limit)
                    )
                ).scalars()
            )

    async def context(self, user_id: int, material_id: int, query: str, limit: int | None = None) -> str:
        async with self.db.sessions() as session:
            material = (
                await session.execute(
                    select(Material).where(Material.id == material_id, Material.user_id == user_id)
                )
            ).scalar_one_or_none()
            if material is None:
                return ''
            chunks = list(
                (
                    await session.execute(
                        select(MaterialChunk)
                        .where(MaterialChunk.material_id == material.id)
                        .order_by(MaterialChunk.chunk_index)
                    )
                ).scalars()
            )
        selected = retrieve_chunks(
            [item.text for item in chunks],
            query,
            limit=limit or self.settings.retrieval_chunk_limit,
        )
        header = f'Название: {material.title}\nКратко: {material.summary}\n\n'
        return (header + '\n\n'.join(selected))[:32_000]

    async def delete(self, user_id: int, material_id: int) -> bool:
        async with self.db.sessions() as session:
            material = (
                await session.execute(
                    select(Material).where(Material.id == material_id, Material.user_id == user_id)
                )
            ).scalar_one_or_none()
            if material is None:
                return False
            local_path = material.local_path
            await session.execute(delete(ProjectMaterial).where(ProjectMaterial.material_id == material.id))
            await session.execute(delete(MaterialChunk).where(MaterialChunk.material_id == material.id))
            await session.delete(material)
            await session.commit()
        if local_path:
            try:
                Path(local_path).unlink(missing_ok=True)
            except OSError:
                pass
        return True

    async def delete_user_materials(self, user_id: int) -> int:
        materials = await self.latest(user_id, 10_000)
        for material in materials:
            await self.delete(user_id, material.id)
        return len(materials)

    async def cleanup_expired(self) -> int:
        async with self.db.sessions() as session:
            materials = list(
                (
                    await session.execute(
                        select(Material).where(
                            Material.expires_at.is_not(None),
                            Material.expires_at < now_utc(),
                        )
                    )
                ).scalars()
            )
        for material in materials:
            await self.delete(material.user_id, material.id)
        return len(materials)


class ProjectService:
    def __init__(self, db):
        self.db = db

    async def list(self, user_id: int):
        async with self.db.sessions() as session:
            return list(
                (
                    await session.execute(
                        select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
                    )
                ).scalars()
            )

    async def create(self, user_id: int, name: str):
        clean = ' '.join((name or '').split())[:120] or 'Новый проект'
        async with self.db.sessions() as session:
            existing = (
                await session.execute(select(Project).where(Project.user_id == user_id, Project.name == clean))
            ).scalar_one_or_none()
            if existing:
                return existing
            project = Project(user_id=user_id, name=clean)
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return project

    async def add_material(self, user_id: int, project_id: int, material_id: int) -> bool:
        async with self.db.sessions() as session:
            project = (
                await session.execute(select(Project).where(Project.id == project_id, Project.user_id == user_id))
            ).scalar_one_or_none()
            material = (
                await session.execute(select(Material).where(Material.id == material_id, Material.user_id == user_id))
            ).scalar_one_or_none()
            if not project or not material:
                return False
            existing = (
                await session.execute(
                    select(ProjectMaterial).where(
                        ProjectMaterial.project_id == project_id,
                        ProjectMaterial.material_id == material_id,
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(ProjectMaterial(project_id=project_id, material_id=material_id))
                await session.commit()
            return True

    async def materials(self, user_id: int, project_id: int):
        async with self.db.sessions() as session:
            project = (
                await session.execute(select(Project).where(Project.id == project_id, Project.user_id == user_id))
            ).scalar_one_or_none()
            if not project:
                return None, []
            rows = list(
                (
                    await session.execute(
                        select(Material)
                        .join(ProjectMaterial, ProjectMaterial.material_id == Material.id)
                        .where(ProjectMaterial.project_id == project_id, Material.user_id == user_id)
                        .order_by(ProjectMaterial.created_at.desc())
                    )
                ).scalars()
            )
            return project, rows


class StyleService:
    def __init__(self, db):
        self.db = db

    async def get(self, user_id: int) -> str:
        async with self.db.sessions() as session:
            row = (
                await session.execute(select(UserStyle).where(UserStyle.user_id == user_id))
            ).scalar_one_or_none()
            return (row.profile or '') if row else ''

    async def set(self, user_id: int, profile: str):
        clean = ' '.join((profile or '').split())[:1000]
        async with self.db.sessions() as session:
            row = (
                await session.execute(select(UserStyle).where(UserStyle.user_id == user_id))
            ).scalar_one_or_none()
            if row is None:
                row = UserStyle(user_id=user_id, profile=clean, sample_count=1)
                session.add(row)
            else:
                row.profile = clean
                row.sample_count += 1
                row.updated_at = now_utc()
            await session.commit()
        return clean


class MetricService:
    def __init__(self, db):
        self.db = db

    async def inc(self, name: str, user_id: int | None = None, value: int = 1):
        async with self.db.sessions() as session:
            session.add(Metric(name=name[:64], user_id=user_id, value=value))
            await session.commit()


class ErrorService:
    def __init__(self, db):
        self.db = db

    async def record(self, request_id: str, user_id: int | None, feature: str, error: Exception):
        async with self.db.sessions() as session:
            session.add(
                ErrorLog(
                    request_id=request_id[:64],
                    user_id=user_id,
                    feature=feature[:64],
                    error_type=type(error).__name__[:255],
                    message=str(error)[:1000],
                )
            )
            await session.commit()


class PrivacyService:
    def __init__(self, db, materials: MaterialService):
        self.db = db
        self.materials = materials

    async def delete_user_data(self, user_id: int) -> None:
        await self.materials.delete_user_materials(user_id)
        async with self.db.sessions() as session:
            projects = list((await session.execute(select(Project.id).where(Project.user_id == user_id))).scalars())
            if projects:
                await session.execute(delete(ProjectMaterial).where(ProjectMaterial.project_id.in_(projects)))
            await session.execute(delete(Project).where(Project.user_id == user_id))
            await session.execute(delete(UserStyle).where(UserStyle.user_id == user_id))
            await session.execute(delete(Reminder).where(Reminder.user_id == user_id))
            await session.execute(delete(AIUsage).where(AIUsage.user_id == user_id))
            await session.execute(delete(Metric).where(Metric.user_id == user_id))
            await session.commit()
