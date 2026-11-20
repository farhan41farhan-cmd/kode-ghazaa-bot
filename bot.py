
# ---------------- راه اندازی اولیه ----------------

async def post_init(app):
    try:
        await send_panel(app)

        logging.info("پنل با موفقیت آماده شد.")

    except Exception:
        logging.exception("خطا در ارسال پنل")
        raise

    # پاک سازی نیمه شب
    app.create_task(midnight_scheduler(app))

    # یادآوری چهارشنبه
    app.create_task(reminder_scheduler(app))

    logging.info("زمان بندی پاک سازی و یادآوری فعال شد.")

# ---------------- مدیریت خطا ----------------

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(
        "خطا هنگام پردازش درخواست تلگرام:",
        exc_info=context.error
    )

# ---------------- اجرای ربات ----------------

def main():

    # راه اندازی وب سرور Render
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

    # دستور استارت
    app.add_handler(
        CommandHandler("start", start)
    )

    # دکمه های پنل
    app.add_handler(
        CallbackQueryHandler(button)
    )

    # مدیریت خطا
    app.add_error_handler(on_error)

    logging.info("ربات کد غذا در حال راه اندازی است.")

    # اجرای ربات
    app.run_polling(
        bootstrap_retries=-1,
        poll_interval=1,
        timeout=30,
        drop_pending_updates=False
    )

if __name__ == "__main__":
    main()
