import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import jdatetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError, NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ---------------- تنظیمات ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_TEXT = os.getenv("ADMIN_ID", "0").strip()
ADMIN_ID = int(ADMIN_ID_TEXT) if ADMIN_ID_TEXT.isdigit() else 0

GROUP_ID = -1004389774687
DATA_FILE = os.getenv("DATA_FILE", "requests.json")
IRAN_TZ = ZoneInfo("Asia/Tehran")

COOLDOWN_MINUTES = 15
WARNING_SECONDS = 10
HEALTH_CHECK_SECONDS = 60
RECONNECT_NOTICE_COOLDOWN = 300

if not TOKEN:
    raise RuntimeError("متغیر محیطی BOT_TOKEN در Render تنظیم نشده است.")

# ---------------- ذخیره اطلاعات ----------------

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError("Invalid data")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        loaded = {}

    loaded.setdefault("active", {})
    loaded.setdefault("cooldowns", {})
    loaded.setdefault("bot_messages", [])
    loaded.setdefault("panel_message_id", None)
    loaded.setdefault("reminder_message_id", None)
    loaded.setdefault("reminder_delete_at", None)
    return loaded


data = load_data()


def save_data():
    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temp_file, DATA_FILE)


def track_message(message_id):
    if message_id not in data["bot_messages"]:
        data["bot_messages"].append(message_id)
        save_data()


def untrack_message(message_id):
    if message_id in data["bot_messages"]:
        data["bot_messages"].remove(message_id)
        save_data()


def current_iran_time():
    return datetime.now(IRAN_TZ)


# ---------------- گزارش وضعیت به مدیر ----------------

async def notify_admin(app, text):
    if not ADMIN_ID:
        logging.warning("ADMIN_ID تنظیم نشده؛ پیام خصوصی وضعیت ارسال نشد.")
        return
    try:
        await app.bot.send_message(chat_id=ADMIN_ID, text=text)
    except TelegramError:
        logging.exception("ارسال پیام وضعیت به مدیر ناموفق بود.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.effective_message is None or user is None:
        return

    await update.effective_message.reply_text(
        f"سلام {user.first_name} عزیز ❤️\n\n"
        "ربات کد غذا فعاله.\n"
        f"🆔 آیدی عددی شما:\n{user.id}\n\n"
        "برای دریافت گزارش وضعیت ربات، همین دستور را در پیوی ربات اجرا کنید."
    )
    logging.info("کاربر %s دستور /start را اجرا کرد.", user.id)


# ---------------- وب‌سرور Render ----------------

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info("Health server listening on port %s", port)
    server.serve_forever()


# ---------------- پنل اصلی ----------------

PANEL_BUTTONS = [
    ("🟢 کد ناهار نجف می‌فروشم", "najaf_sell"),
    ("🔵 کد ناهار نجف می‌خرم", "najaf_buy"),
    ("🌙 کد شام نجف می‌فروشم", "najaf_dinner_sell"),
    ("🌙 کد شام نجف می‌خرم", "najaf_dinner_buy"),
    ("🟠 کد ناهار بابایی می‌فروشم", "babayi_sell"),
    ("🟣 کد ناهار بابایی می‌خرم", "babayi_buy"),
    ("🌙 کد شام بابایی می‌فروشم", "babayi_dinner_sell"),
    ("🌙 کد شام بابایی می‌خرم", "babayi_dinner_buy"),
    ("🟡 کد ناهار بقیه‌الله می‌فروشم", "baghi_sell"),
    ("🔵 کد ناهار بقیه‌الله می‌خرم", "baghi_buy"),
    ("🔄 معاوضه کد غذا", "exchange"),
]


async def send_panel(app):
    keyboard = [
        [InlineKeyboardButton(label, callback_data=callback)]
        for label, callback in PANEL_BUTTONS
    ]
    markup = InlineKeyboardMarkup(keyboard)
    panel_id = data.get("panel_message_id")

    if panel_id:
        try:
            await app.bot.edit_message_text(
                chat_id=GROUP_ID,
                message_id=panel_id,
                text="🍽 کد غذا\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=markup,
            )
            return
        except TelegramError:
            logging.warning("پنل قبلی در دسترس نیست؛ پنل تازه ارسال می‌شود.")

    sent = await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=markup,
    )
    data["panel_message_id"] = sent.message_id
    track_message(sent.message_id)
    save_data()


# ---------------- پیام‌های موقت ----------------

async def delete_later(message, seconds=WARNING_SECONDS):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except TelegramError:
        pass
    untrack_message(message.message_id)


async def send_temporary_warning(context, text, user_id, previous=None):
    keyboard = None
    if previous:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🗑 حذف درخواست قبلی",
                callback_data=f"remove:{user_id}:{previous['message_id']}",
            )
        ]])

    msg = await context.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        reply_markup=keyboard,
    )
    track_message(msg.message_id)
    context.application.create_task(delete_later(msg))


