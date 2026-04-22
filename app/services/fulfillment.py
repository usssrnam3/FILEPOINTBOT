from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import FSInputFile
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import Settings
from app.db.models import Order, OrderStatus, Product, ProductType


class FulfillmentService:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    async def handle_paid_order(self, session: AsyncSession, *, bot: Bot, order_id: int) -> None:
        order = await session.scalar(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.user),
                selectinload(Order.product).selectinload(Product.file),
            )
        )
        if order is None:
            raise ValueError("Заказ не найден.")

        if order.product.type == ProductType.DIGITAL:
            await self.send_paid_file(session, bot=bot, order_id=order.id, mark_fulfilled=True)
            return

        for admin_id in self.settings.admin_ids:
            await bot.send_message(
                admin_id,
                (
                    "Новый оплаченный заказ на услугу\n"
                    f"Заказ #{order.id}\n"
                    f"Товар: {order.product.title}\n"
                    f"Пользователь: {order.user.first_name or order.user.username or order.user.telegram_id}\n"
                    f"Комментарий: {order.customer_comment or 'не указан'}"
                ),
            )
        await bot.send_message(
            order.user.telegram_id,
            (
                "Оплата получена. Заказ на услугу создан, администратор уже получил уведомление.\n"
                f"Номер заказа: #{order.id}"
            ),
        )

    async def send_paid_file(
        self,
        session: AsyncSession,
        *,
        bot: Bot,
        order_id: int,
        mark_fulfilled: bool,
    ) -> None:
        lock_key = f"deliver-order:{order_id}"
        lock_acquired = True
        if mark_fulfilled:
            lock_acquired = await self.redis.set(lock_key, "1", nx=True, ex=60)
            if not lock_acquired:
                return

        try:
            order = await session.scalar(
                select(Order)
                .where(Order.id == order_id)
                .options(
                    selectinload(Order.user),
                    selectinload(Order.product).selectinload(Product.file),
                )
            )
            if order is None:
                raise ValueError("Заказ не найден.")
            if order.product.file is None:
                order.status = OrderStatus.FAILED
                order.delivery_error = "Файл товара не найден."
                await session.commit()
                raise ValueError("Файл товара отсутствует.")

            file_input = FSInputFile(
                path=order.product.file.storage_path,
                filename=order.product.file.original_filename,
            )
            await bot.send_document(
                order.user.telegram_id,
                file_input,
                caption=f"Ваш оплаченный файл по заказу #{order.id}",
                protect_content=True,
            )
            if mark_fulfilled:
                order.status = OrderStatus.FULFILLED
                order.fulfilled_at = datetime.now(timezone.utc)
                order.delivery_error = None
                await session.commit()
        finally:
            if mark_fulfilled and lock_acquired:
                await self.redis.delete(lock_key)
