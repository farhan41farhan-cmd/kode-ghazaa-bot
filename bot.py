import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]

GROUP_ID = -1004389774687


async def send_panel(app):
    keyboard = [
        [
            InlineKeyboardButton("🟢 کد نجف می‌فروشم", callback_data="najaf_sell"),
            InlineKeyboardButton("🔵 کد نجف می‌خرم", callback_data="najaf_buy")
        ],
        [
            InlineKeyboardButton("🟠 کد بابایی می‌فروشم", callback_data="babayi_sell"),
            InlineKeyboardButton("🟣 کد بابایی می‌خرم", callback_data="babayi_buy")
        ]
    ]

    await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🍽 کد غذا\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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

        await query.message.delete()
        return
    else:
        return

    name = (
        user.full_name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    user_link = f"tg://user?id={user.id}"

    message = f'<a href="{user_link}">{name}</a>\n{text}'

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


async def post_init(app):
    await send_panel(app)


def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CallbackQueryHandler(button))

    app.run_polling()


if __name__ == "__main__":
    main()
