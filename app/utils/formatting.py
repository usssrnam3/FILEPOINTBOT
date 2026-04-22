def format_price(amount: int, currency: str = "RUB") -> str:
    rubles = amount / 100
    currency_symbol = "₽" if currency == "RUB" else currency
    return f"{rubles:,.2f}".replace(",", " ").replace(".00", "") + f" {currency_symbol}"

