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

    # -------------------------
    # اجرای Web Server برای Render
    # -------------------------

    web_thread = threading.Thread(

        target=start_web_server,

        daemon=True

    )

    web_thread.start()


    # -------------------------
    # ساخت Telegram Bot
    # -------------------------

    app = (

        Application.builder()

        .token(TOKEN)

        .post_init(post_init)

        .build()

    )


    # -------------------------
    # Handler دکمه‌ها
    # -------------------------

    app.add_handler(

        CallbackQueryHandler(button)

    )


    # -------------------------
    # اجرای Polling
    # -------------------------

    app.run_polling()


# =========================
# شروع برنامه
# =========================

if __name__ == "__main__":

    main()
