import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import jdatetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = -1004389774687
DATA_FILE = "requests.json"

IRAN_TZ = ZoneInfo("Asia/Tehran")

COOLDOWN_MINUTES = 15
WARNING_SECONDS = 10


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

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

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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


# وب سرور Render

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    server.serve_forever()


# پنل اصلی

async def send_panel(app):

    buttons = [
        ("🟢 کد ناهار نجف می‌فروشم", "najaf_sell"),
        ("🔵 کد ناهار نجف می‌خرم", "najaf_buy"),
        ("🌙 کد شام نجف می‌فروشم", "najaf_dinner_sell"),
        ("🌙 کد شام نجف می‌خرم", "najaf_dinner_buy"),
        ("🟠 کد ناهار بابایی می‌فروشم", "babayi_sell"),
        ("🟣 کد ناهار بابایی می‌خرم", "babayi_buy"),
        ("🌙 کد شام بابایی می‌فروشم", "babayi_dinner_sell"),
        ("🌙 کد شام بابایی می‌خرم", "babayi_dinner_buy"),
        ("🟡 کد ناهار بقیه الله می‌فروشم", "baghi_sell"),
        ("🔵 کد ناهار بقیه الله می‌خرم", "baghi_buy"),
        ("🔄 معاوضه کد غذا", "exchange"),
    ]

    keyboard = [
        [InlineKeyboardButton(text, callback_data=callback)]
        for text, callback in buttons
    ]

    sent = await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    data["panel_message_id"] = sent.message_id
    save_data()


# حذف خودکار هشدارها

async def delete_later(message, seconds=WARNING_SECONDS):

    await asyncio.sleep(seconds)

    try:
        await message.delete()
    except Exception:
        pass

    untrack_message(message.message_id)


# هشدار موقت

async def send_temporary_warning(
    context,
    text,
    user_id,
    previous=None
):

    keyboard = None

    if previous:

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🗑 حذف درخواست قبلی",
                callback_data=(
                    f"remove:{user_id}:{previous['message_id']}"
                ),
            )
        ]])

    msg = await context.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        reply_markup=keyboard
    )

    track_message(msg.message_id)

    asyncio.create_task(delete_later(msg))


# پاک سازی کامل پیام های ربات در نیمه شب

async def midnight_cleanup(app):

    logging.info("شروع پاک سازی نیمه شب")

    panel_id = data.get("panel_message_id")

    for message_id in list(data["bot_messages"]):

        if message_id == panel_id:
            continue

        try:
            await app.bot.delete_message(
                chat_id=GROUP_ID,
                message_id=message_id
            )

        except Exception:
            logging.warning(
                "حذف پیام %s ناموفق بود",
                message_id
            )

    # فقط پنل باقی می ماند

    data["bot_messages"] = (
        [panel_id] if panel_id else []
    )

    # پاک کردن درخواست های فعال

    data["active"] = {}

    # صفر کردن محدودیت 15 دقیقه ای

    data["cooldowns"] = {}

    data["reminder_message_id"] = None
    data["reminder_delete_at"] = None

    save_data()

    logging.info("پاک سازی نیمه شب انجام شد")


# زمان بندی روزانه ساعت 12 شب

async def midnight_scheduler(app):

    while True:

        now = current_iran_time()

        next_midnight = (
            now + timedelta(days=1)
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        seconds = (
            next_midnight - now
        ).total_seconds()

        logging.info(
            "زمان باقی مانده تا پاک سازی: %s ثانیه",
            int(seconds)
        )

        await asyncio.sleep(seconds)

        try:
            await midnight_cleanup(app)

        except Exception:
            logging.exception(
                "خطا در پاک سازی نیمه شب"
            )


# محاسبه چهارشنبه آینده ساعت 6 صبح

def next_wednesday_morning():

    now = current_iran_time()

    days = (2 - now.weekday()) % 7

    target = (
        now + timedelta(days=days)
    ).replace(
        hour=6,
        minute=0,
        second=0,
        microsecond=0
    )

    if target <= now:
        target += timedelta(days=7)

    return target


# ارسال پیام یادآوری چهارشنبه

async def send_reminder(app):

    msg = await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا رزرو کنید یادتون نره 😉"
    )

    data["reminder_message_id"] = msg.message_id

    delete_at = (
        current_iran_time().replace(
            hour=15,
            minute=0,
            second=0,
            microsecond=0
        )
    )

    data["reminder_delete_at"] = delete_at.isoformat()

    track_message(msg.message_id)


