# -*- coding: utf-8 -*-
"""
admin_forward.py
──────────────────────────────────────────────────────────────────────────
هر بار که کاربر یک درخواست را «تایید و شروع ثبت» می‌کند، همان لحظه (قبل از
هرگونه پردازش خودکار در سنا) یک کپی کامل از تمام اطلاعات وارد‌شده + همهٔ
تصاویر/فایل‌های پیوست، برای ADMIN_ID فرستاده می‌شود.

چرا این کار مهم است: مستقل از باگ‌های احتمالی در مرحلهٔ خودکارسازی
(Playwright/سنا)، مدیر همیشه یک نسخهٔ کامل از درخواست کاربر را دارد و در
صورت خرابی/کرش می‌تواند دستی پیگیری کند. همچنین چون هر کپی با آیدی عددی
کاربر تگ می‌شود، مدیر می‌تواند مستقیماً با `/send <آیدی>` (پیاده‌سازی‌شده در
admin_relay.py) به همان کاربر پاسخ بدهد.

فعلاً فقط برای «چک» پیاده‌سازی و تست شده (send_check_submission_to_admin).
تابع عمومی send_text_dump_to_admin برای استفاده در بقیهٔ سرویس‌ها
(لایحه/اظهارنامه/اعلام وکالت/تجدیدنظر/...) هم آماده است — کافی است دیکشنری
دادهٔ همان سرویس را با یک عنوان به آن بدهید و در صورت نیاز _send_images_to_admin
را برای پیوست‌های همان سرویس صدا بزنید. پیشنهاد می‌کنم در گام بعد همین الگو
را در confirm_handler هر سرویس دیگر هم پیاده کنیم.

نکته: تصاویر با همان file_id اصلی کاربر برای ادمین ارسال می‌شوند (بدون
دانلود/آپلود مجدد) — چون file_id در سطح کل بات معتبر است، نه فقط در چت
کاربر اصلی.
"""
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

MAX_CHUNK = 3500


def _chunk_text(text: str, max_chunk: int = MAX_CHUNK):
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_chunk:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks


async def send_text_dump_to_admin(bot: Bot, admin_id: int, header: str, body: str):
    """متن کامل را (با شکستن به چند پیام در صورت طولانی بودن) برای ادمین می‌فرستد."""
    full = f"{header}\n\n{body}"
    for chunk in _chunk_text(full):
        try:
            await bot.send_message(admin_id, chunk)
        except Exception as e:
            logger.error(f"[ADMIN-FORWARD] خطا در ارسال متن به ادمین: {e}", exc_info=True)


async def _send_images_to_admin(bot: Bot, admin_id: int, images: list, caption_prefix: str = ""):
    for i, img in enumerate(images, start=1):
        file_id = img.get("file_id") if isinstance(img, dict) else img
        if not file_id:
            continue
        try:
            await bot.send_photo(admin_id, file_id, caption=f"{caption_prefix} — تصویر {i}")
        except Exception as e:
            logger.error(f"[ADMIN-FORWARD] خطا در ارسال تصویر به ادمین: {e}", exc_info=True)


async def send_generic_submission_to_admin(
    bot: Bot, admin_id: int, user_id: int, service_label: str, data: dict,
    exclude_keys=None, image_keys=None,
):
    """نسخهٔ عمومی — برای هر سرویسی که فرمت‌بندی اختصاصی برایش ننوشته‌ایم.
    تمام فیلدهای دیکشنری state (به‌جز کلیدهای داخلی/موقت با پیشوند _) را
    عیناً به‌صورت متن dump می‌کند و تصاویر داخل image_keys را هم می‌فرستد.

    image_keys: نام فیلدهایی که تصویر/پیوست دارند. هر فیلد می‌تواند یکی از
    این دو شکل باشد:
      - لیست مستقیم تصاویر: [{"file_id": "..."}, ...]
      - لیست گروه‌های پیوست: [{"title": "...", "images": [...]}, ...]
    """
    exclude_keys = set(exclude_keys or [])
    image_keys = list(image_keys or [])

    lines = [f"🆔 آیدی کاربر: {user_id}", f"(برای پاسخ مستقیم: /send {user_id})", ""]
    for k, v in data.items():
        if k.startswith("_") or k in exclude_keys or k in image_keys:
            continue
        if v in (None, "", [], {}):
            continue
        lines.append(f"• {k}: {v}")

    await send_text_dump_to_admin(
        bot, admin_id,
        header=f"📥 کپی کامل درخواست: {service_label}",
        body="\n".join(lines),
    )

    for key in image_keys:
        val = data.get(key)
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, dict) and "images" in item:
                await _send_images_to_admin(
                    bot, admin_id, item.get("images", []),
                    caption_prefix=f"{service_label} | کاربر {user_id} | "
                                   f"{item.get('title', item.get('tracking_no', key))}")
            elif isinstance(item, dict) and "file_id" in item:
                await _send_images_to_admin(bot, admin_id, [item], caption_prefix=f"{service_label} | کاربر {user_id}")

    docx_file_id = data.get("check_docx_file_id") or data.get("docx_file_id")
    if docx_file_id:
        try:
            await bot.send_document(admin_id, docx_file_id, caption=f"📄 فایل ورد ارسالی کاربر {user_id}")
        except Exception as e:
            logger.error(f"[ADMIN-FORWARD] خطا در ارسال فایل ورد به ادمین: {e}", exc_info=True)


