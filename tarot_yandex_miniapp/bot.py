from __future__ import annotations
import os, json, uuid, base64, logging, random, mimetypes
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

ROOT = Path(__file__).resolve().parent
PHOTO_DIR = ROOT / "user_photos"
PHOTO_DIR.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_KEY = os.getenv("YANDEX_API_KEY", "").strip()
FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "").strip()
MODEL = os.getenv("YANDEX_MODEL", "qwen3.6-35b-a3b").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tarot")

MAJOR = [
"Шут","Маг","Верховная Жрица","Императрица","Император","Иерофант","Влюблённые",
"Колесница","Сила","Отшельник","Колесо Фортуны","Справедливость","Повешенный",
"Смерть","Умеренность","Дьявол","Башня","Звезда","Луна","Солнце","Суд","Мир"
]
RANKS = ["Туз","Двойка","Тройка","Четвёрка","Пятёрка","Шестёрка","Семёрка","Восьмёрка","Девятка","Десятка","Паж","Рыцарь","Королева","Король"]
SUITS = ["Жезлов","Кубков","Мечей","Пентаклей"]
DECK = MAJOR + [f"{rank} {suit}" for suit in SUITS for rank in RANKS]
POSITIONS = [
    ("Прошлое", "Что привело к ситуации, какие события и установки повлияли на неё."),
    ("Настоящее", "Что происходит сейчас, какие силы и чувства особенно важны."),
    ("Будущее", "Вероятное направление развития и на что стоит обратить внимание.")
]
client = OpenAI(api_key=API_KEY, base_url="https://ai.api.cloud.yandex.net/v1", project=FOLDER_ID) if API_KEY and FOLDER_ID else None

def card_filename(name: str) -> str:
    return name + ".jpg"

def make_cards():
    chosen = random.sample(DECK, 3)
    return [{"name": n, "orientation": random.choice(["прямое положение", "перевёрнутое положение"])} for n in chosen]

def get_photo_path(context):
    p = context.user_data.get("photo_path")
    return Path(p) if p and Path(p).exists() else None

async def ask_yandex(question: str, photo_path: Path | None = None) -> str:
    if not client:
        return "Не настроен Yandex AI. Проверь YANDEX_API_KEY и YANDEX_FOLDER_ID в файле .env."
    content = [{"type": "text", "text": question}]
    if photo_path and photo_path.exists():
        mime = mimetypes.guess_type(photo_path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(photo_path.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    try:
        response = client.chat.completions.create(
            model=f"gpt://{FOLDER_ID}/{MODEL}",
            messages=[
                {"role": "system", "content": (
                    "Ты бережный и вдумчивый консультант по символической системе Таро Rider–Waite–Smith. "
                    "Не утверждай, что предсказываешь неизбежное будущее. Не делай медицинских, юридических "
                    "или финансовых диагнозов. Если приложено фото, опиши только уместные визуальные детали "
                    "и используй их как дополнительный контекст, не выдумывай личность, характер или судьбу "
                    "человека по внешности. Не делай выводов о чувствительных признаках."
                )},
                {"role": "user", "content": content}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        result = response.choices[0].message.content
        return result if isinstance(result, str) else str(result)
    except Exception:
        log.exception("Yandex API error")
        return "Не удалось получить трактовку от Yandex AI. Проверь модель, API-ключ, Folder ID и доступ к модели."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Добро пожаловать в Таро.\n\n"
        "Отправь свой вопрос одним сообщением. Если хочешь, сначала прикрепи фото: я учту его как дополнительный контекст.\n\n"
        "Команды: /new — новый расклад, /help — помощь."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться:\n"
        "1. При желании отправь боту фотографию.\n"
        "2. Следующим сообщением напиши вопрос для расклада.\n"
        "3. Открой три карты в Mini App и нажми «Передать расклад».\n\n"
        "Фото используется только для текущего расклада и удаляется после трактовки. "
        "Не отправляй документы, пароли и другую конфиденциальную информацию."
    )

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.photo:
        return
    old = get_photo_path(context)
    if old:
        try: old.unlink()
        except OSError: pass
    photo = msg.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    dest = PHOTO_DIR / f"{update.effective_user.id}_{uuid.uuid4().hex}.jpg"
    await tg_file.download_to_drive(custom_path=dest)
    context.user_data["photo_path"] = str(dest)
    await msg.reply_text("📷 Фото получено. Теперь отправь вопрос для расклада. Фото будет использовано только для этой трактовки.")

async def new_reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("question"):
        await update.message.reply_text("Сначала отправь вопрос для расклада. Фото можно прикрепить перед вопросом.")
        return
    cards = make_cards()
    token = uuid.uuid4().hex
    context.user_data["reading"] = {"cards": cards, "token": token, "question": context.user_data["question"]}
    context.user_data["question"] = None
    if WEBAPP_URL:
        payload = json.dumps(cards, ensure_ascii=False, separators=(",", ":"))
        from urllib.parse import urlencode
        url = WEBAPP_URL + "?" + urlencode({"token": token, "cards": payload})
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✨ Открыть три карты", web_app=WebAppInfo(url=url))]])
        await update.message.reply_text("Три карты уже выбраны. Открой Mini App, переверни их в любом порядке и передай расклад боту.", reply_markup=keyboard)
    else:
        await update.message.reply_text("WEBAPP_URL не задан. Добавь ссылку Mini App в .env и перезапусти бота.")

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return
    context.user_data["question"] = text
    await new_reading(update, context)

async def receive_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.web_app_data:
        return
    try:
        data = json.loads(msg.web_app_data.data)
        reading = context.user_data.get("reading")
        if not reading or data.get("token") != reading.get("token"):
            await msg.reply_text("Этот расклад уже неактуален. Напиши новый вопрос, чтобы начать заново.")
            return
        order = data.get("order")
        if not isinstance(order, list) or sorted(order) != [0, 1, 2]:
            await msg.reply_text("Не удалось проверить порядок карт. Начни новый расклад.")
            return
        cards = reading["cards"]
        photo = get_photo_path(context)
        lines = [
            f"Вопрос клиента: {reading['question']}",
            "Карты в порядке открытия:"
        ]
        for position_index, card_index in enumerate(order):
            position, description = POSITIONS[card_index]
            card = cards[card_index]
            lines.append(f"{position}: {card['name']} ({card['orientation']}). {description}")
        lines.append("Дай отдельную трактовку каждой карты, затем общий вывод и практичный совет. Пиши по-русски, бережно, без категоричных предсказаний.")
        if photo:
            lines.append("К сообщению приложено фото клиента. Учитывай только уместный визуальный контекст, не делай выводов о личности по внешности.")
        await msg.reply_text("🔮 Расклад принят. Готовлю трактовку…")
        answer = await ask_yandex("\n".join(lines), photo)
        await msg.reply_text(answer)
        if photo:
            try: photo.unlink()
            except OSError: pass
            context.user_data.pop("photo_path", None)
        context.user_data.pop("reading", None)
    except Exception:
        log.exception("Bad Mini App payload")
        await msg.reply_text("Не удалось обработать расклад. Попробуй начать заново командой /new.")

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши вопрос одним сообщением. Если нужно, сначала отправь фото.")

def main():
    if not TOKEN:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN в .env")
    if not API_KEY or not FOLDER_ID:
        log.warning("Не заполнены YANDEX_API_KEY или YANDEX_FOLDER_ID")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, receive_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))
    log.info("Tarot Yandex Mini App bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