# ---------------- پاک‌سازی نیمه‌شب ----------------

async def midnight_cleanup(app):
    logging.info("شروع پاک‌سازی نیمه‌شب")
    panel_id = data.get("panel_message_id")

    for message_id in list(data["bot_messages"]):
        if message_id == panel_id:
            continue
        try:
            await app.bot.delete_message(chat_id=GROUP_ID, message_id=message_id)
        except TelegramError:
            logging.warning("حذف پیام %s ناموفق بود.", message_id)

    data["bot_messages"] = [panel_id] if panel_id else []
    data["active"] = {}
    data["cooldowns"] = {}
    data["reminder_message_id"] = None
    data["reminder_delete_at"] = None
    save_data()
    logging.info("پاک‌سازی نیمه‌شب تمام شد.")


async def midnight_scheduler(app):
    while True:
        now = current_iran_time()
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        await asyncio.sleep(max(1, (next_midnight - now).total_seconds()))
        try:
            await midnight_cleanup(app)
        except Exception:
            logging.exception("خطا در پاک‌سازی نیمه‌شب")


# ---------------- یادآوری چهارشنبه ساعت ۰۰:۰۱ ----------------

def next_wednesday_reminder():
    now = current_iran_time()
    # در پایتون دوشنبه=0 و چهارشنبه=2 است.
    days = (2 - now.weekday()) % 7
    target = (now + timedelta(days=days)).replace(
        hour=0, minute=1, second=0, microsecond=0
    )
    if target <= now:
        target += timedelta(days=7)
    return target


async def send_reminder(app):
    msg = await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا رزرو کنید یادتون نره 😉",
    )
    data["reminder_message_id"] = msg.message_id
    # پیام یادآوری تا پاک‌سازی نیمه‌شب بعدی باقی می‌ماند.
    data["reminder_delete_at"] = None
    track_message(msg.message_id)
    save_data()


async def reminder_scheduler(app):
    while True:
        target = next_wednesday_reminder()
        seconds = max(1, (target - current_iran_time()).total_seconds())
        logging.info("یادآوری بعدی در %s ارسال می‌شود.", target.isoformat())
        await asyncio.sleep(seconds)
        try:
            await send_reminder(app)
            logging.info("یادآوری چهارشنبه ارسال شد و تا پاک‌سازی بعدی می‌ماند.")
        except Exception:
            logging.exception("ارسال یادآوری ناموفق بود.")


# ---------------- نظارت بر اتصال تلگرام ----------------

async def connection_monitor(app):
    was_connected = True
    last_failure_notice = None

    while True:
        await asyncio.sleep(HEALTH_CHECK_SECONDS)
        try:
            await app.bot.get_me()
            if not was_connected:
                await notify_admin(
                    app,
                    "🟢 ربات دوباره به تلگرام وصل شد و ارتباط برقرار است.",
                )
            was_connected = True
            last_failure_notice = None
        except Exception:
            logging.exception("بررسی اتصال تلگرام ناموفق بود.")
            now = current_iran_time()
            if was_connected or (
                last_failure_notice is None
                or (now - last_failure_notice).total_seconds()
                >= RECONNECT_NOTICE_COOLDOWN
            ):
                await notify_admin(
                    app,
                    "🔴 ارتباط ربات با تلگرام قطع یا ناپایدار شده است؛ "
                    "ربات در حال تلاش برای اتصال مجدد است.",
                )
                last_failure_notice = now
            was_connected = False


# ---------------- مدیریت دکمه‌ها ----------------

