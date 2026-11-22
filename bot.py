import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import jdatetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)

from telegram.error import TelegramError

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ---------------- تنظیمات اصلی ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_ID = 2022751165
GROUP_ID = -1004389774687

DATA_FILE = os.getenv("DATA_FILE", "requests.json")

IRAN_TZ = ZoneInfo("Asia/Tehran")

COOLDOWN_MINUTES = 15
WARNING_SECONDS = 10
AUTH_WARNING_SECONDS = 5
HEALTH_CHECK_SECONDS = 30

BOT_CONNECTION_STATUS = "در حال راه‌اندازی"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN در Environment تنظیم نشده است.")


# ---------------- کاربران از قبل احراز هویت شده ----------------

PRE_VERIFIED_USER_IDS = {
    7594827517,
    6161866923,
    6771302483,
    1391246916,
    7120252179,
    5927912295,
    7836222001,
    978299343,
    5353288599,
    657971495,
    5835535949,
    6543372135,
    8151777470,
    6093298995,
    6994388972,
    1317571780,
    1264345070,
    2022751165,
    1340565729,
    1240411327,
    2118879830,
    8915144118,
    8738938328,
    7729420196,
    1476787682,
    5497361720,
    7318089951,
    5835743385,
    522918913,
    937434125,
    1407796961,
    9078388763,
    6802378228,
    5643714988,
    1678654655,
    7173682763,
    5932482562,
    5727822354,
    1511072233,
    1461126069,
    5882458136,
    8122606051,
    7468183827,
    868581419,
    8821648792,
    8706932689,
    8931394611,
    8294623660,
    8479777892,
    7906982364,
    8362957817,
    6548736530,
    8939468486,
    6787610432,
    619728265,
    902008819,
    8738733398,
    7331326121,
    172024828,
    7147148898,
    8103852169,
    7145762745,
    8091545739,
    5418668780,
    7629326045,
    300827321,
    1213472115,
    7018560045,
    8982077402,
    7286664294,
    7816621670,
    1398908334,
    2097267366,
    6018068274,
    1605269682,
    8081200627,
    8307772084,
    7022128018,
    6150262700,
    8292580493,
    8805655838,
    973632982,
    5778378885,
    546109160,
    7067056421,
    5125978909,
    7191541874,
    6379787802,
    7733152239,
    8589829171,
    6458872358,
    9262245699,
    5308654949,
    6873260419,
    7853317833,
    146918379,
    7251572110,
    1892323087,
    1784545920,
    5525364811,
    8895463188,
    5665275641,
    2027218559,
    618578353,
    8962604561,
    2096897699,
    5857555549,
    7719542934,
}


# ---------------- ذخیره اطلاعات ----------------

def load_data():

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)

        if not isinstance(result, dict):
            result = {}

    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        result = {}

    result.setdefault("active", {})
    result.setdefault("cooldowns", {})
    result.setdefault("bot_messages", [])
    result.setdefault("panel_message_id", None)
    result.setdefault("reminder_message_id", None)
    result.setdefault("verified", {})
    result.setdefault("phone_to_user", {})

    if not isinstance(result["verified"], dict):
        result["verified"] = {}

    if not isinstance(result["phone_to_user"], dict):
        result["phone_to_user"] = {}

    # ثبت کاربران قبلاً احراز هویت شده
    for user_id in PRE_VERIFIED_USER_IDS:

        result["verified"].setdefault(
            str(user_id),
            {
                "phone": "",
                "verified_at": "ثبت‌شده در فهرست ثابت",
                "name": "",
                "username": "",
            },
        )

    return result


data = load_data()


def save_data():

    temp_file = DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, DATA_FILE)


def current_time():
    return datetime.now(IRAN_TZ)


def track_message(message_id):

    if message_id not in data["bot_messages"]:
        data["bot_messages"].append(message_id)
        save_data()


def untrack_message(message_id):

    if message_id in data["bot_messages"]:
        data["bot_messages"].remove(message_id)
        save_data()


def normalize_phone(phone):

    translation = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789",
    )

    phone = str(phone).translate(translation)

    digits = "".join(ch for ch in phone if ch.isdigit())

    if digits.startswith("0098"):
        digits = digits[2:]

    elif digits.startswith("0") and len(digits) == 11:
        digits = "98" + digits[1:]

    elif len(digits) == 10 and digits.startswith("9"):
        digits = "98" + digits

    return digits


def is_verified(user_id):

    return (
        str(user_id) in data["verified"]
        or int(user_id) in PRE_VERIFIED_USER_IDS
    )


