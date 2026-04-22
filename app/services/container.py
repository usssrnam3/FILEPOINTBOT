from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.services.file_storage import FileStorage
from app.services.payments.base import BasePaymentProvider


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    storage: FileStorage
    payment_provider: BasePaymentProvider

