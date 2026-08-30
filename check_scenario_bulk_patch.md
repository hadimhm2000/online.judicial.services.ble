# پچ check_scenario.py — دو تغییر دقیق

این فایل دیف نیست، دو تکه‌کد دقیق است که باید در check_scenario.py جایگزین شوند.
هر دو تکه با `Ctrl+F` روی رشتهٔ منحصربه‌فرد ذکرشده پیدا می‌شوند.

## تغییر ۱ از ۲ — استخراج batch_tracking_code (بالای process_check_task)

جای این خط را در ابتدای process_check_task پیدا کنید (حدود خط ۱۰۱):

```python
    is_bulk_check = data.get("_is_bulk_check", False)
    bulk_row_index = data.get("_bulk_row_index", 0)
```

و بلافاصله بعدش این خط را اضافه کنید:

```python
    is_bulk_check = data.get("_is_bulk_check", False)
    bulk_row_index = data.get("_bulk_row_index", 0)
    batch_tracking_code = data.get("batch_tracking_code", "")
```

---

## تغییر ۲ از ۲ — مسیر موفقیت (ارسال نتیجه)

این تکه را در process_check_task پیدا کنید (حدود خط ۸۳۳ — بعد از چاپ PDF):

```python
            # ── ۱۶. ارسال نتیجه ──────────────────────────────────────────
            from lavayeh_handlers import send_lavayeh_result
            nat_ids = ", ".join([
                p.get("national_id", "") for p in plaintiffs if p.get("national_id")
            ])

            if pdf_path and os.path.exists(pdf_path):
                await send_lavayeh_result(
                    bot, user_id, pdf_path, final_total,
                    tracking_code=bill_no,
                    national_ids=nat_ids,
                    lavayeh_title=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                    lavayeh_province="",
                    lavayeh_row_number=1,
                    lavayeh_persons=plaintiffs,
                    skip_fee_calc=True,
                    is_ezhharnameh=False,
                    service_type="CHECK")
                await bot.send_message(
                    ADMIN_ID,
                    f"✅ [CHECK] ثبت دادخواست چک کاربر {user_id} موفق."
                    f" هزینه: {final_total:,} ریال"
                )
            else:
                await bot.send_message(
                    user_id,
                    f"📄 دادخواست چک با کد بایگانی `{bill_no}` ثبت شد "
                    f"اما خطا در چاپ PDF رخ داد."
                    f"با مدیریت تماس بگیرید.")
                try:
                    from panel_sync import upsert_case_to_panel
                    await upsert_case_to_panel(
                        bale_user_id=user_id, full_name=str(user_id),
                        service_type="CHECK", status="FAILED",
                        tracking_code=bill_no or None,
                        document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                        error_details="ثبت در سامانه انجام شد اما چاپ PDF ناموفق بود",
                        error_step="print_pdf",
                    )
                except Exception as panel_err:
                    logging.warning(f"[CHECK] خطا در ثبت شکست پرونده در پنل: {panel_err}")

            return
```

و آن را با این جایگزین کنید (تنها فرق: شاخه‌بندی bulk/تکی مثل lavayeh_scenario.py،
دقیقاً همان کاری که آنجا هم انجام شده):

```python
            # ── ۱۶. ارسال نتیجه ──────────────────────────────────────────
            from lavayeh_handlers import send_lavayeh_result, send_bulk_item_result
            nat_ids = ", ".join([
                p.get("national_id", "") for p in plaintiffs if p.get("national_id")
            ])

            if pdf_path and os.path.exists(pdf_path):
                if is_bulk_check and batch_tracking_code:
                    # فلوی دسته‌جمعی: بدون فاکتور/امضای انفرادی — فقط اضافه به
                    # signable_items؛ فاکتور تسویه و منوی امضا در پایان کل بچ
                    # توسط finalize_bulk_batch یک‌جا انجام می‌شود.
                    await send_bulk_item_result(
                        bot, user_id, pdf_path, final_total,
                        tracking_code=bill_no,
                        national_ids=nat_ids,
                        lavayeh_title=f"دادخواست چک — {request_title}",
                        batch_tracking_code=batch_tracking_code,
                        row_index=bulk_row_index,
                        lavayeh_persons=plaintiffs,
                        service_type="CHECK")
                else:
                    await send_lavayeh_result(
                        bot, user_id, pdf_path, final_total,
                        tracking_code=bill_no,
                        national_ids=nat_ids,
                        lavayeh_title=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                        lavayeh_province="",
                        lavayeh_row_number=1,
                        lavayeh_persons=plaintiffs,
                        skip_fee_calc=True,
                        is_ezhharnameh=False,
                        service_type="CHECK")
                await bot.send_message(
                    ADMIN_ID,
                    f"✅ [CHECK] ثبت دادخواست چک کاربر {user_id} موفق."
                    f" هزینه: {final_total:,} ریال"
                    + (f" (دسته‌جمعی — ردیف {bulk_row_index} — بچ {batch_tracking_code})" if is_bulk_check else "")
                )
            else:
                await bot.send_message(
                    user_id,
                    f"📄 دادخواست چک با کد بایگانی `{bill_no}` ثبت شد "
                    f"اما خطا در چاپ PDF رخ داد."
                    f"با مدیریت تماس بگیرید.")
                try:
                    from panel_sync import upsert_case_to_panel
                    await upsert_case_to_panel(
                        bale_user_id=user_id, full_name=str(user_id),
                        service_type="CHECK", status="FAILED",
                        tracking_code=bill_no or None,
                        document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                        error_details="ثبت در سامانه انجام شد اما چاپ PDF ناموفق بود",
                        error_step="print_pdf",
                    )
                except Exception as panel_err:
                    logging.warning(f"[CHECK] خطا در ثبت شکست پرونده در پنل: {panel_err}")

                # ── حتی وقتی چاپ PDF شکست خورد، ردیف دسته‌جمعی باید «تمام‌شده»
                # علامت بخورد وگرنه finalize_bulk_batch هرگز صدا زده نمی‌شود
                # (mark_bulk_item_done منتظر تکمیل همهٔ ردیف‌های صف‌شده است).
                if is_bulk_check and batch_tracking_code:
                    try:
                        from bulk_submissions import BULK_TASKS, mark_bulk_item_done
                        if batch_tracking_code in BULK_TASKS:
                            BULK_TASKS[batch_tracking_code].setdefault("failures", []).append({
                                "row_index": bulk_row_index,
                                "tracking_code": bill_no,
                                "title": f"دادخواست چک — {request_title}",
                                "error": "ثبت در سامانه انجام شد اما چاپ PDF ناموفق بود",
                            })
                        await mark_bulk_item_done(bot, user_id, batch_tracking_code)
                    except Exception as log_err:
                        logging.error(f"[CHECK] خطا در mark_bulk_item_done (شکست چاپ PDF): {log_err}")

            return
```