# زمان بندی هفتگی چهارشنبه

async def reminder_scheduler(app):

    # اگر پیام قبلی هنوز باید حذف شود

    reminder_id = data.get("reminder_message_id")
    delete_at_text = data.get("reminder_delete_at")

    if reminder_id and delete_at_text:

        try:
            delete_at = datetime.fromisoformat(
                delete_at_text
            )

            now = current_iran_time()

            if now < delete_at:

                await asyncio.sleep(
                    (delete_at - now).total_seconds()
                )

                try:
                    await app.bot.delete_message(
                        chat_id=GROUP_ID,
                        message_id=reminder_id
                    )
                except Exception:
                    pass

            untrack_message(reminder_id)

        except Exception:
            logging.exception(
                "خطا در حذف یادآوری قبلی"
            )

        data["reminder_message_id"] = None
        data["reminder_delete_at"] = None
        save_data()

    while True:

        target = next_wednesday_morning()

        seconds = (
            target - current_iran_time()
        ).total_seconds()

        logging.info(
            "زمان باقی مانده تا یادآوری چهارشنبه: %s ثانیه",
            int(seconds)
        )

        await asyncio.sleep(seconds)

        try:

            await send_reminder(app)

            logging.info(
                "پیام یادآوری چهارشنبه ارسال شد"
            )

            # انتظار تا ساعت 3 بعدازظهر

            now = current_iran_time()

            delete_at = now.replace(
                hour=15,
                minute=0,
                second=0,
                microsecond=0
            )

            await asyncio.sleep(
                max(
                    0,
                    (delete_at - now).total_seconds()
                )
            )

            reminder_id = data.get(
                "reminder_message_id"
            )

            if reminder_id:

                try:
                    await app.bot.delete_message(
                        chat_id=GROUP_ID,
                        message_id=reminder_id
                    )
                except Exception:
                    pass

                untrack_message(reminder_id)

            data["reminder_message_id"] = None
            data["reminder_delete_at"] = None

            save_data()

            logging.info(
                "پیام یادآوری چهارشنبه حذف شد"
            )

        except Exception:
            logging.exception(
                "خطا در برنامه یادآوری چهارشنبه"
            )


# مدیریت دکمه ها