OPTIONS = dict(PANEL_BUTTONS)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    user = query.from_user
    user_id = str(user.id)

    try:
        await query.answer()
    except TelegramError:
        pass

    # حذف پیام درخواست فقط توسط صاحب آن
    if query.data.startswith("delete:"):
        try:
            owner_id = int(query.data.split(":", 1)[1])
        except (ValueError, IndexError):
            return

        if user.id != owner_id or query.message is None:
            return

        message_id = query.message.message_id
        try:
            await query.message.delete()
        except TelegramError:
            return

        untrack_message(message_id)
        active = data["active"].get(user_id)
        if active and active.get("message_id") == message_id:
            data["active"].pop(user_id, None)
            save_data()
        return

    # حذف درخواست قبلی از طریق دکمه هشدار
    if query.data.startswith("remove:"):
        try:
            _, owner_text, message_text = query.data.split(":", 2)
            owner_id = int(owner_text)
            message_id = int(message_text)
        except (ValueError, IndexError):
            return

        if user.id != owner_id:
            return

        active = data["active"].get(user_id)
        if active and active.get("message_id") == message_id:
            try:
                await context.bot.delete_message(
                    chat_id=GROUP_ID, message_id=message_id
                )
            except TelegramError:
                pass
            untrack_message(message_id)
            data["active"].pop(user_id, None)
            save_data()

        if query.message:
            try:
                await query.message.delete()
            except TelegramError:
                pass
            untrack_message(query.message.message_id)
        return

    if query.data not in OPTIONS:
        return

    request_text = OPTIONS[query.data]
    now = current_iran_time()
    today = now.date().isoformat()

    # محدودیت ۱۵ دقیقه‌ای
    cooldown_value = data["cooldowns"].get(user_id)
    if cooldown_value:
        try:
            cooldown_until = datetime.fromisoformat(cooldown_value)
            if now < cooldown_until:
                seconds_left = int((cooldown_until - now).total_seconds())
                minutes_left = max(1, (seconds_left + 59) // 60)
                await send_temporary_warning(
                    context,
                    f"⏳ لطفاً {minutes_left} دقیقه دیگر صبر کنید؛ "
                    "بعد از ثبت هر درخواست باید ۱۵ دقیقه برای درخواست بعدی صبر کنید.",
                    user.id,
                )
                return
        except ValueError:
            data["cooldowns"].pop(user_id, None)

    # هر کاربر در هر روز فقط یک درخواست فعال
    active = data["active"].get(user_id)
    if active and active.get("date") == today:
        await send_temporary_warning(
            context,
            "⚠️ شما امروز یک درخواست ثبت کرده‌اید.\n"
            "برای ثبت درخواست جدید، ابتدا درخواست قبلی خود را حذف کنید.",
            user.id,
            active,
        )
        return

    # تاریخ شمسی
    jalali = jdatetime.datetime.fromgregorian(datetime=now)
    weekdays = {
        0: "دوشنبه",
        1: "سه‌شنبه",
        2: "چهارشنبه",
        3: "پنجشنبه",
        4: "جمعه",
        5: "شنبه",
        6: "یکشنبه",
    }
    months = {
        1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
        5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
        9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند",
    }
    date_text = (
        f"{weekdays[jalali.togregorian().weekday()]}، "
        f"{jalali.day} {months[jalali.month]} {jalali.year}"
    )
    time_text = now.strftime("%H:%M:%S")
    name = html_escape(user.full_name)

    message_text = (
        f'<a href="tg://user?id={user.id}">{name}</a>\n'
        f"{request_text}\n\n"
        f"📅 {date_text}\n"
        f"⏰ ساعت ایران: {time_text}"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 حذف پیام", callback_data=f"delete:{user.id}")
    ]])

    sent = await context.bot.send_message(
        chat_id=GROUP_ID,
        text=message_text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    track_message(sent.message_id)

    data["active"][user_id] = {
        "message_id": sent.message_id,
        "date": today,
    }
    data["cooldowns"][user_id] = (
        now + timedelta(minutes=COOLDOWN_MINUTES)
    ).isoformat()
    save_data()


def html_escape(value):
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------- راه‌اندازی و خاموشی ----------------

async def post_init(app):
    await notify_admin(app, "🟡 ربات در حال راه‌اندازی است...")

    # ارسال یا به‌روزرسانی پنل؛ تلاش مجدد در صورت خطای موقت
    while True:
        try:
            await send_panel(app)
            await notify_admin(app, "🟢 پنل با موفقیت وصل و آماده استفاده است.")
            await notify_admin(app, "🟢 ربات وصل شد و آماده فعالیت است.")
            break
        except Exception:
            logging.exception("خطا در ارسال پنل؛ تلاش مجدد تا ۳۰ ثانیه دیگر.")
            await notify_admin(
                app,
                "🔴 پنل ارسال نشد؛ ربات ۳۰ ثانیه دیگر دوباره تلاش می‌کند.",
            )
            await asyncio.sleep(30)

    app.create_task(midnight_scheduler(app))
    app.create_task(reminder_scheduler(app))
    app.create_task(connection_monitor(app))


async def post_shutdown(app):
    await notify_admin(app, "🔴 ربات در حال خاموش شدن است.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(
        "خطا هنگام پردازش درخواست تلگرام:",
        exc_info=context.error,
    )
    # خطاهای عادی هندلر لزوماً به معنی قطع‌شدن کل ربات نیستند.
    if isinstance(context.error, NetworkError):
        await notify_admin(
            context.application,
            "⚠️ خطای شبکه رخ داده؛ ربات برای ادامه ارتباط تلاش می‌کند.",
        )


# ---------------- اجرای برنامه ----------------

def main():
    # وب‌سرور سلامت Render در یک Thread جداگانه اجرا می‌شود.
    threading.Thread(
        target=start_web_server,
        daemon=True,
    ).start()

    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_error_handler(on_error)

    logging.info("ربات کد غذا در حال راه‌اندازی است.")
    app.run_polling(
        bootstrap_retries=-1,
        poll_interval=1,
        timeout=30,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
