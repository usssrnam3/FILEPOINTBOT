from datetime import datetime, timezone

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserService:
    async def sync_user(self, session: AsyncSession, telegram_user: TelegramUser) -> User:
        query = select(User).where(User.telegram_id == telegram_user.id)
        user = await session.scalar(query)
        if user is None:
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                last_seen_at=datetime.now(timezone.utc),
            )
            session.add(user)
        else:
            user.username = telegram_user.username
            user.first_name = telegram_user.first_name
            user.last_name = telegram_user.last_name
            user.last_seen_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(user)
        return user

