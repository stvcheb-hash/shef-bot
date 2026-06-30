import time
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, PhotoSize
from aiogram.filters import Command

from openai_client import extract_products, extract_products_from_image, generate_recipe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

# Хранилище пользователей (в памяти)
users_state: dict = {}

# Лимит бесплатных рецептов в день
FREE_LIMIT_PER_DAY = 3


def _get_user(uid: int) -> dict:
    """Получает или создаёт состояние пользователя."""
    if uid not in users_state:
        users_state[uid] = {
            "is_paid": False,
            "paid_until": 0,
            "requests_today": 0,
            "day_started": int(time.time() // 86400),
        }
    u = users_state[uid]
    
    # Проверяем, не истёк ли платный доступ
    if u["is_paid"] and u["paid_until"] < time.time():
        u["is_paid"] = False
    
    # Сброс счётчика в новый день
    today = int(time.time() // 86400)
    if u["day_started"] != today:
        u["requests_today"] = 0
        u["day_started"] = today
    
    return u


def _format_recipe(recipe: dict) -> str:
    """Форматирует рецепт в красивое сообщение."""
    title = recipe.get("title", "Без названия")
    time_min = recipe.get("time_minutes", "?")
    difficulty = recipe.get("difficulty", "?")
    
    ingredients = recipe.get("ingredients", [])
    steps = recipe.get("steps", [])
    chef_tip = recipe.get("chef_tip", "")
    warning = recipe.get("warning")
    
    calories = recipe.get("calories_kcal", "?")
    proteins = recipe.get("proteins_g", "?")
    fats = recipe.get("fats_g", "?")
    carbs = recipe.get("carbs_g", "?")
    
    text = f"🍽 <b>{title}</b>\n"
    text += f"⏱ {time_min} мин · {difficulty}\n\n"
    
    text += "🛒 <b>Ингредиенты:</b>\n"
    for ing in ingredients:
        text += f"• {ing.get('name', '?')} — {ing.get('grams', '?')} г\n"
    
    text += "\n👨‍🍳 <b>Готовим:</b>\n"
    for i, step in enumerate(steps, 1):
        text += f"{i}. {step}\n\n"
    
    if chef_tip:
        text += f"💡 {chef_tip}\n\n"
    
    text += "📊 <b>КБЖУ на порцию:</b>\n"
    text += f"Калории: {calories} ккал\n"
    text += f"Б: {proteins} г · Ж: {fats} г · У: {carbs} г\n"
    
    if warning:
        text += f"\n⚠️ {warning}"
    
    return text


async def _send_recipe(message: Message, recipe: dict):
    """Отправляет отформатированный рецепт."""
    text = _format_recipe(recipe)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        " <b>Шеф-рацион из помойки</b>\n\n"
        "Напиши, что у тебя в холодильнике — текстом.\n"
        "Или <b>отправь фото</b> холодильника — я сам распознаю продукты!\n\n"
        "Пример: курица, 2 яйца, пол-лимона, старый сыр, рис\n\n"
        " Бесплатно: 3 рецепта в день"
    )


@router.message(F.photo)
async def handle_photo(message: Message):
    """Обрабатывает фото холодильника."""
    # Берём фото лучшего качества (последнее в списке)
    photo: PhotoSize = message.photo[-1]
    
    # Скачиваем фото
    file = await message.bot.get_file(photo.file_id)
   file_obj = await message.bot.download_file(file.file_path)
photo_bytes = file_obj.read()
    
    # Отправляем индикатор
    await message.answer("📸 Распознаю продукты на фото...")
    
    try:
        # Распознаём продукты
        result = await extract_products_from_image(photo_bytes)
        products = result.get("products", [])
        
        if not products:
            await message.answer(
                "😕 Не удалось распознать продукты на фото.\n\n"
                "Попробуй:\n"
                "• Сфотографировать ближе\n"
                "• Хорошее освещение\n"
                "• Или напиши продукты текстом"
            )
            return
        
        # Показываем распознанное
        products_list = "\n".join(f"• {p['name']} ({p['grams']} г)" for p in products[:10])
        await message.answer(
            f" Распознал продукты:\n\n{products_list}\n\n"
            f"Готовлю рецепт..."
        )
        
        # Генерируем рецепт
        recipe = await generate_recipe(products)
        await _send_recipe(message, recipe)
        
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")
        await message.answer(
            "😵 Что-то пошло не так при обработке фото.\n"
            "Попробуй ещё раз или напиши продукты текстом."
        )


@router.message(F.text)
async def handle_recipe_request(message: Message):
    """Обрабатывает текстовый запрос с продуктами."""
    user = _get_user(message.from_user.id)
    
    # Проверка лимита (если не платный)
    if not user["is_paid"] and user["requests_today"] >= FREE_LIMIT_PER_DAY:
        await message.answer(
            f"🚫 Лимит бесплатных рецептов на сегодня исчерпан ({FREE_LIMIT_PER_DAY}/3).\n\n"
            f"Приходи завтра или оформи подписку «Режим Худей» для безлимита!"
        )
        return
    
    # Извлекаем продукты
    await message.answer("🔍 Ищу продукты...")
    
    try:
        result = await extract_products(message.text)
        products = result.get("products", [])
        
        if not products:
            await message.answer(
                " Не удалось найти продукты в твоём сообщении.\n"
                "Попробуй написать проще: курица, яйца, рис"
            )
            return
        
        # Увеличиваем счётчик
        user["requests_today"] += 1
        
        # Генерируем рецепт
        await message.answer("👨‍🍳 Готовлю рецепт...")
        recipe = await generate_recipe(products)
        await _send_recipe(message, recipe)
        
    except Exception as e:
        logger.error(f"Error in handle_recipe_request: {e}")
        await message.answer(
            "😵 Что-то пошло не так.\n"
            "Попробуй ещё раз."
        )