async def send_check_submission_to_admin(bot: Bot, admin_id: int, user_id: int, data: dict):
    """کپی کامل یک درخواست چک (تمام فیلدها + همهٔ تصاویر فقرات + مدارک اضافی)
    را برای ادمین می‌فرستد — دقیقاً همان لحظه‌ای که کاربر «تایید و شروع ثبت»
    را می‌زند، مستقل از موفقیت/شکست پردازش خودکار در سنا."""

    def _person_line(p, idx):
        ptype = p.get("person_type", "")
        if ptype == "شخص حقوقی":
            reps = p.get("representatives") or []
            if reps:
                rep_lines = "\n".join(
                    f"      {j}. {r.get('representative_type', '')}: {r.get('national_id', '')}"
                    for j, r in enumerate(reps, start=1))
                return (f"  {idx}. {ptype} | شناسه: {p.get('company_id','')} | نمایندگان:\n{rep_lines}")
            return (f"  {idx}. {ptype} | شناسه: {p.get('company_id','')} | "
                    f"{p.get('representative_type','')}: {p.get('national_id','')}")
        if ptype == "وکیل":
            line = f"  {idx}. وکیل | کدملی: {p.get('national_id','')}"
            if p.get("contract_number"):
                line += f" | قرارداد وکالت: {p.get('contract_number','')}"
            if p.get("stamp_amount_text"):
                line += f" | تمبر: {p.get('stamp_amount_text','')}"
            return line
        return f"  {idx}. {ptype} | کدملی: {p.get('national_id','')}"

    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    witnesses = data.get("check_witnesses", [])
    cheque_items = data.get("check_cheque_items", [])
    amount = data.get("check_amount", 0) or 0

    plaintiffs_text = "\n".join(_person_line(p, i + 1) for i, p in enumerate(plaintiffs)) or "  -"
    defendants_text = "\n".join(_person_line(p, i + 1) for i, p in enumerate(defendants)) or "  -"
    witnesses_text = "\n".join(f"  {i+1}. {w.get('national_id','')}" for i, w in enumerate(witnesses)) or "  -"

    # ⭐ درخواست‌های تامین خواسته / اعسار (عناوین مطالبه وجه)
    tamin_line = "⚖️ تامین خواسته و توقیف اموال خوانده: " + (
        "بله" if data.get("check_tamin_khasteh") else "خیر")
    aasar_line = "📋 اعسار از هزینه دادرسی: " + (
        "بله" if data.get("check_aasar") else "خیر")

    # استشهادیه (پیوست الزامی اعسار)
    estesh_count = 0
    for group in data.get("check_attachment_groups", []):
        if group.get("is_esteshahadieh") or "استشهاد" in (group.get("title", "") or ""):
            estesh_count += len(group.get("images", []))
    estesh_line = (
        f"📋 استشهادیه محلی: {estesh_count} تصویر" if estesh_count else "")

    body = (
        f"🆔 آیدی کاربر: {user_id}\n"
        f"(برای پاسخ مستقیم به همین کاربر: /send {user_id})\n\n"
        f"📌 عنوان خواسته: {data.get('check_request_title','')}\n"
        f"💰 مبلغ: {amount:,} ریال\n"
        f"{tamin_line}\n{aasar_line}\n"
        + (f"{estesh_line}\n" if estesh_line else "") +
        f"\n📄 عنوان خواسته (متن): {data.get('check_khasteh_text','')}\n\n"
        f"👤 خواهان(ها):\n{plaintiffs_text}\n\n"
        f"👥 خوانده(ها):\n{defendants_text}\n\n"
        f"🔍 مطلع/گواه:\n{witnesses_text}\n\n"
        f"📋 شرح متن:\n{data.get('check_text','')}\n\n"
        f"📝 سایر دلایل:\n{data.get('check_extra_text','') or '-'}\n\n"
        f"🏛 صلاحیت دادگاه: {data.get('check_branch_name','')} (کد: {data.get('check_branch_code','')})\n\n"
        f"🧾 تعداد فقرات چک: {len(cheque_items)}"
    )

    await send_text_dump_to_admin(
        bot, admin_id,
        header="📥 کپی کامل درخواست ثبت چک (ارسال‌شده توسط کاربر)",
        body=body,
    )

    for i, item in enumerate(cheque_items, start=1):
        await _send_images_to_admin(
            bot, admin_id, item.get("images", []),
            caption_prefix=f"🧾 فقره {i} | کدرهگیری: {item.get('tracking_no','')} | کاربر: {user_id}"
        )

    for group in data.get("check_attachment_groups", []):
        await _send_images_to_admin(
            bot, admin_id, group.get("images", []),
            caption_prefix=f"📎 مدرک «{group.get('title','')}» | کاربر: {user_id}"
        )

    docx_file_id = data.get("check_docx_file_id")
    if docx_file_id:
        try:
            await bot.send_document(admin_id, docx_file_id, caption=f"📄 فایل ورد ارسالی کاربر {user_id}")
        except Exception as e:
            logger.error(f"[ADMIN-FORWARD] خطا در ارسال فایل ورد به ادمین: {e}", exc_info=True)
