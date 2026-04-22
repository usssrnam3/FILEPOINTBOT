from aiogram import Dispatcher

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.user import router as user_router
from app.bot.middlewares.container import ContainerMiddleware
from app.services.container import AppContainer


def setup_dispatcher(container: AppContainer, storage) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    middleware = ContainerMiddleware(container)
    dispatcher.message.middleware(middleware)
    dispatcher.callback_query.middleware(middleware)
    dispatcher.include_router(user_router)
    dispatcher.include_router(admin_router)
    return dispatcher

