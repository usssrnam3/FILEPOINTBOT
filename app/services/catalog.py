from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product


class CatalogService:
    async def list_active_products(self, session: AsyncSession) -> list[Product]:
        query = (
            select(Product)
            .where(Product.is_active.is_(True))
            .options(selectinload(Product.file))
            .order_by(Product.created_at.desc())
        )
        result = await session.scalars(query)
        return list(result.all())

    async def list_all_products(self, session: AsyncSession) -> list[Product]:
        query = select(Product).options(selectinload(Product.file)).order_by(Product.created_at.desc())
        result = await session.scalars(query)
        return list(result.all())

    async def get_product(self, session: AsyncSession, product_id: int) -> Product | None:
        query = select(Product).where(Product.id == product_id).options(selectinload(Product.file))
        return await session.scalar(query)

