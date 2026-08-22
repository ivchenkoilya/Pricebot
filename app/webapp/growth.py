from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.database.razberi_models import Material, Project, Reminder
from app.services.core import bonus_requests
from app.services.growth import build_referral_link
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-growth'])


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


@router.get('/profile/stats')
async def profile_stats(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    """Profile counters plus referral data used by both Home and Profile Mini App views."""
    ctx = runtime_context(request)
    user = await ctx.users.upsert(_tg_namespace(tg))

    async with ctx.db.sessions() as db:
        materials = int((await db.execute(select(func.count(Material.id)).where(Material.user_id == user.id))).scalar_one())
        projects = int((await db.execute(select(func.count(Project.id)).where(Project.user_id == user.id))).scalar_one())
        reminders = int((await db.execute(select(func.count(Reminder.id)).where(Reminder.user_id == user.id))).scalar_one())

    ai_today = await ctx.usage.ai_count_today(user.id)
    referral = await ctx.growth.stats(user.id)
    me = await ctx.bot.get_me()
    referral_link = build_referral_link(me.username or '', int(user.telegram_id))

    return {
        # Existing AppV1 contract — this endpoint was referenced by the UI but
        # did not previously exist in the connected FastAPI routers.
        'materials': materials,
        'projects': projects,
        'reminders': reminders,
        'ai_today': ai_today,
        # Growth additions consumed by ReferralProfileWidget.
        'invited': referral.invited_total,
        'activated': referral.rewarded_total,
        'earned_requests': referral.earned_requests,
        'bonus_requests': bonus_requests(user),
        'referral_bonus': int(ctx.settings.referral_bonus_requests),
        'referral_link': referral_link,
        'source': referral.source,
        'campaign': referral.campaign,
    }
