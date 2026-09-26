name = user.full_name

    # جلوگیری از خراب شدن HTML
    name = (
        name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


    # لینک مستقیم به پروفایل کاربر
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


    # =========================
    # ارسال پیام به گروه
    # =========================

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=message,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# اجرای پنل هنگام شروع بات
# =========================

async def post_init(app):
    await send_panel(app)


# =========================
# اجرای اصلی برنامه
# =========================

def main():

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(
        CallbackQueryHandler(button)
    )

    app.run_polling()


# =========================
# شروع برنامه
# =========================

if __name__ == "__main__":
    main()