# ---------------- پیام مدیر ----------------

async def notify_admin(app, message):

    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=message,
        )

    except TelegramError:
        logging.exception("ارسال پیام به مدیر ناموفق بود.")


# ---------------- شروع ربات ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    if context.args and context.args[0] == "verify":

        if is_verified(user.id):

            await message.reply_text(
                "✅ احراز هویت شما قبلاً انجام شده است.\n"
                "🟢 وضعیت حساب: احراز هویت شده",
                reply_markup=ReplyKeyboardRemove(),
            )

            return

        keyboard = ReplyKeyboardMarkup(
            [[
                KeyboardButton(
                    "🟢 تأیید و احراز هویت",
                    request_contact=True,
                )
            ]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await message.reply_text(
            "برای تکمیل احراز هویت، دکمه زیر را بزنید.\n\n"
            "⚠️ فقط مخاطب متعلق به همین حساب تلگرام پذیرفته می‌شود.",
            reply_markup=keyboard,
        )

        return

    if user.id == ADMIN_ID:

        keyboard = ReplyKeyboardMarkup(
            [["📡 وضعیت ربات"]],
            resize_keyboard=True,
        )

        await message.reply_text(
            "سلام مدیر عزیز ❤️\n\n"
            "به پنل وضعیت ربات خوش آمدی.\n"
            "برای مشاهده وضعیت اتصال، دکمه زیر را بزن.",
            reply_markup=keyboard,
        )

        return

    if is_verified(user.id):

        await message.reply_text(
            "سلام ❤️\n"
            "🟢 وضعیت حساب شما: احراز هویت شده"
        )

    else:

        await message.reply_text(
            "سلام ❤️\n"
            "برای ثبت درخواست خرید یا فروش در گروه، "
            "ابتدا باید احراز هویت کنید."
        )


async def private_status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    message = update.effective_message

    if not user or not message or user.id != ADMIN_ID:
        return

    if message.text != "📡 وضعیت ربات":
        return

    if BOT_CONNECTION_STATUS == "وصل":
        status_text = "🟢 وضعیت ربات: وصل است."

    elif BOT_CONNECTION_STATUS == "قطع":
        status_text = "🔴 وضعیت ربات: قطع است."

    else:
        status_text = "🟡 وضعیت ربات: در حال راه‌اندازی است."

    await message.reply_text(status_text)


# ---------------- احراز هویت کاربران ----------------

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    message = update.effective_message

    if not user or not message or not message.contact:
        return

    if update.effective_chat.type != "private":
        return

    contact = message.contact

    if not contact.user_id or contact.user_id != user.id:

        await message.reply_text(
            "❌ این مخاطب متعلق به حساب تلگرام شما نیست.\n"
            "لطفاً مخاطب خودتان را ارسال کنید."
        )

        return

    phone = normalize_phone(contact.phone_number)

    if not phone:

        await message.reply_text(
            "❌ دریافت اطلاعات مخاطب ناموفق بود."
        )

        return

    user_key = str(user.id)

    owner_id = data["phone_to_user"].get(phone)

    if owner_id and str(owner_id) != user_key:

        await message.reply_text(
            "❌ این شماره قبلاً برای حساب تلگرام دیگری ثبت شده است.\n"
            "در صورت اشتباه، با مدیر ربات تماس بگیرید.",
            reply_markup=ReplyKeyboardRemove(),
        )

        await notify_admin(
            context.application,
            "⚠️ تلاش برای ثبت شماره تکراری\n\n"
            f"نام: {escape(user.full_name)}\n"
            f"آیدی تلگرام: {user.id}"
        )

        return

    old_record = data["verified"].get(user_key)

    if old_record:

        old_phone = old_record.get("phone")

        if old_phone and data["phone_to_user"].get(old_phone) == user_key:
            data["phone_to_user"].pop(old_phone, None)

    data["verified"][user_key] = {
        "phone": phone,
        "verified_at": current_time().isoformat(),
        "name": user.full_name,
        "username": user.username or "",
    }

    data["phone_to_user"][phone] = user_key

    save_data()

    await message.reply_text(
        "✅ احراز هویت شما با موفقیت انجام شد.\n\n"
        "اکنون می‌توانید از امکانات ربات کد غذا استفاده کنید.\n"
        "🟢 وضعیت حساب: احراز هویت شده",
        reply_markup=ReplyKeyboardRemove(),
    )

    await notify_admin(
        context.application,
        "🟢 کاربر جدید احراز هویت شد\n\n"
        f"نام: {escape(user.full_name)}\n"
        f"نام کاربری: @{user.username if user.username else 'ندارد'}\n"
        f"آیدی تلگرام: {user.id}\n"
        f"شماره تماس: +{phone}\n"
        f"زمان: {current_time().strftime('%Y-%m-%d %H:%M:%S')}"
    )


# ---------------- وب‌سرور Render ----------------

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_web_server():

    port = int(os.environ.get("PORT", "10000"))

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )

    logging.info("Health server started on port %s", port)

    server.serve_forever()


# ---------------- دکمه‌های پنل گروه ----------------

OPTIONS = {

    "najaf_sell": "🟢 کد ناهار نجف می‌فروشم",
    "najaf_buy": "🔵 کد ناهار نجف می‌خرم",

    "najaf_dinner_sell": "🌙 کد شام نجف می‌فروشم",
    "najaf_dinner_buy": "🌙 کد شام نجف می‌خرم",

    "babayi_sell": "🟠 کد ناهار بابایی می‌فروشم",
    "babayi_buy": "🟣 کد ناهار بابایی می‌خرم",

    "babayi_dinner_sell": "🌙 کد شام بابایی می‌فروشم",
    "babayi_dinner_buy": "🌙 کد شام بابایی می‌خرم",

    "baghi_sell": "🟡 کد ناهار بقیه‌الله می‌فروشم",
    "baghi_buy": "🔵 کد ناهار بقیه‌الله می‌خرم",

    "exchange": "🔄 معاوضه کد غذا",
}


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

    context.application.create_task(
        delete_later(msg)
    )


# ---------------- پیام احراز هویت در گروه ----------------

async def send_verification_warning(context, user):

    me = await context.bot.get_me()

    verify_url = f"https://t.me/{me.username}?start=verify"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔐 ورود به ربات و احراز هویت",
            url=verify_url,
        )
    ]])

    msg = await context.bot.send_message(
        chat_id=GROUP_ID,
        text=(
            f"🔒 {escape(user.full_name)} عزیز،\n"
            "برای ثبت درخواست خرید یا فروش، "
            "ابتدا باید احراز هویت کنید.\n"
            "لطفاً از دکمه زیر وارد پیوی ربات شوید."
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    track_message(msg.message_id)

    context.application.create_task(
        delete_later(msg, AUTH_WARNING_SECONDS)
    )


# ---------------- پاک‌سازی نیمه‌شب ----------------

async def midnight_cleanup(app):

    logging.info("شروع پاک‌سازی نیمه‌شب")

    panel_id = data.get("panel_message_id")

    for message_id in list(data["bot_messages"]):

        if message_id == panel_id:
            continue

        try:

            await app.bot.delete_message(
                chat_id=GROUP_ID,
                message_id=message_id,
            )

        except TelegramError:

            logging.warning(
                "حذف پیام %s ناموفق بود.",
                message_id,
            )

    data["bot_messages"] = [panel_id] if panel_id else []

    data["active"] = {}
    data["cooldowns"] = {}
    data["reminder_message_id"] = None

    save_data()

    logging.info("پاک‌سازی نیمه‌شب تمام شد.")


async def midnight_scheduler(app):

    while True:

        now = current_time()

        next_midnight = (
            now + timedelta(days=1)
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        seconds = (next_midnight - now).total_seconds()

        await asyncio.sleep(max(1, seconds))

        try:

            await midnight_cleanup(app)

        except Exception:

            logging.exception("خطا در پاک‌سازی نیمه‌شب")


# ---------------- یادآوری چهارشنبه ----------------

def next_wednesday_reminder():

    now = current_time()

    days = (2 - now.weekday()) % 7

    target = (
        now + timedelta(days=days)
    ).replace(
        hour=0,
        minute=1,
        second=0,
        microsecond=0,
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

    track_message(msg.message_id)

    save_data()


async def reminder_scheduler(app):

    while True:

        target = next_wednesday_reminder()

        seconds = (target - current_time()).total_seconds()

        await asyncio.sleep(max(1, seconds))

        try:

            await send_reminder(app)

            logging.info("یادآوری چهارشنبه ارسال شد.")

        except Exception:

            logging.exception("ارسال یادآوری ناموفق بود.")


# ---------------- بررسی اتصال تلگرام ----------------

async def connection_monitor(app):

    global BOT_CONNECTION_STATUS

    while True:

        await asyncio.sleep(HEALTH_CHECK_SECONDS)

        try:

            await app.bot.get_me()

            if BOT_CONNECTION_STATUS != "وصل":

                BOT_CONNECTION_STATUS = "وصل"

                await notify_admin(
                    app,
                    "🟢 ربات وصل شد؛ وضعیت ربات وصل است."
                )

        except Exception:

            logging.exception("بررسی اتصال تلگرام ناموفق بود.")

            if BOT_CONNECTION_STATUS != "قطع":

                BOT_CONNECTION_STATUS = "قطع"

                await notify_admin(
                    app,
                    "🔴 ربات قطع شد؛ ارتباط با تلگرام برقرار نیست."
                )


# ---------------- مدیریت دکمه‌های پنل ----------------

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if not query or not query.from_user:
        return

    user = query.from_user

    user_id = str(user.id)

    try:
        await query.answer()

    except TelegramError:
        pass

    # حذف درخواست توسط صاحب درخواست

    if query.data.startswith("delete:"):

        try:
            owner_id = int(query.data.split(":", 1)[1])

        except ValueError:
            return

        if user.id != owner_id or not query.message:
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

    # حذف درخواست قبلی از طریق هشدار

    if query.data.startswith("remove:"):

        try:

            _, owner_text, message_text = query.data.split(":", 2)

            owner_id = int(owner_text)
            message_id = int(message_text)

        except ValueError:
            return

        if user.id != owner_id:
            return

        active = data["active"].get(user_id)

        if active and active.get("message_id") == message_id:

            try:

                await context.bot.delete_message(
                    chat_id=GROUP_ID,
                    message_id=message_id,
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

    # بررسی احراز هویت

    if not is_verified(user.id):

        try:
            await send_verification_warning(context, user)

        except TelegramError:
            logging.exception("ارسال پیام احراز هویت ناموفق بود.")

        return

    request_text = OPTIONS[query.data]

    now = current_time()

    today = now.date().isoformat()

    # محدودیت ۱۵ دقیقه‌ای

    cooldown_value = data["cooldowns"].get(user_id)

    if cooldown_value:

        try:

            cooldown_until = datetime.fromisoformat(cooldown_value)

            if now < cooldown_until:

                seconds_left = int(
                    (cooldown_until - now).total_seconds()
                )

                minutes_left = max(
                    1,
                    (seconds_left + 59) // 60,
                )

                await send_temporary_warning(
                    context,
                    f"⏳ لطفاً {minutes_left} دقیقه دیگر صبر کنید.",
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
            "برای ثبت درخواست جدید، ابتدا درخواست قبلی را حذف کنید.",
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
        f"{weekdays[jalali.togregorian().weekday()]}، "
        f"{jalali.day} {months[jalali.month]} {jalali.year}"
    )

    time_text = now.strftime("%H:%M:%S")

    name = escape(user.full_name)

    message_text = (
        f'<a href="tg://user?id={user.id}">{name}</a>\n'
        f"{request_text}\n"
        "🟢 احراز هویت شده\n\n"
        f"📅 {date_text}\n"
        f"⏰ ساعت ایران: {time_text}"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🗑 حذف پیام",
            callback_data=f"delete:{user.id}",
        )
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


# ---------------- راه‌اندازی ربات ----------------

async def post_init(app):

    global BOT_CONNECTION_STATUS

    BOT_CONNECTION_STATUS = "در حال راه‌اندازی"

    await notify_admin(
        app,
        "🟡 ربات در حال راه‌اندازی است."
    )

    try:

        await app.bot.get_me()

        BOT_CONNECTION_STATUS = "وصل"

        await notify_admin(
            app,
            "🟢 ربات وصل شد؛ وضعیت ربات وصل است."
        )

    except Exception:

        BOT_CONNECTION_STATUS = "قطع"

        logging.exception("اتصال اولیه به تلگرام ناموفق بود.")

        await notify_admin(
            app,
            "🔴 اتصال اولیه برقرار نشد؛ "
            "ربات در حال تلاش برای اتصال مجدد است."
        )

    app.create_task(midnight_scheduler(app))

    app.create_task(reminder_scheduler(app))

    app.create_task(connection_monitor(app))


async def post_shutdown(app):

    logging.info("ربات در حال خاموش شدن است.")


async def on_error(update, context):

    logging.error(
        "خطای ربات:",
        exc_info=context.error,
    )


# ---------------- اجرای اصلی ----------------

def main():

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

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.CONTACT,
            receive_contact,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            private_status,
        )
    )

    app.add_handler(
        CallbackQueryHandler(button)
    )

    app.add_error_handler(on_error)

    logging.info("ربات در حال اجرا است.")

    app.run_polling(
        bootstrap_retries=-1,
        poll_interval=1,
        timeout=30,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
