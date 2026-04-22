from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Order, OrderStatus, Product
from app.utils.formatting import format_price


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Каталог"), KeyboardButton(text="Мои заказы")],
        ],
        resize_keyboard=True,
    )


def catalog_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.button(
            text=f"{product.title} · {format_price(product.price_amount, product.currency)}",
            callback_data=f"product:{product.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def product_keyboard(product_id: int, product_type_label: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Купить {product_type_label}", callback_data=f"buy:{product_id}")
    builder.button(text="Назад в каталог", callback_data="catalog:open")
    builder.adjust(1)
    return builder.as_markup()


def payment_keyboard(payment_id: int, pay_button_text: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=pay_button_text, callback_data=f"pay:{payment_id}")
    builder.button(text="Мои заказы", callback_data="orders:open")
    builder.adjust(1)
    return builder.as_markup()


def orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        status_label = {
            OrderStatus.PENDING_PAYMENT: "ожидает оплаты",
            OrderStatus.PAID: "оплачен",
            OrderStatus.FULFILLED: "выдан",
            OrderStatus.CANCELLED: "отменен",
            OrderStatus.FAILED: "ошибка",
        }[order.status]
        builder.button(
            text=f"#{order.id} · {order.product.title} · {status_label}",
            callback_data=f"order:{order.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def order_keyboard(order: Order) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if order.product.file is not None and order.status in {OrderStatus.PAID, OrderStatus.FULFILLED}:
        builder.button(text="Получить файл снова", callback_data=f"redownload:{order.id}")
    builder.button(text="К списку заказов", callback_data="orders:open")
    builder.adjust(1)
    return builder.as_markup()

