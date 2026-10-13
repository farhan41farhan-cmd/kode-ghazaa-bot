import os
import json
import threading
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer

import jdatetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = -1004389774687
DATA_FILE = "requests.json"
IRAN_TZ = ZoneInfo("Asia/Tehran")
COOLDOWN_MINUTES = 15
WARNING_SECONDS = 10


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Invalid data")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        data = {}
    data.setdefault("active", {})
    data.setdefault("cooldowns", {})
    return data


data = load_data()


def save_data():
    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, DATA_FILE)


# Health check server for Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


async def send_panel(app):
    keyboard = [
        [
            InlineKeyboardButton("🟢 کد نجف می‌فروشم", callback_data="najaf_sell"),
            InlineKeyboardButton("🔵 کد نجف می‌خرم", callback_data="najaf_buy"),
        ],
        [
            InlineKeyboardButton("🟠 کد بابایی می‌فروشم", callback_data="babayi_sell"),
            InlineKeyboardButton("🟣 کد بابایی می‌خرم", callback_data="babayi_buy"),
        ],
        [InlineKeyboardButton("🔄 معاوضه کد غذا", callback_data="exchange")],
    ]
    await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_later(message, seconds=WARNING_SECONDS):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except Exception:
        pass


async def send_temporary_warning(context, text, user_id, previous=None):
    keyboard = None
    if previous:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑️ حذف درخواست قبلی", callback_data=f"remove:{user_id}:{previous['message_id']}")
        ]])
    msg = await context.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        reply_markup=keyboard,
    )
    asyncio.create_task(delete_later(msg))


def current_iran_time():
    return datetime.now(IRAN_TZ)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)

    try:
        await query.answer()
    except Exception:
        pass

    # Delete the user's own request message
    if query.data.startswith("delete:"):
        try:
            owner_id = int(query.data.split(":", 1)[1])
        except (ValueError, IndexError):
            return
        if user.id != owner_id:
            return
        try:
            await query.message.delete()
        except Exception:
            return
        active = data["active"].get(user_id)
        if active and active.get("message_id") == query.message.message_id:
            data["active"].pop(user_id, None)
            save_data()
        return

    # Delete a previous request from the warning button
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
                await context.bot.delete_message(chat_id=GROUP_ID, message_id=message_id)
            except Exception:
                pass
            data["active"].pop(user_id, None)
            save_data()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    options = {
        "najaf_sell": "🟢 کد نجف می‌فروشم",
        "najaf_buy": "🔵 کد نجف می‌خرم",
        "babayi_sell": "🟠 کد بابایی می‌فروشم",
        "babayi_buy": "🟣 کد بابایی می‌خرم",
        "exchange": "🔄 معاوضه کد غذا",
    }
    if query.data not in options:
        return
    request_text = options[query.data]

    now = current_iran_time()
    today = now.date().isoformat()

    # 15-minute cooldown, even if the user deleted the previous request
    cooldown_value = data["cooldowns"].get(user_id)
    if cooldown_value:
        try:
            cooldown_until = datetime.fromisoformat(cooldown_value)
            if now < cooldown_until:
                remaining = cooldown_until - now
                seconds_left = int(remaining.total_seconds())
                minutes_left = max(1, (seconds_left + 59) // 60)
                await send_temporary_warning(
                    context,
                    f"⏳ لطفاً {minutes_left} دقیقه دیگر صبر کنید؛ بعد از ثبت هر درخواست باید ۱۵ دقیقه برای درخواست بعدی صبر کنید.",
                    user.id,
                )
                return
        except ValueError:
            data["cooldowns"].pop(user_id, None)

    # If there is already an active request today, ask them to remove it first
    active = data["active"].get(user_id)
    if active and active.get("date") == today:
        await send_temporary_warning(
            context,
            "⚠️ شما امروز یک درخواست ثبت کرده‌اید.\nبرای ثبت درخواست جدید، ابتدا درخواست قبلی خود را حذف کنید.\nپس از ثبت درخواست جدید باید ۱۵ دقیقه صبر کنید.",
            user.id,
            active,
        )
        return

    jalali = jdatetime.datetime.fromgregorian(datetime=now)
    weekdays = {0: "شنبه", 1: "یکشنبه", 2: "دوشنبه", 3: "سه‌شنبه", 4: "چهارشنبه", 5: "پنجشنبه", 6: "جمعه"}
    months = {1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر", 5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان", 9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"}
    date_text = f"{weekdays[jalali.weekday()]}، {jalali.day} {months[jalali.month]} {jalali.year}"
    time_text = now.strftime("%H:%M:%S")

    name = (user.full_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
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

    data["active"][user_id] = {
        "message_id": sent.message_id,
        "date": today,
    }
    data["cooldowns"][user_id] = (now + timedelta(minutes=COOLDOWN_MINUTES)).isoformat()
    save_data()


async def post_init(app):
    await send_panel(app)


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

    app.add_handler(CallbackQueryHandler(button))

    app.run_polling(
        bootstrap_retries=-1,
        poll_interval=1,
        timeout=30,
        drop_pending_updates=False
    )


if __name__ == "__main__":
    main()
