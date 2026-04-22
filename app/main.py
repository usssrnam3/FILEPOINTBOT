import asyncio
import logging

from aiogram import Bot
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import Redis

from app.bot.setup import setup_dispatcher
from app.config.settings import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.container import AppContainer
from app.services.file_storage import FileStorage
from app.services.payments.base import DemoPaymentProvider


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    settings = get_settings()

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    storage = RedisStorage.from_url(
        settings.redis_url,
        key_builder=DefaultKeyBuilder(with_bot_id=True),
    )
    file_storage = FileStorage(settings.storage_dir)

    payment_provider = DemoPaymentProvider()
    container = AppContainer(
        settings=settings,
        session_factory=session_factory,
        redis=redis,
        storage=file_storage,
        payment_provider=payment_provider,
    )

    bot = Bot(token=settings.bot_token)
    dispatcher = setup_dispatcher(container, storage)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await storage.close()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
