from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as TelegramUser

from app.bot.keyboards.common import (
    catalog_keyboard,
    main_menu_keyboard,
    order_keyboard,
    orders_keyboard,
    payment_keyboard,
    product_keyboard,
)
from app.bot.states.checkout import ServiceCheckoutState
from app.db.models import ProductType
from app.services.catalog import CatalogService
from app.services.checkout import CheckoutService
from app.services.container import AppContainer
from app.services.fulfillment import FulfillmentService
from app.services.users import UserService
from app.utils.formatting import format_price

router = Router(name="user")

catalog_service = CatalogService()
user_service = UserService()


def build_checkout_service(container: AppContainer) -> CheckoutService:
    fulfillment_service = FulfillmentService(container.redis, container.settings)
    return CheckoutService(container.payment_provider, fulfillment_service)


def status_label(status: str) -> str:
    return {
        "pending_payment": "ожидает оплаты",
        "paid": "оплачен",
        "fulfilled": "выдан",
        "cancelled": "отменен",
        "failed": "ошибка",
    }.get(status, status)


@router.message(CommandStart())
async def cmd_start(message: Message, container: AppContainer) -> None:
    if message.from_user is None:
        return
    async with container.session_factory() as session:
        await user_service.sync_user(session, message.from_user)
    await message.answer(
        (
            "Добро пожаловать в магазин цифровых файлов и услуг.\n"
            "Здесь можно посмотреть каталог, оплатить товар и сразу получить файл в Telegram."
        ),
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("catalog"))
@router.message(F.text == "Каталог")
async def show_catalog(message: Message, container: AppContainer) -> None:
    if message.from_user is None:
        return
    async with container.session_factory() as session:
        await user_service.sync_user(session, message.from_user)
        products = await catalog_service.list_active_products(session)
    if not products:
        await message.answer("Каталог пока пуст. Попробуйте позже.")
        return
    await message.answer("Доступные товары:", reply_markup=catalog_keyboard(products))


@router.callback_query(F.data == "catalog:open")
async def open_catalog_callback(callback: CallbackQuery, container: AppContainer) -> None:
    async with container.session_factory() as session:
        products = await catalog_service.list_active_products(session)
    if not products:
        await callback.message.edit_text("Каталог пока пуст.")
        await callback.answer()
        return
    await callback.message.edit_text("Доступные товары:", reply_markup=catalog_keyboard(products))
    await callback.answer()


