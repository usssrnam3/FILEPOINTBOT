from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Order, OrderStatus, Payment, PaymentStatus, Product, ProductType, User
from app.services.fulfillment import FulfillmentService
from app.services.payments.base import BasePaymentProvider


@dataclass(slots=True)
class CheckoutResult:
    order: Order
    payment: Payment
    product: Product


class CheckoutService:
    def __init__(
        self,
        payment_provider: BasePaymentProvider,
        fulfillment_service: FulfillmentService,
    ) -> None:
        self.payment_provider = payment_provider
        self.fulfillment_service = fulfillment_service

    async def create_checkout(
        self,
        session: AsyncSession,
        *,
        user: User,
        product: Product,
        customer_comment: str | None = None,
    ) -> CheckoutResult:
        order = Order(
            user_id=user.id,
            product_id=product.id,
            status=OrderStatus.PENDING_PAYMENT,
            amount=product.price_amount,
            currency=product.currency,
            customer_comment=customer_comment,
        )
        session.add(order)
        await session.flush()

        prepared = await self.payment_provider.prepare_payment(
            order_id=order.id,
            amount=product.price_amount,
            title=product.title,
        )
        payment = Payment(
            order_id=order.id,
            provider=self.payment_provider.code,
            provider_payment_id=prepared.provider_payment_id,
            status=PaymentStatus.PENDING,
            amount=product.price_amount,
            currency=product.currency,
            metadata_json=prepared.metadata,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(order)
        await session.refresh(payment)
        return CheckoutResult(order=order, payment=payment, product=product)

    async def complete_demo_payment(
        self,
        session: AsyncSession,
        *,
        bot: Bot,
        payment_id: int,
        telegram_user_id: int,
    ) -> tuple[Order, Product]:
        payment = await session.scalar(
            select(Payment)
            .where(Payment.id == payment_id)
            .options(
                selectinload(Payment.order)
                .selectinload(Order.product)
                .selectinload(Product.file),
                selectinload(Payment.order).selectinload(Order.user),
            )
        )
        if payment is None:
            raise ValueError("Платеж не найден.")

        order = payment.order
        if order.user.telegram_id != telegram_user_id:
            raise PermissionError("Этот платеж принадлежит другому пользователю.")
        if payment.status == PaymentStatus.SUCCEEDED:
            return order, order.product

        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = datetime.now(timezone.utc)
        order.status = OrderStatus.PAID
        order.paid_at = datetime.now(timezone.utc)
        await session.commit()

        await self.fulfillment_service.handle_paid_order(session, bot=bot, order_id=order.id)

        refreshed = await session.scalar(
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.product).selectinload(Product.file))
        )
        if refreshed is None:
            raise ValueError("Заказ не найден после оплаты.")
        return refreshed, refreshed.product

    async def list_user_orders(self, session: AsyncSession, *, telegram_user_id: int) -> list[Order]:
        query = (
            select(Order)
            .join(User)
            .where(User.telegram_id == telegram_user_id)
            .options(
                selectinload(Order.product).selectinload(Product.file),
                selectinload(Order.payment),
            )
            .order_by(Order.created_at.desc())
        )
        result = await session.scalars(query)
        return list(result.all())

    async def get_user_order(
        self,
        session: AsyncSession,
        *,
        order_id: int,
        telegram_user_id: int,
    ) -> Order | None:
        query = (
            select(Order)
            .join(User)
            .where(Order.id == order_id, User.telegram_id == telegram_user_id)
            .options(
                selectinload(Order.product).selectinload(Product.file),
                selectinload(Order.payment),
            )
        )
        return await session.scalar(query)

    async def redeliver_order(
        self,
        session: AsyncSession,
        *,
        bot: Bot,
        order_id: int,
        telegram_user_id: int,
    ) -> Order:
        order = await self.get_user_order(session, order_id=order_id, telegram_user_id=telegram_user_id)
        if order is None:
            raise ValueError("Заказ не найден.")
        if order.product.type != ProductType.DIGITAL:
            raise ValueError("Повторная выдача доступна только для цифровых товаров.")
        if order.status not in {OrderStatus.PAID, OrderStatus.FULFILLED}:
            raise ValueError("Файл можно получить только после оплаты.")

        await self.fulfillment_service.send_paid_file(session, bot=bot, order_id=order.id, mark_fulfilled=False)
        return order

