import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import jdatetime
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes


TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = -1004389774687


# =========================
# Web Server برای Render
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    server.serve_forever()


# =========================
# پنل اصلی بات
# =========================

async def send_panel(app):

    keyboard = [
        [
            InlineKeyboardButton(
                "🟢 کد نجف می‌فروشم",
                callback_data="najaf_sell"
            ),
            InlineKeyboardButton(
                "🔵 کد نجف می‌خرم",
                callback_data="najaf_buy"
            )
        ],
        [
            InlineKeyboardButton(
                "🟠 کد بابایی می‌فروشم",
                callback_data="babayi_sell"
            ),
            InlineKeyboardButton(
                "🟣 کد بابایی می‌خرم",
                callback_data="babayi_buy"
            )
        ]
    ]

    await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# دکمه‌های بات
# =========================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    if query.data == "najaf_sell":
        text = "🟢 کد نجف می‌فروشم"

    elif query.data == "najaf_buy":
        text = "🔵 کد نجف می‌خرم"

    elif query.data == "babayi_sell":
        text = "🟠 کد بابایی می‌فروشم"

    elif query.data == "babayi_buy":
        text = "🟣 کد بابایی می‌خرم"

    elif query.data.startswith("delete:"):

        try:
            owner_id = int(query.data.split(":")[1])
        except ValueError:
            return

        if user.id != owner_id:
            await query.answer(
                "❌ این پیام متعلق به شما نیست.",
                show_alert=True
            )
            return

        try:
            await query.message.delete()
        except Exception:
            await query.answer(
                "❌ امکان حذف این پیام وجود ندارد.",
                show_alert=True
            )

        return

    else:
        return

    # =========================
    # ساعت ایران
    # =========================

    iran_time = datetime.now(
        ZoneInfo("Asia/Tehran")
    )

    # =========================
    # تبدیل میلادی به شمسی
    # =========================

    jalali = jdatetime.datetime.fromgregorian(
        datetime=iran_time
    )

    # =========================
    # روزهای هفته شمسی
    # =========================

    weekdays = {
        0: "شنبه",
        1: "یکشنبه",
        2: "دوشنبه",
        3: "سه‌شنبه",
        4: "چهارشنبه",
        5: "پنجشنبه",
        6: "جمعه"
    }

    # =========================
    # ماه‌های شمسی
    # =========================

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
        12: "اسفند"
    }

    weekday = weekdays[jalali.weekday()]
    month = months[jalali.month]

    date_text = (
        f"{weekday}، "
        f"{jalali.day} "
        f"{month} "
        f"{jalali.year}"
    )

    time_text = iran_time.strftime("%H:%M:%S")

    # =========================
    # نام کاربر
    # =========================

    name = user.full_name

    name = (
        name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    # =========================
    # لینک پروفایل کاربر
    # =========================

    user_link = f"tg://user?id={user.id}"

    # =========================
    # متن پیام
    # =========================

    message = (
        f'<a href="{user_link}">{name}</a>\n'
        f'{text}\n\n'
        f'📅 {date_text}\n'
        f'⏰ ساعت ایران: {time_text}'
    )

    # =========================
    # دکمه حذف
    # =========================

    keyboard = [
        [
            InlineKeyboardButton(
                "🗑 حذف پیام",
                callback_data=f"delete:{user.id}"
            )
        ]
    ]

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=message,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# بعد از شروع برنامه
# =========================

async def post_init(app):
    await send_panel(app)


# =========================
# اجرای اصلی برنامه
# =========================

def main():

    # Web Server برای Render
    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True
    )

    web_thread.start()

    # ساخت Telegram Bot
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handler دکمه‌ها
    app.add_handler(
        CallbackQueryHandler(button)
    )

    # اجرای Polling
    app.run_polling()


# =========================
# شروع برنامه
# =========================

if __name__ == "__main__":
    main()
