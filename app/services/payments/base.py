from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(slots=True)
class PaymentPreparation:
    provider_payment_id: str
    title: str
    description: str
    metadata: dict = field(default_factory=dict)


class BasePaymentProvider(ABC):
    code: str
    pay_button_text: str

    @abstractmethod
    async def prepare_payment(self, *, order_id: int, amount: int, title: str) -> PaymentPreparation:
        raise NotImplementedError


class DemoPaymentProvider(BasePaymentProvider):
    code = "demo"
    pay_button_text = "Оплатить сейчас"

    async def prepare_payment(self, *, order_id: int, amount: int, title: str) -> PaymentPreparation:
        external_id = f"demo_{order_id}_{uuid4().hex[:12]}"
        return PaymentPreparation(
            provider_payment_id=external_id,
            title="Демо-оплата",
            description=(
                f"Оплата товара «{title}» в тестовом режиме. "
                "Кнопка ниже помечает платеж успешным без реального списания."
            ),
            metadata={"demo": True, "amount": amount},
        )

