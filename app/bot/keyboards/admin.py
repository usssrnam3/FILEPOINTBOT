from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Product, ProductType
from app.utils.formatting import format_price


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить цифровой товар", callback_data="admin:add:digital")
    builder.button(text="Добавить услугу", callback_data="admin:add:service")
    builder.button(text="Список товаров", callback_data="admin:products")
    builder.adjust(1)
    return builder.as_markup()


def admin_products_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        state = "вкл" if product.is_active else "выкл"
        builder.button(
            text=f"{product.title} · {format_price(product.price_amount)} · {state}",
            callback_data=f"admin_product:{product.id}",
        )
    builder.button(text="В меню админа", callback_data="admin:menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_product_keyboard(product: Product) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    action = "Снять с публикации" if product.is_active else "Опубликовать"
    builder.button(text=action, callback_data=f"admin_toggle:{product.id}")
    builder.button(text="К списку товаров", callback_data="admin:products")
    builder.adjust(1)
    return builder.as_markup()


def type_label(product_type: ProductType) -> str:
    return "файл" if product_type == ProductType.DIGITAL else "услугу"