---

## تغییر ۳ (اختیاری ولی توصیه‌شده) — مسیر شکست نهایی پس از max_attempts

این تکه (انتهای process_check_task، داخل `except Exception as e:`، شاخهٔ `else:`
که یعنی آخرین تلاش هم شکست خورد) را پیدا کنید:

```python
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت دادخواست چک با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(ADMIN_ID, f"❌ [CHECK] کاربر {user_id} پس از {max_attempts} تلاش ناموفق.")
                try:
                    from panel_sync import upsert_case_to_panel
                    await upsert_case_to_panel(
                        bale_user_id=user_id, full_name=str(user_id),
                        service_type="CHECK", status="FAILED",
                        tracking_code=tracking_no or None,
                        document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                        error_details=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}",
                        error_step="MAX_RETRIES_EXCEEDED",
                    )
                except Exception as panel_err:
                    logging.warning(f"[CHECK] خطا در ثبت شکست پرونده در پنل: {panel_err}")
```

و بلافاصله قبل از `try: from bug_reporter import report_bug` (که بعد از این
بلوک می‌آید)، این را اضافه کنید — تا این ردیف هم در دسته‌جمعی «تمام‌شده»
علامت بخورد و batch هیچ‌وقت نیمه‌کاره روی completed_count گیر نکند:

```python
                if is_bulk_check and batch_tracking_code:
                    try:
                        from bulk_submissions import BULK_TASKS, mark_bulk_item_done
                        if batch_tracking_code in BULK_TASKS:
                            BULK_TASKS[batch_tracking_code].setdefault("failures", []).append({
                                "row_index": bulk_row_index,
                                "tracking_code": tracking_no,
                                "title": f"دادخواست چک — {request_title}",
                                "error": str(e),
                            })
                        await mark_bulk_item_done(bot, user_id, batch_tracking_code)
                    except Exception as log_err:
                        logging.error(f"[CHECK] خطا در mark_bulk_item_done (شکست قطعی): {log_err}")
```

---

## چرا این ۳ تغییر کافی است

- `send_bulk_item_result` (که از قبل در lavayeh_handlers.py برای لایحه/اظهارنامه
  استفاده می‌شود) کاملاً سرویس‌مستقل نوشته شده: پارامتر `service_type="CHECK"`
  را می‌پذیرد و خودش هم PDF را می‌فرستد، هم آیتم را به
  `BULK_TASKS[batch]["signable_items"]` اضافه می‌کند، هم در پایان
  `mark_bulk_item_done` را صدا می‌زند. یعنی برای مسیر موفقیت، فقط باید آن را
  به‌جای send_lavayeh_result صدا بزنید — کار دیگری لازم نیست.
- `mark_bulk_item_done`/`finalize_bulk_batch` هم کاملاً سرویس‌مستقل‌اند (فقط
  روی `signable_items`/`failures`/`completed_count` کار می‌کنند، هیچ‌جا اسم
  «لایحه» یا «اظهارنامه» را هاردکد نکرده‌اند) — پس بدون هیچ تغییری برای چک
  هم درست کار می‌کنند.
- تنها ریسک واقعی این بود که یک ردیف دسته‌جمعی در مسیرهای شکست (چاپ PDF
  ناموفق / max_attempts تمام شد) هرگز `mark_bulk_item_done` را صدا نزند —
  آن‌وقت `completed_count` هیچ‌وقت به `queued_count` نمی‌رسید و
  `finalize_bulk_batch` (گزارش مالی + فاکتور تسویه + منوی امضا) برای کل بچ
  هرگز اجرا نمی‌شد، حتی اگر همهٔ ردیف‌های دیگر موفق شده بودند. تغییر ۳ دقیقاً
  همین را می‌بندد.
