import json
import re
import logging
import base64
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, OPENAI_BASE_URL, GPT_MODEL

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


def _extract_json(text: str) -> dict:
    """Извлекает JSON из ответа модели."""
    if not text:
        raise ValueError("Пустой ответ")
    
    # Убираем markdown
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()
    
    # Ищем JSON
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Full parse error: {e}")
    
    raise ValueError("Не удалось распарсить JSON")


async def extract_products(user_text: str) -> dict:
    from prompts import EXTRACT_PROMPT
    
    logger.info("=" * 50)
    logger.info("EXTRACT_PRODUCTS START")
    logger.info(f"User text: {user_text[:100]}")
    
    try:
        resp = await client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "You extract products from text. Reply with valid JSON only."},
                {"role": "user", "content": EXTRACT_PROMPT.format(text=user_text)},
            ],
            temperature=0.1,
        )
        
        raw = resp.choices[0].message.content
        logger.info(f"RAW RESPONSE:\n{raw}")
        
        result = _extract_json(raw)
        logger.info(f"Parsed result: {result}")
        
        # Нормализуем ключи
        normalized = {}
        for key, value in result.items():
            clean_key = str(key).strip().lower().replace('"', '').replace('\n', '').replace(' ', '')
            if 'product' in clean_key:
                normalized['products'] = value
            else:
                normalized[clean_key] = value
        
        if 'products' not in normalized:
            logger.error(f"No 'products' key. Available: {list(normalized.keys())}")
            raise ValueError("Модель не вернула список продуктов")
        
        logger.info("EXTRACT_PRODUCTS SUCCESS")
        return normalized
        
    except Exception as e:
        logger.error(f"EXCEPTION: {type(e).__name__}: {e}")
        raise


async def extract_products_from_image(photo_bytes: bytes) -> dict:
    """Распознаёт продукты на фото через Vision-модель."""
    logger.info("=" * 50)
    logger.info("EXTRACT_PRODUCTS_FROM_IMAGE START")
    
    photo_b64 = base64.b64encode(photo_bytes).decode("utf-8")
    
    try:
        resp = await client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "Ты распознаёшь продукты на фото холодильника. Отвечай СТРОГО валидным JSON без пояснений, без markdown, без ```."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Извлеки список продуктов с фото.
Для каждого продукта укажи name и примерные grams.
Если продукт выглядит испорченным — добавь поле warning.
Игнорируй упаковку, этикетки, пустые полки.
Распознавай только еду.

СТРОГО JSON:
{
  "products": [
    {"name": "куриное филе", "grams": 300},
    {"name": "молоко", "grams": 500}
  ]
}"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{photo_b64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.1,
        )
        
        raw = resp.choices[0].message.content
        logger.info(f"RAW IMAGE RESPONSE:\n{raw[:500]}")
        
        result = _extract_json(raw)
        logger.info(f"Parsed result: {result}")
        
        # Нормализуем ключи
        normalized = {}
        for key, value in result.items():
            clean_key = str(key).strip().lower().replace('"', '').replace('\n', '').replace(' ', '')
            if 'product' in clean_key:
                normalized['products'] = value
            else:
                normalized[clean_key] = value
        
        if 'products' not in normalized:
            logger.error(f"No 'products' key. Available: {list(normalized.keys())}")
            raise ValueError("Модель не вернула список продуктов")
        
        logger.info("EXTRACT_PRODUCTS_FROM_IMAGE SUCCESS")
        return normalized
        
    except Exception as e:
        logger.error(f"EXCEPTION: {type(e).__name__}: {e}")
        raise


async def generate_recipe(products: list) -> dict:
    from prompts import SYSTEM_PROMPT
    
    products_str = "\n".join(f"- {p['name']} ({p['grams']} г)" for p in products)
    logger.info("=" * 50)
    logger.info("GENERATE_RECIPE START")
    
    try:
        resp = await client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Придумай рецепт из:\n{products_str}"},
            ],
            temperature=0.7,
        )
        
        raw = resp.choices[0].message.content
        logger.info(f"RAW RECIPE:\n{raw[:500]}")
        
        result = _extract_json(raw)
        return result
        
    except Exception as e:
        logger.error(f"EXCEPTION in generate_recipe: {type(e).__name__}: {e}")
        raise