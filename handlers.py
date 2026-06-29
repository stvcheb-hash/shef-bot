import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from openai_client import extract_products, generate_recipe
from kbju_db import calc_kbju
from config import FREE_LIMIT_PER_DAY

router = Router()

users_state: dict = {}


def _get_user(uid: int) -> dict:
    if uid not in users_state:
        users_state[uid] = {
            "requests_today": 0,
            "day_started": int(time.time() // 86400),
        }
    u = users_state[uid]
    today = int(time.time() // 86400)
    if u["day_started"] != today:
        u["requests_today"] = 0
        u["day_started"] = today
    return u


@router.message(Command("start"))
async def cmd_start(message: Message):
    text = (
        "🧊 <b>Шеф-рацион из помойки</b>\n\n"
        "Напиши, что у тебя в холодильнике — "
        "текстом.\n"
        "Пример: <i>курица, 2 яйца, пол-лимона, старый сыр, рис</i>\n\n"
        f"🎁 Бесплатно: {FREE_LIMIT_PER_DAY} рецепта в день"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text)
async def handle_recipe_request(message: Message):
    uid = message.from_user.id
    user = _get_user(uid)

    if user["requests_today"] >= FREE_LIMIT_PER_DAY:
        await message.answer(
            "🚫 Лимит бесплатных рецептов на сегодня исчерпан.\n"
            "Приходи завтра!"
        )
        return

    wait_msg = await message.answer("🔍 Разбираю твой холодильник...")

    try:
        extracted = await extract_products(message.text)
        products = extracted.get("products", [])
        if not products:
            await wait_msg.edit_text("Не нашёл продуктов 🤔 Попробуй ещё раз.")
            return

        await wait_msg.edit_text("👨‍🍳 Шеф колдует над рецептом...")
        recipe = await generate_recipe(products)
        kbju = calc_kbju(recipe.get("ingredients", []))

        ingredients_str = "\n".join(
            f"• {i['name']} — {i['grams']} г" for i in recipe.get("ingredients", [])
        )
        steps_str = "\n\n".join(
            f"<b>{i+1}.</b> {s}" for i, s in enumerate(recipe.get("steps", []))
        )
        warning = f"\n\n⚠️ <i>{recipe['warning']}</i>" if recipe.get("warning") else ""

        result = (
            f"🍽 <b>{recipe.get('title', 'Блюдо')}</b>\n"
            f"⏱ {recipe.get('time_minutes', '?')} мин · {recipe.get('difficulty', '?')}\n\n"
            f"<b>🛒 Ингредиенты:</b>\n{ingredients_str}\n\n"
            f"<b>👨‍🍳 Готовим:</b>\n{steps_str}\n\n"
            f"💡 <i>{recipe.get('chef_tip', '')}</i>\n\n"
            f"📊 <b>КБЖУ на порцию:</b>\n"
            f"Калории: <b>{kbju['calories']}</b> ккал\n"
            f"Б: {kbju['proteins']} г · Ж: {kbju['fats']} г · У: {kbju['carbs']} г"
            f"{warning}"
        )

        await wait_msg.edit_text(result, parse_mode="HTML")
        user["requests_today"] += 1

    except Exception as e:
        await wait_msg.edit_text(f"😵 Что-то пошло не так: {e}\nПопробуй ещё раз.")