@router.callback_query(F.data.startswith("product:"))
async def show_product(callback: CallbackQuery, container: AppContainer) -> None:
    product_id = int(callback.data.split(":")[1])
    async with container.session_factory() as session:
        product = await catalog_service.get_product(session, product_id)
    if product is None or not product.is_active:
        await callback.answer("Товар недоступен.", show_alert=True)
        return
    type_label = "файл" if product.type == ProductType.DIGITAL else "услугу"
    text = (
        f"{product.title}\n\n"
        f"{product.description}\n\n"
        f"Цена: {format_price(product.price_amount, product.currency)}\n"
        f"Тип: {'Цифровой товар' if product.type == ProductType.DIGITAL else 'Услуга'}"
    )
    await callback.message.edit_text(text, reply_markup=product_keyboard(product.id, type_label))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_product(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if callback.from_user is None:
        return
    product_id = int(callback.data.split(":")[1])
    async with container.session_factory() as session:
        product = await catalog_service.get_product(session, product_id)
    if product is None or not product.is_active:
        await callback.answer("Товар недоступен.", show_alert=True)
        return

    if product.type == ProductType.SERVICE:
        await state.set_state(ServiceCheckoutState.waiting_for_comment)
        await state.update_data(product_id=product.id)
        await callback.message.answer(
            (
                f"Вы покупаете услугу «{product.title}».\n"
                "Отправьте одним сообщением комментарий или краткое ТЗ. "
                "Если комментарий не нужен, отправьте символ '-'."
            )
        )
        await callback.answer()
        return

    await create_checkout_for_product(callback.message, callback.from_user, product.id, container)
    await callback.answer()


@router.message(ServiceCheckoutState.waiting_for_comment)
async def capture_service_comment(message: Message, state: FSMContext, container: AppContainer) -> None:
    if message.from_user is None or message.text is None:
        await message.answer("Нужен текстовый комментарий. Если комментарий не нужен, отправьте '-'.")
        return
    data = await state.get_data()
    product_id = int(data["product_id"])
    customer_comment = None if message.text.strip() == "-" else message.text.strip()
    await create_checkout_for_product(message, message.from_user, product_id, container, customer_comment)
    await state.clear()


async def create_checkout_for_product(
    message: Message,
    telegram_user: TelegramUser,
    product_id: int,
    container: AppContainer,
    customer_comment: str | None = None,
) -> None:
    checkout_service = build_checkout_service(container)
    async with container.session_factory() as session:
        product = await catalog_service.get_product(session, product_id)
        if product is None or not product.is_active:
            await message.answer("Товар недоступен.")
            return
        user = await user_service.sync_user(session, telegram_user)
        result = await checkout_service.create_checkout(
            session,
            user=user,
            product=product,
            customer_comment=customer_comment,
        )
    await message.answer(
        (
            f"Заказ #{result.order.id} создан.\n"
            f"Товар: {result.product.title}\n"
            f"Сумма: {format_price(result.payment.amount, result.payment.currency)}\n\n"
            "Для MVP используется демо-оплата без реального списания."
        ),
        reply_markup=payment_keyboard(result.payment.id, container.payment_provider.pay_button_text),
    )


@router.callback_query(F.data.startswith("pay:"))
async def complete_payment(callback: CallbackQuery, bot: Bot, container: AppContainer) -> None:
    if callback.from_user is None:
        return
    payment_id = int(callback.data.split(":")[1])
    checkout_service = build_checkout_service(container)
    async with container.session_factory() as session:
        try:
            order, product = await checkout_service.complete_demo_payment(
                session,
                bot=bot,
                payment_id=payment_id,
                telegram_user_id=callback.from_user.id,
            )
        except PermissionError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    success_text = (
        f"Оплата заказа #{order.id} подтверждена.\n"
        f"Товар: {product.title}\n"
    )
    if product.type == ProductType.DIGITAL:
        success_text += "Файл отправлен в этот чат."
    else:
        success_text += "Заказ на услугу создан, администратор уведомлен."
    await callback.message.edit_text(success_text)
    await callback.answer("Оплата подтверждена.")


@router.message(Command("orders"))
@router.message(F.text == "Мои заказы")
async def show_orders(message: Message, container: AppContainer) -> None:
    if message.from_user is None:
        return
    checkout_service = build_checkout_service(container)
    async with container.session_factory() as session:
        orders = await checkout_service.list_user_orders(session, telegram_user_id=message.from_user.id)
    if not orders:
        await message.answer("У вас пока нет заказов.")
        return
    await message.answer("Ваши заказы:", reply_markup=orders_keyboard(orders))


@router.callback_query(F.data == "orders:open")
async def open_orders_callback(callback: CallbackQuery, container: AppContainer) -> None:
    if callback.from_user is None:
        return
    checkout_service = build_checkout_service(container)
    async with container.session_factory() as session:
        orders = await checkout_service.list_user_orders(session, telegram_user_id=callback.from_user.id)
    if not orders:
        await callback.message.edit_text("У вас пока нет заказов.")
        await callback.answer()
        return
    await callback.message.edit_text("Ваши заказы:", reply_markup=orders_keyboard(orders))
    await callback.answer()


@router.callback_query(F.data.startswith("order:"))
async def show_order(callback: CallbackQuery, container: AppContainer) -> None:
    if callback.from_user is None:
        return
    order_id = int(callback.data.split(":")[1])
    checkout_service = build_checkout_service(container)
    async with container.session_factory() as session:
        order = await checkout_service.get_user_order(
            session,
            order_id=order_id,
            telegram_user_id=callback.from_user.id,
        )
    if order is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    text = (
        f"Заказ #{order.id}\n"
        f"Товар: {order.product.title}\n"
        f"Статус: {status_label(order.status.value)}\n"
        f"Сумма: {format_price(order.amount, order.currency)}\n"
        f"Комментарий: {order.customer_comment or 'не указан'}"
    )
    await callback.message.edit_text(text, reply_markup=order_keyboard(order))
    await callback.answer()


@router.callback_query(F.data.startswith("redownload:"))
async def redownload_file(callback: CallbackQuery, bot: Bot, container: AppContainer) -> None:
    if callback.from_user is None:
        return
    order_id = int(callback.data.split(":")[1])
    checkout_service = build_checkout_service(container)
    async with container.session_factory() as session:
        try:
            await checkout_service.redeliver_order(
                session,
                bot=bot,
                order_id=order_id,
                telegram_user_id=callback.from_user.id,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await callback.answer("Файл отправлен повторно.")
