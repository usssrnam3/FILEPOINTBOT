from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.admin import admin_menu_keyboard, admin_product_keyboard, admin_products_keyboard
from app.bot.states.admin import CreateProductState
from app.db.models import ProductType
from app.services.admin import AdminService
from app.services.catalog import CatalogService
from app.services.container import AppContainer
from app.services.users import UserService
from app.utils.formatting import format_price

router = Router(name="admin")

admin_service = AdminService()
catalog_service = CatalogService()
user_service = UserService()


def is_admin(container: AppContainer, telegram_id: int) -> bool:
    return container.settings.is_admin(telegram_id)


def parse_rub_to_kopecks(raw_value: str) -> int:
    normalized = raw_value.replace(",", ".").strip()
    amount = Decimal(normalized)
    if amount <= 0:
        raise ValueError
    return int(amount * 100)


@router.message(Command("admin"))
async def admin_entry(message: Message, container: AppContainer) -> None:
    if message.from_user is None or not is_admin(container, message.from_user.id):
        await message.answer("Доступ запрещен.")
        return
    async with container.session_factory() as session:
        await user_service.sync_user(session, message.from_user)
    await message.answer("Админ-панель:", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "admin:menu")
async def admin_menu(callback: CallbackQuery, container: AppContainer) -> None:
    if callback.from_user is None or not is_admin(container, callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text("Админ-панель:", reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:products")
async def admin_products(callback: CallbackQuery, container: AppContainer) -> None:
    if callback.from_user is None or not is_admin(container, callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    async with container.session_factory() as session:
        products = await catalog_service.list_all_products(session)
    if not products:
        await callback.message.edit_text("Товаров пока нет.", reply_markup=admin_menu_keyboard())
        await callback.answer()
        return
    await callback.message.edit_text("Все товары:", reply_markup=admin_products_keyboard(products))
    await callback.answer()


@router.callback_query(F.data.in_({"admin:add:digital", "admin:add:service"}))
async def start_create_product(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if callback.from_user is None or not is_admin(container, callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    product_type = ProductType.DIGITAL if callback.data.endswith("digital") else ProductType.SERVICE
    await state.set_state(CreateProductState.waiting_for_title)
    await state.update_data(product_type=product_type.value)
    await callback.message.answer("Введите название товара.")
    await callback.answer()


@router.message(CreateProductState.waiting_for_title)
async def product_title(message: Message, state: FSMContext, container: AppContainer) -> None:
    if message.from_user is None or not is_admin(container, message.from_user.id):
        await message.answer("Доступ запрещен.")
        return
    if not message.text:
        await message.answer("Нужно текстовое название.")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateProductState.waiting_for_description)
    await message.answer("Теперь отправьте описание товара.")


@router.message(CreateProductState.waiting_for_description)
async def product_description(message: Message, state: FSMContext, container: AppContainer) -> None:
    if message.from_user is None or not is_admin(container, message.from_user.id):
        await message.answer("Доступ запрещен.")
        return
    if not message.text:
        await message.answer("Нужно текстовое описание.")
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(CreateProductState.waiting_for_price)
    await message.answer("Укажите цену в рублях. Пример: 1490 или 1490.00")


@router.message(CreateProductState.waiting_for_price)
async def product_price(message: Message, state: FSMContext, container: AppContainer) -> None:
    if message.from_user is None or not is_admin(container, message.from_user.id):
        await message.answer("Доступ запрещен.")
        return
    if not message.text:
        await message.answer("Нужно отправить цену текстом.")
        return
    try:
        price_amount = parse_rub_to_kopecks(message.text)
    except (InvalidOperation, ValueError):
        await message.answer("Не удалось распознать цену. Пример: 1490 или 1490.50")
        return

    data = await state.get_data()
    product_type = ProductType(data["product_type"])
    await state.update_data(price_amount=price_amount)
    if product_type == ProductType.DIGITAL:
        await state.set_state(CreateProductState.waiting_for_file)
        await message.answer("Отправьте файл одним Telegram-документом.")
        return

    async with container.session_factory() as session:
        product = await admin_service.create_product(
            session,
            admin_telegram_id=message.from_user.id,
            title=data["title"],
            description=data["description"],
            product_type=product_type,
            price_amount=price_amount,
        )
    await state.clear()
    await message.answer(
        (
            f"Услуга создана: #{product.id}\n"
            f"{product.title}\n"
            f"Цена: {format_price(product.price_amount)}\n"
            "По умолчанию товар не опубликован. Опубликуйте его в списке товаров."
        ),
        reply_markup=admin_menu_keyboard(),
    )


@router.message(CreateProductState.waiting_for_file)
async def product_file(message: Message, state: FSMContext, bot: Bot, container: AppContainer) -> None:
    if message.from_user is None or not is_admin(container, message.from_user.id):
        await message.answer("Доступ запрещен.")
        return
    if message.document is None:
        await message.answer("Нужно отправить именно документ, а не фото или текст.")
        return
    data = await state.get_data()
    stored_file = await container.storage.save_document(bot, message.document)
    async with container.session_factory() as session:
        product = await admin_service.create_product(
            session,
            admin_telegram_id=message.from_user.id,
            title=data["title"],
            description=data["description"],
            product_type=ProductType(data["product_type"]),
            price_amount=int(data["price_amount"]),
            stored_file=stored_file,
        )
    await state.clear()
    await message.answer(
        (
            f"Цифровой товар создан: #{product.id}\n"
            f"{product.title}\n"
            f"Цена: {format_price(product.price_amount)}\n"
            "По умолчанию товар не опубликован. Опубликуйте его в списке товаров."
        ),
        reply_markup=admin_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("admin_product:"))
async def admin_product_detail(callback: CallbackQuery, container: AppContainer) -> None:
    if callback.from_user is None or not is_admin(container, callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    product_id = int(callback.data.split(":")[1])
    async with container.session_factory() as session:
        product = await catalog_service.get_product(session, product_id)
    if product is None:
        await callback.answer("Товар не найден.", show_alert=True)
        return
    product_kind = "Цифровой товар" if product.type == ProductType.DIGITAL else "Услуга"
    publication = "опубликован" if product.is_active else "скрыт"
    file_info = product.file.original_filename if product.file is not None else "без файла"
    text = (
        f"#{product.id} · {product.title}\n\n"
        f"{product.description}\n\n"
        f"Тип: {product_kind}\n"
        f"Цена: {format_price(product.price_amount)}\n"
        f"Статус: {publication}\n"
        f"Файл: {file_info}"
    )
    await callback.message.edit_text(text, reply_markup=admin_product_keyboard(product))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_toggle:"))
async def admin_toggle_product(callback: CallbackQuery, container: AppContainer) -> None:
    if callback.from_user is None or not is_admin(container, callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    product_id = int(callback.data.split(":")[1])
    async with container.session_factory() as session:
        product = await catalog_service.get_product(session, product_id)
        if product is None:
            await callback.answer("Товар не найден.", show_alert=True)
            return
        if product.type == ProductType.DIGITAL and product.file is None:
            await callback.answer("Нельзя опубликовать цифровой товар без файла.", show_alert=True)
            return
        product = await admin_service.toggle_product(session, product)
    product_kind = "Цифровой товар" if product.type == ProductType.DIGITAL else "Услуга"
    publication = "опубликован" if product.is_active else "скрыт"
    file_info = product.file.original_filename if product.file is not None else "без файла"
    text = (
        f"#{product.id} · {product.title}\n\n"
        f"{product.description}\n\n"
        f"Тип: {product_kind}\n"
        f"Цена: {format_price(product.price_amount)}\n"
        f"Статус: {publication}\n"
        f"Файл: {file_info}"
    )
    await callback.message.edit_text(text, reply_markup=admin_product_keyboard(product))
    state_label = "опубликован" if product.is_active else "снят с публикации"
    await callback.answer(f"Товар {state_label}.")