async def button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query is None:
        return

    user = query.from_user
    user_id = str(user.id)

    try:
        await query.answer()
    except Exception:
        pass

    # حذف درخواست توسط صاحب درخواست

    if query.data.startswith("delete:"):

        try:
            owner_id = int(
                query.data.split(":", 1)[1]
            )
        except (ValueError, IndexError):
            return

        if user.id != owner_id:
            return

        try:
            await query.message.delete()
        except Exception:
            return

        untrack_message(
            query.message.message_id
        )

        active = data["active"].get(user_id)

        if (
            active
            and active.get("message_id")
            == query.message.message_id
        ):

            data["active"].pop(user_id, None)
            save_data()

        return

    # حذف درخواست قبلی از طریق هشدار

    if query.data.startswith("remove:"):

        try:
            _, owner_text, message_text = (
                query.data.split(":", 2)
            )

            owner_id = int(owner_text)
            message_id = int(message_text)

        except (ValueError, IndexError):
            return

        if user.id != owner_id:
            return

        active = data["active"].get(user_id)

        if (
            active
            and active.get("message_id") == message_id
        ):

            try:
                await context.bot.delete_message(
                    chat_id=GROUP_ID,
                    message_id=message_id
                )
            except Exception:
                pass

            untrack_message(message_id)

            data["active"].pop(user_id, None)
            save_data()

        try:
            await query.message.delete()
        except Exception:
            pass

        untrack_message(
            query.message.message_id
        )

        return

    # گزینه های پنل

    options = {

        "najaf_sell": "🟢 کد ناهار نجف می‌فروشم",
        "najaf_buy": "🔵 کد ناهار نجف می‌خرم",

        "najaf_dinner_sell": "🌙 کد شام نجف می‌فروشم",
        "najaf_dinner_buy": "🌙 کد شام نجف می‌خرم",

        "babayi_sell": "🟠 کد ناهار بابایی می‌فروشم",
        "babayi_buy": "🟣 کد ناهار بابایی می‌خرم",

        "babayi_dinner_sell": "🌙 کد شام بابایی می‌فروشم",
        "babayi_dinner_buy": "🌙 کد شام بابایی می‌خرم",

        "baghi_sell": "🟡 کد ناهار بقیه الله می‌فروشم",
        "baghi_buy": "🔵 کد ناهار بقیه الله می‌خرم",

        "exchange": "🔄 معاوضه کد غذا",
    }

    if query.data not in options:
        return

    request_text = options[query.data]

    now = current_iran_time()

    today = now.date().isoformat()

    # محدودیت 15 دقیقه ای

    cooldown_value = data["cooldowns"].get(user_id)

    if cooldown_value:

        try:

            cooldown_until = datetime.fromisoformat(
                cooldown_value
            )

            if now < cooldown_until:

                remaining = (
                    cooldown_until - now
                )

                seconds_left = int(
                    remaining.total_seconds()
                )

                minutes_left = max(
                    1,
                    (seconds_left + 59) // 60
                )

                await send_temporary_warning(
                    context,
                    (
                        f"⏳ لطفاً {minutes_left} دقیقه دیگر صبر کنید؛ "
                        "بعد از ثبت هر درخواست باید ۱۵ دقیقه "
                        "برای درخواست بعدی صبر کنید."
                    ),
                    user.id
                )

                return

        except ValueError:

            data["cooldowns"].pop(user_id, None)

    # جلوگیری از درخواست فعال در همان روز

    active = data["active"].get(user_id)

    if active and active.get("date") == today:

        await send_temporary_warning(
            context,
            (
                "⚠️ شما امروز یک درخواست ثبت کرده‌اید.\n"
                "برای ثبت درخواست جدید، ابتدا درخواست قبلی "
                "خود را حذف کنید.\n"
                "پس از ثبت درخواست جدید باید ۱۵ دقیقه صبر کنید."
            ),
            user.id,
            active
        )

        return

    # تاریخ شمسی

    jalali = jdatetime.datetime.fromgregorian(
        datetime=now
    )

    weekdays = {
        0: "شنبه",
        1: "یکشنبه",
        2: "دوشنبه",
        3: "سه‌شنبه",
        4: "چهارشنبه",
        5: "پنجشنبه",
        6: "جمعه",
    }

    months = {
        1: "فروردین",
        2: "اردیبهشت",
        3: "خرداد",
        4: "تیر",
        5: "مرداد",
        6: "شهریور",
        7: "مهر",
        8: "آبان",
        9: "آذر",
        10: "دی",
        11: "بهمن",
        12: "اسفند",
    }

    date_text = (
        f"{weekdays[jalali.weekday()]}، "
        f"{jalali.day} {months[jalali.month]} "
        f"{jalali.year}"
    )

    time_text = now.strftime("%H:%M:%S")

    name = (
        user.full_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    message_text = (
        f'<a href="tg://user?id={user.id}">{name}</a>\n'
        f"{request_text}\n\n"
        f"📅 {date_text}\n"
        f"⏰ ساعت ایران: {time_text}"
    )

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🗑 حذف پیام",
                callback_data=f"delete:{user.id}"
            )
        ]]
    )

    sent = await context.bot.send_message(
        chat_id=GROUP_ID,
        text=message_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    track_message(sent.message_id)

    data["active"][user_id] = {
        "message_id": sent.message_id,
        "date": today
    }

    data["cooldowns"][user_id] = (
        now + timedelta(
            minutes=COOLDOWN_MINUTES
        )
    ).isoformat()

    save_data()


# راه اندازی اولیه

async def post_init(app):

    try:

        await send_panel(app)

        logging.info(
            "پنل با موفقیت ارسال شد."
        )

    except Exception:

        logging.exception(
            "خطا در ارسال پنل"
        )

        raise

    # شروع برنامه پاک سازی نیمه شب

    app.create_task(
        midnight_scheduler(app)
    )

    # شروع برنامه یادآوری چهارشنبه

    app.create_task(
        reminder_scheduler(app)
    )

    logging.info(
        "زمان بندی پاک سازی و یادآوری فعال شد."
    )


async def on_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logging.error(
        "خطا هنگام پردازش درخواست تلگرام:",
        exc_info=context.error
    )


# اجرای ربات

def main():

    threading.Thread(
        target=start_web_server,
        daemon=True
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
        .build()
    )

    app.add_handler(
        CallbackQueryHandler(button)
    )

    app.add_error_handler(on_error)

    logging.info(
        "ربات کد غذا در حال راه اندازی است."
    )

    app.run_polling(
        bootstrap_retries=-1,
        poll_interval=1,
        timeout=30,
        drop_pending_updates=False
    )


if __name__ == "__main__":
    main()
