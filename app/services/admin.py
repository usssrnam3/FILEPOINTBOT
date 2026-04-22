from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product, ProductFile, ProductType
from app.services.file_storage import StoredFile


class AdminService:
    async def create_product(
        self,
        session: AsyncSession,
        *,
        admin_telegram_id: int,
        title: str,
        description: str,
        product_type: ProductType,
        price_amount: int,
        stored_file: StoredFile | None = None,
    ) -> Product:
        product = Product(
            title=title,
            description=description,
            type=product_type,
            price_amount=price_amount,
            currency="RUB",
            is_active=False,
            created_by_admin_id=admin_telegram_id,
        )
        session.add(product)
        await session.flush()

        if product_type == ProductType.DIGITAL and stored_file is not None:
            session.add(
                ProductFile(
                    product_id=product.id,
                    telegram_file_id=stored_file.telegram_file_id,
                    telegram_file_unique_id=stored_file.telegram_file_unique_id,
                    original_filename=stored_file.original_filename,
                    storage_path=stored_file.storage_path,
                    mime_type=stored_file.mime_type,
                    file_size=stored_file.file_size,
                )
            )

        await session.commit()
        await session.refresh(product)
        return product

    async def toggle_product(self, session: AsyncSession, product: Product) -> Product:
        product.is_active = not product.is_active
        await session.commit()
        await session.refresh(product)
        return product

