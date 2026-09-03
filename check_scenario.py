"""

سناریوی ثبت دادخواست چک در سامانه قضایی ثنا.


جریان کلی:

  ۱. تعیین مسیر بر اساس مبلغ (بیش از ۱ میلیارد ریال → دادخواست بدوی، کمتر → دعاوی صلح)

  ۲. کلیک «ثبت و اصلاح دادخواست»

  ۳. مرحله «شروع» — بررسی وکیل/نماینده

  ۴. مرحله «خواسته» — انتخاب موضوع پرونده، افزودن ردیف، کلیک روی
     دراپ‌داون «خواسته» و تایپ «چک»، ۵ ثانیه صبر و انتخاب گزینهٔ دقیق
     («درخواست صدور اجرائیه نسبت به چک بلامحل» برای اجرائیه /
     «مطالبه وجه چک» برای مطالبه وجه)، سپس متن خواسته و مبلغ

  ۵. مرحله «خواهان» — افزودن اشخاص + استعلام ثنا (دکمهٔ استعلام بدون id!)

  ۶. مرحله «خوانده» — افزودن اشخاص + استعلام ثنا

  ۷. مرحله «وکیل» / «نماينده» (در صورت وجود)

  ۸. مرحله «مطلع/ گواه»

  ۹. مرحله «شرح» — وارد کردن شرح متن

  ۱۰. مرحله «دلايل» — دلایل اضافی

  ۱۱. ثبت موقت + اعتبارسنجی کد بایگانی (bill_no)

  ۱۲. مرحله «منضمات» — برای هر فقره چک: انتخاب نوع پیوست
      (اجرائیه → «تصوير چك و گواهينامه عدم پرداخت» / مطالبه وجه →
      «تصوير چك»)، کدرهگیری + استعلام بانک مرکزی (فقط اجرائیه —
      ۱۵ ثانیه صبر و تحلیل پاپ‌آپ)، تکمیل فیلدهای سند، «ثبت و ویرایش
      پیوست» و سپس آپلود و تایید تصاویر + پیوست‌های اضافی کاربر

  ۱۳. آماده‌سازی (کد صلاحیت دادگاه + تایید اطلاعات)

  ۱۴. محاسبه هزینه — فرمول جدید کارفرما: (جمع کل هزینه + جمعِ
      «ثبت اطلاعات اشخاص» + «تنظیم دادخواست/شکواییه» + «افزودن پیوست»
      + «خدمات الکترونیک قضایی» + ۵۵۰,۰۰۰ ریال) و رند به بالا

  ۱۵. چاپ PDF — از باکس «چاپ اوليه» (صفحهٔ جدید باز می‌شود → PDF →
      ارسال برای کاربر)

  ۱۶. ارسال نتیجه + درگاه پرداخت (فاکتور کیف پول بله) — و پس از
      تایید پرداخت، مرحلهٔ امضای الکترونیک فعال می‌شود


اصلاحات این نسخه (طبق فایل لاگ/باگ ارسالی کارفرما):

  ۱. دراپ‌داون «خواسته»: قبلاً اولین `.ui-select-toggle.btn-info` صفحهٔ
     (دراپ‌داون «موضوع پرونده») کلیک می‌شد و `.ui-select-search` اولِ
     صفحه (که مخفیِ همان دراپ‌داون است) منتظر visible ماند → خطای
     «dropdown خواسته باز نشد» و انتخاب هرگز انجام نمی‌شد. حالا دکمهٔ
     دراپ‌داون «خواسته» از طریق placeholder پیدا می‌شود، جستجوی visible
     تایپ می‌شود، ۵ ثانیه صبر و گزینهٔ دقیق انتخاب می‌شود.

  ۲. استعلام اشخاص (خواهان/خوانده/مطلع/گواه/نماینده): قبلاً
     `#btnCallNationalityCode` کلیک می‌شد؛ در این بخش‌ها دکمهٔ استعلام
     اصلاً id ندارد (طبق HTML مشخصات: ng-click="actions.callNationalityCode(...)"
     و tooltip="استعلام شخص") → استعلام هرگز زده نمی‌شد → اشخاص ثبت
     نمی‌شدند → ثبت موقت با کد بایگانی خالی شکست می‌خورد. حالا استعلام
     با انتخابگر ng-click + فال‌بک tooltip زده و نتیجه بررسی می‌شود.

  ۳. کد بایگانی خالی: قبلاً با bill_no خالی به منضمات/هزینه/چاپ ادامه
     داده می‌شد («Option 'منضمات' not found» → NavigationResetError →
     ری‌استارت بی‌پایان کل تسک). حالا استخراج چند بار تلاش می‌شود و اگر
     خالی ماند، فرآیند با اطلاع به کاربر/مدیر متوقف می‌شود.

  ۴. منضمات: ورود با retry و بدون safe_click_by_text (که کل تسک را
     ری‌استارت می‌کند)؛ پشتیبانی کامل از چند فقره چک
     (check_cheque_items — TODO قبلی کد)؛ استعلام بانک مرکزی طبق
     مشخصات (۱۵ ثانیه + تحلیل پاپ‌آپ: موفق / ورود همزمان → لاگین مجدد
     مدیر و تلاش مجدد / کدرهگیری اشتباه → پیام و توقف / خطای دیگر →
     حداکثر ۳ تلاش سپس پیام قطعی سامانه و توقف)؛ تکمیل فیلدهای سند
     (Amount=1، Exporter=هیچکدام، Holder=بله، RejectReason=کسرموجودی،
     ReasonForIssuance=بابت پرداخت بدهی)؛ آپلود با لایهٔ مقاوم
     upload_helpers (editDocument → آپلود همه → تایید همه).

  ۵. هزینه: قبلاً costSum از div خالیِ [ng-model="viewModel.costSum"]
     خوانده می‌شد (عدد واقعی text-node داخل td والد است!) → costSum=0.
     حالا از td والد خوانده می‌شود و فرمول جدید (۴ ردیف + ۵۵۰,۰۰۰
     ریال + رند به بالا) اعمال می‌شود.

  ۶. چاپ: قبلاً دکمهٔ متنی «چاپ» جستجو می‌شد که در صفحه وجود ندارد.
     حالا طبق مشخصات، باکس «چاپ اوليه» کلیک می‌شود، صفحهٔ جدید باز‌شده
     با expect_page گرفته می‌شود و PDF آن برای کاربر ارسال می‌شود
     (الگو و مدیریت خطا از بخش اظهارنامه).

  ۷. پرداخت/امضا: قبلاً send_lavayeh_result/send_bulk_item_result با
     پارامتر sign_menu_path صدا زده می‌شدند که در تعریف توابع وجود
     نداشت → TypeError و شکست کل ارسال نتیجه! حالا پارامتر در کل
     زنجیره (فاکتور → پرداخت موفق → امضا) پاس می‌شود؛ درگاه پرداخت
     همیشه (حتی اگر چاپ PDF ناموفق باشد) ارسال می‌شود و پس از تایید
     پرداخت، مرحلهٔ امضا فعال می‌گردد.

"""

import asyncio
import logging
import os
import time
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, soft_click_if_exists,
    goto_url_with_retry, human_delay, force_click_by_text,
    safe_click_by_text, safe_type, wait_for_angular_idle,
    handle_session_expired, wait_for_horizontal_loading_bar,
    detect_concurrent_login_popup, NavigationResetError)
from upload_helpers import (
    prepare_files_for_upload,
    click_save_doc_with_retry,
    click_edit_document_for_title,
    click_upload_all_with_retry,
    click_apply_all_with_retry,
    close_any_popup as _uh_close_any_popup,
    get_and_close_error_popup_text as _uh_error_popup_text,
    download_images_from_bale,
    resilient_upload_attachment,
    _default_fill_other_attachment_form)


logger = logging.getLogger(__name__)

# شمارهٔ پشتیبانی — طبق مشخصات در پیام‌های خطای منضمات/کدرهگیری استفاده می‌شود
SUPPORT_PHONE = "09306186888"


class CheckAbortError(Exception):
    """قطع فرآیند ثبت چک بدون تلاش مجدد.

    برای حالت‌هایی که ادامه/تکرار ثبت فایده ندارد و باید کاربر/مدیر طبق
    مشخصات کارفرما پیام مربوطه را دریافت کنند:
      - استعلام ثنا ناموفق (کدملی در ثنا ثبت نشده و ...)
      - ثبت موقت بدون کد بایگانی
      - کدرهگیری چک اشتباه (استعلام بانک مرکزی)
      - قطعی سامانه در بخش منضمات پس از ۳ تلاش استعلام
    """

    def __init__(self, message: str, step: str = "ABORTED", user_msg: str | None = None):
        super().__init__(message)
        self.step = step
        self.user_msg = user_msg


def _text_to_editor_html(text: str) -> str:
    """متن کاربر را به HTML امن برای ادیتور تبدیل می‌کند."""
    if not text:
        return "<p><br></p>"
    # هم \n واقعی و هم \\n literal (خروجی docx_parser) پشتیبانی می‌شود
    normalized = text.replace("\r\n", "\n").replace("\\n", "\n")
    lines = normalized.split("\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")
        parts.append(f"<p>{escaped}</p>" if escaped else "<p><br></p>")
    return "".join(parts)


async def process_check_task(data: dict, bot: Bot):
    """پردازش تسک ثبت دادخواست چک"""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]

    request_title = data.get("check_request_title", "")
    amount = data.get("check_amount", 0)
    khasteh_text = data.get("check_khasteh_text", "")
    # ⭐ درخواست‌های تامین خواسته و اعسار از هزینه دادرسی (بله/خیر از کاربر)
    tamin_khasteh = bool(data.get("check_tamin_khasteh", False))
    aasar = bool(data.get("check_aasar", False))
    tracking_no = data.get("check_tracking_no", "")
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    witnesses = data.get("check_witnesses", [])
    check_text = data.get("check_text", "")
    extra_text = data.get("check_extra_text", "")
    check_images = data.get("check_images", [])
    branch_code = data.get("check_branch_code", "")
    branch_name = data.get("check_branch_name", "")
    check_text_html = data.get("check_text_html", "")
    is_bulk_check = data.get("_is_bulk_check", False)
    bulk_row_index = data.get("_bulk_row_index", 0)
    batch_tracking_code = data.get("batch_tracking_code", "")
    _doc_category_suffix = f" (دسته‌جمعی — ردیف {bulk_row_index})" if is_bulk_check else ""

    # 🧾 فقرات چک — پشتیبانی از چند فقره (هر فقره: کدرهگیری + ۳ تصویر).
    # اگر check_cheque_items موجود نبود (مثل فلوی دسته‌جمعی)، از فیلدهای
    # تک‌فقره‌ای قدیمی ساخته می‌شود.
    cheque_items = list(data.get("check_cheque_items") or [])
    if not cheque_items and (tracking_no or check_images):
        cheque_items = [{"tracking_no": tracking_no, "images": check_images}]
    # 📎 پیوست‌های اضافی کاربر (غیر از تصاویر فقرات چک)
    attachment_groups = list(data.get("check_attachment_groups") or [])

    has_lawyer = any(p.get("person_type") == "وکیل" for p in plaintiffs)
    has_legal_plaintiff = any(p.get("person_type") == "شخص حقوقی" for p in plaintiffs)
    is_high_amount = amount > 1_000_000_000  # بیش از ۱ میلیارد ریال

    # مسیر منوی سامانه برای مرحلهٔ امضا (پس از پرداخت) — دقیقاً همان مسیرِ
    # انتخاب‌شده در شروع ثبت؛ sign_menu_path در کل زنجیرهٔ پرداخت→امضا پاس می‌شود
    sign_menu_path = (
        ["ارایه و پیگیری دادخواست", "دادخواست بدوی"]
        if is_high_amount
        else ["دعاوی دادگاههای صلح", "دعاوی حقوقی"]
    )

    logging.info(
        f"[CHECK] user={user_id} title={request_title} amount={amount} "
        f"plaintiffs={len(plaintiffs)} defendants={len(defendants)} "
        f"cheques={len(cheque_items)} extra_attachments={len(attachment_groups)} "
        f"tamin_khasteh={tamin_khasteh} aasar={aasar} "
        f"is_high_amount={is_high_amount} branch={branch_code}"
    )

    try:
        from panel_sync import upsert_case_to_panel as _upsert_early
        await _upsert_early(
            bale_user_id=user_id, full_name=str(user_id),
            service_type="CHECK", status="PROCESSING",
            document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
            branch_name=branch_name, branch_code=branch_code,
            result_summary="در حال ثبت در سامانه سنا",
        )
    except Exception as panel_err:
        logging.warning(f"[CHECK] خطا در ثبت اولیه پرونده در پنل: {panel_err!r}")

    await bot.send_message(
        user_id,
        f"🏦 *در حال ثبت دادخواست چک...*\n"
        f"نوع خواسته: *{request_title}*\n"
        f"مبلغ: *{amount:,} ریال*")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [CHECK] شروع ثبت دادخواست چک برای کاربر {user_id}\n"
        f"نوع: {request_title} | مبلغ: {amount:,} | خواهان: {len(plaintiffs)} | "
        f"خوانده: {len(defendants)} | فقرات چک: {len(cheque_items)}\n"
        f"تامین خواسته: {'بله' if tamin_khasteh else 'خیر'} | "
        f"اعسار: {'بله' if aasar else 'خیر'}"
    )

    # bill_no قبل از حلقهٔ تلاش مقداردهی می‌شود تا در هندلر CheckAbortError
    # (که ممکن است قبل از ثبت موقت رخ دهد) همیشه تعریف‌شده باشد
    bill_no = ""

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
            )
            if not ok:
                return
            await human_delay(3.0, 5.0)

            # بررسی اولیهٔ نشست پیش از شروع پر کردن فرم — اگر همین حالا منقضی
            # یا درگیر ورود همزمان باشد، بهتر است همین ابتدا مدیریت شود تا کل
            # مراحل بعدی روی صفحهٔ نامعتبر اجرا نشوند.
            await check_and_handle_expiry(sana_page, bot, user_id)

            # ── ۱. انتخاب مسیر بر اساس مبلغ ──────────────────────────────
            if is_high_amount:
                # مسیر: ارایه و پیگیری دادخواست → دادخواست بدوی
                clicked = await sana_page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a.list-group-item'));
                    const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری دادخواست"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "ارایه و پیگیری دادخواست", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # کلیک «دادخواست بدوی»
                clicked = await sana_page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('li.list-group-item'));
                    const t = items.find(el => el.innerText && el.innerText.includes("دادخواست بدوی"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دادخواست بدوی", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)
            else:
                # مسیر: دعاوی دادگاههای صلح → دعاوی حقوقی
                clicked = await sana_page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a.list-group-item'));
                    const t = links.find(el => el.innerText && el.innerText.includes("دعاوی دادگاههای صلح"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دعاوی دادگاههای صلح", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # کلیک «دعاوی حقوقی»
                clicked = await sana_page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('li.list-group-item'));
                    const t = items.find(el => el.innerText && el.innerText.includes("دعاوی حقوقی"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دعاوی حقوقی", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۲. کلیک «ثبت و اصلاح دادخواست» ──────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const boxes = Array.from(document.querySelectorAll('.box'));
                const t = boxes.find(el => {
                    const h5 = el.querySelector('h5');
                    return h5 && h5.innerText && h5.innerText.includes("ثبت و اصلاح دادخواست");
                });
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ثبت و اصلاح دادخواست", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۳. مرحله «شروع» ────────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "شروع");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "شروع", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # اگر وکیل/نماینده داشت → مشابه اظهارنامه
            if has_lawyer:
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbLawyerOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)
            elif has_legal_plaintiff:
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbAgentOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)

            # ── ۴. مرحله «خواسته» ──────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "خواسته");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "خواسته", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ۴.۱ انتخاب «موضوع پرونده»
            # ⚠️ طبق مشخصات: در این فیلد نباید هیچ‌چیزی تایپ شود — صرفاً
            # گزینهٔ اول لیست (بدون تایپ) انتخاب می‌شود.
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('.ui-select-toggle');
                if (btn) btn.click();
            }''')
            await asyncio.sleep(2)

            try:
                await sana_page.wait_for_selector(
                    '.ui-select-choices-row, [ng-bind-html*="typeaheadHighlight"]',
                    timeout=5000
                )
                await sana_page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('.ui-select-choices-row, [ng-bind-html*="typeaheadHighlight"]'));
                    const visible = items.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visible.length > 0) {
                        const row = visible[0].closest('a, .ui-select-choices-row, li') || visible[0];
                        row.click();
                        return true;
                    }
                    return false;
                }''')
                await asyncio.sleep(3)
            except PlaywrightTimeoutError:
                logging.warning("[CHECK] dropdown موضوع پرونده باز نشد")

            # ۴.۲ کلیک «افزودن»
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('#btnAddSection');
                if (btn && !btn.disabled) btn.click();
            }''')
            await resilient_sleep(sana_page, 3, bot, user_id)

            # ۴.۳ ⭐ انتخاب نوع خواسته از dropdown — کلیک روی دراپ‌داون
            # «خواسته»، تایپ «چک»، ۵ ثانیه صبر و انتخاب گزینهٔ دقیق طبق
            # نوع خواستهٔ کاربر (اصلاحیهٔ اصلی — قبلاً دراپ‌داون اشتباه
            # باز می‌شد و خواسته هرگز انتخاب نمی‌شد).
            khasteh_ok = await _select_khasteh_option(sana_page, request_title, bot, user_id)
            if not khasteh_ok:
                # هنوز ثبت موقتی انجام نشده → تلاش مجدد کل فلوی ثبت امن است
                raise RuntimeError(
                    "انتخاب «خواسته» از دراپ‌داون انجام نشد "
                    f"(user={user_id}, title={request_title})"
                )

            # ۴.۴ وارد کردن متن خواسته
            await sana_page.evaluate('''(text) => {
                const inp = document.querySelector('input[id^="txtDescription"]');
                if (inp) {
                    inp.value = text;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', khasteh_text)
            await asyncio.sleep(1)

            # ۴.۵ انتخاب «مبلغ معین»
            await sana_page.evaluate('''() => {
                const sel = document.querySelector('select[ng-model*="PriceType"]');
                if (sel) {
                    sel.value = "1";
                    sel.dispatchEvent(new Event("input", { bubbles: true }));
                    sel.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(1)

            # ۴.۶ وارد کردن مبلغ
            amount_str = str(amount)
            await sana_page.evaluate('''(val) => {
                const inp = document.querySelector('input[id^="txtPrice"]');
                if (inp) {
                    inp.focus();
                    inp.value = "";
                    inp.value = val;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', amount_str)
            await asyncio.sleep(1)

            # ۴.۷ تیک‌های خسارت (فقط مطالبه وجه)
            if request_title == "مطالبه وجه چک":
                await sana_page.evaluate('''() => {
                    const rdbJudge = document.querySelector('#rdbJudgePrice');
                    if (rdbJudge && !rdbJudge.checked && !rdbJudge.disabled) rdbJudge.click();
                    const rdbDelay = document.querySelector('#rdbDelayPrice');
                    if (rdbDelay && !rdbDelay.checked && !rdbDelay.disabled) rdbDelay.click();
                }''')
                await asyncio.sleep(1)
            # ۴.۸ ⭐ خواستهٔ فرعی «تامین خواسته» — طبق دستور کارفرما:
            # بعد از خواستهٔ اصلی، دکمهٔ «افزودن» → فیلد «خواسته» → تایپ «تامین»
            # → انتخاب گزینهٔ اول → ادامهٔ مراحل
            if tamin_khasteh:
                tamin_ok = await _add_secondary_khasteh(
                    sana_page, bot, user_id,
                    search_term="تامین", pick_first=True, label="تامین خواسته")
                if not tamin_ok:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⚠️ [CHECK] خواستهٔ فرعی «تامین خواسته» برای کاربر {user_id} "
                        "ثبت نشد — لطفاً در سامانه به‌صورت دستی بررسی/افزودن کنید.")

            # ۴.۹ ⭐ خواستهٔ فرعی «اعسار از پرداخت هزینه دادرسی» — طبق دستور
            # کارفرما: «افزودن» → فیلد «خواسته» → تایپ «اعسار» → گزینهٔ
            # «اعسار از پرداخت هزینه دادرسی»
            if aasar:
                aasar_ok = await _add_secondary_khasteh(
                    sana_page, bot, user_id,
                    search_term="اعسار",
                    target_texts=["اعسار از پرداخت هزینه دادرسی"],
                    fallback_texts=["اعسار"],
                    label="اعسار از هزینه دادرسی")
                if not aasar_ok:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⚠️ [CHECK] خواستهٔ فرعی «اعسار از هزینه دادرسی» برای کاربر {user_id} "
                        "ثبت نشد — لطفاً در سامانه به‌صورت دستی بررسی/افزودن کنید.")

            # ── ۵. مرحله «خواهان» ──────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "خواهان");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "خواهان", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ⚠️ طبق مشخصات: کدملی وارد شود و سپس «گزینه استعلام» زده شود —
            # دکمهٔ استعلام در این بخش id ندارد و از طریق ng-click کلیک می‌شود.
            # اگر خواهان دیگری وجود داشت، همان مراحل با انتخاب «افزودن».
            for idx, person in enumerate(plaintiffs):
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype == "وکیل":
                    continue  # وکیل در step جداگانه

                # کلیک افزودن
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                if ptype == "شخص حقوقی":
                    await _fill_legal_person(sana_page, person, bot, user_id, role="خواهان", idx=idx)
                else:
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id,
                                            role="خواهان", idx=idx)

                await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۶. مرحله «خوانده» ──────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "خوانده");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "خوانده", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for idx, person in enumerate(defendants):
                ptype = person.get("person_type", "شخص حقیقی")

                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                if ptype == "شخص حقوقی":
                    await _fill_legal_person(sana_page, person, bot, user_id, role="خوانده", idx=idx)
                else:
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id,
                                            role="خوانده", idx=idx)

                await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۷. مرحله «وکیل» ─────────────────────────────────────────
            if has_lawyer:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "وكيل");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "وكيل", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for idx, person in enumerate(plaintiffs):
                    if person.get("person_type") != "وکیل":
                        continue
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnAddSection');
                        if (btn && !btn.disabled) btn.click();
                    }''')
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_lawyer_person(sana_page, person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۷.۵ مرحله «نماينده» (اگر حقوقی داشتیم) ──────────────────
            if has_legal_plaintiff:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "نماينده");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "نماينده", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                legal_pl = next((p for p in plaintiffs if p.get("person_type") == "شخص حقوقی"), {})
                rep_type = legal_pl.get("representative_type", "")
                nat_id = legal_pl.get("national_id", "")

                agent_value = "0091000010000008" if rep_type == "مدیرعامل" else "0091000010000010"

                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)
                await wait_for_angular_idle(sana_page)
                await asyncio.sleep(2)

                await sana_page.evaluate('''(val) => {
                    const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
                    if (sel && !sel.disabled) {
                        sel.value = val;
                        sel.dispatchEvent(new Event("input", { bubbles: true }));
                        sel.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', agent_value)
                await asyncio.sleep(2)

                if nat_id:
                    for _try in range(5):
                        set_ok = await sana_page.evaluate('''(val) => {
                            const inp = document.querySelector('#txtRealIrNationalityCode');
                            if (inp && !inp.disabled) {
                                inp.value = val;
                                inp.dispatchEvent(new Event("input", { bubbles: true }));
                                inp.dispatchEvent(new Event("change", { bubbles: true }));
                                return true;
                            }
                            return false;
                        }''', nat_id)
                        if set_ok:
                            break
                        await asyncio.sleep(3)

                    # ⭐ کلیک استعلام — دکمهٔ استعلام id ندارد؛ از طریق ng-click
                    await _click_sana_inquiry_button(sana_page, bot, user_id, role="نماینده")
                    await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۸. مرحله «مطلع/ گواه» ───────────────────────────────────
            # طبق مشخصات: بخش خوانده و مطلع و گواه نیز به همین صورت (کدملی +
            # استعلام) است.
            if witnesses:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.includes("مطلع"));
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "مطلع", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for idx, witness in enumerate(witnesses):
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('#btnAddSection');
                        if (btn && !btn.disabled) btn.click();
                    }''')
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, witness["national_id"], bot, user_id,
                                            role="مطلع/گواه", idx=idx)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۹. مرحله «شرح» ──────────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const steps = Array.from(document.querySelectorAll('.step'));
                const t = steps.find(el => el.innerText && el.innerText.trim() === "شرح");
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "شرح", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            full_text = check_text
            if extra_text:
                full_text += "\n" + extra_text

            text_html = check_text_html if check_text_html else _text_to_editor_html(full_text)

            await sana_page.evaluate('''(html) => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    editor.focus();
                    editor.innerHTML = html;
                    editor.dispatchEvent(new Event("input", { bubbles: true }));
                    editor.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', text_html)
            await resilient_sleep(sana_page, 2, bot, user_id)

            # ── ۱۰. مرحله «دلايل» ────────────────────────────────────────
            if extra_text:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "دلايل");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "دلايل", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                # تیک چک‌باکس و وارد کردن متن دلایل
                await sana_page.evaluate('''() => {
                    const chk = document.querySelector('input[type="checkbox"][id^="chk"]');
                    if (chk && !chk.checked && !chk.disabled) chk.click();
                }''')
                await asyncio.sleep(1)

                await sana_page.evaluate('''(text) => {
                    const ta = document.querySelector('textarea[id^="ReasonAttach"]');
                    if (ta) {
                        ta.value = text;
                        ta.dispatchEvent(new Event("input", { bubbles: true }));
                        ta.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', extra_text)
                await asyncio.sleep(1)

            # ── ۱۱. ثبت موقت ──────────────────────────────────────────────
            clicked = await sana_page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const t = btns.find(el => el.innerText && el.innerText.includes("ثبت موقت"));
                if (t && !t.disabled) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ثبت موقت", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            # بررسی ورود همزمان/انقضای نشست دقیقاً همین‌جا حیاتی است: اگر نشست
            # درست همین لحظه منقضی شده باشد، bill_no زیر خالی/نامعتبر استخراج
            # می‌شود و کل پرونده با کد بایگانی اشتباه ادامه پیدا می‌کند.
            had_expiry_save = await check_and_handle_expiry(sana_page, bot, user_id)
            if had_expiry_save:
                await resilient_sleep(sana_page, 8, bot, user_id)

            # استخراج شماره بایگانی — با چند تلاش (ممکن است دیر رندر شود)
            bill_no = ""
            for _bill_try in range(5):
                bill_no = await sana_page.evaluate('''() => {
                    const inp = document.querySelector('#txtBillNo');
                    if (inp) return inp.value;
                    const sp = document.querySelector('[ng-model*="BillNo"]');
                    if (sp) return sp.innerText || sp.textContent;
                    return "";
                }''') or ""
                bill_no = bill_no.strip()
                if bill_no:
                    break
                await asyncio.sleep(3)
            logging.info(f"[CHECK] bill_no={bill_no}")

            # ⭐ اعتبارسنجی bill_no — قبلاً با کد خالی به منضمات/هزینه/چاپ
            # ادامه داده می‌شد و همهٔ مراحل بعدی روی صفحهٔ نامعتبر fail می‌شد
            # («Option 'منضمات' not found» → ری‌استارت بی‌پایان).
            if not bill_no:
                err_msg = ("ثبت موقت انجام شد ولی کد بایگانی دادخواست چک از "
                           "سامانه قابل استخراج نبود.")
                user_msg = (
                    "⚠️ *خطا در ثبت موقت دادخواست چک:*\n\n"
                    "«" + err_msg + "»\n\n"
                    "فرآیند متوقف شد. لطفاً به مدیریت اطلاع دهید."
                )
                raise CheckAbortError(err_msg, step="TEMP_SAVE_NO_BILL", user_msg=user_msg)

            # ذخیره کدرهگیری در گوگل شیت + اطلاع به مدیر
            await log_event("ثبت موقت", "دادخواست چک", str(user_id), user_id,
                            tracking_code=bill_no, note=f"چک {request_title} | مبلغ: {amount:,}")
            await bot.send_message(
                ADMIN_ID,
                f"📋 *ثبت موقت دادخواست چک موفق*\n"
                f"👤 کاربر: {user_id}\n"
                f"🔢 کد بایگانی: `{bill_no}`\n"
                f"📝 نوع: {request_title}")

            # بازگشت به فهرست
            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۲. مرحله «منضمات» — آپلود تصاویر چک (برای هر فقره) ────
            if cheque_items or attachment_groups:
                attachments_ok = await _process_check_attachments(
                    sana_page,
                    request_title=request_title,
                    cheque_items=cheque_items,
                    attachment_groups=attachment_groups,
                    bot=bot,
                    user_id=user_id,
                    bill_no=bill_no)

                if not attachments_ok:
                    # پیام‌های مربوطه (کدرهگیری اشتباه / قطعی سامانه) داخل
                    # _process_check_attachments ارسال شده‌اند — فقط توقف:
                    raise CheckAbortError(
                        "مرحلهٔ منضمات چک کامل نشد — پیام مربوطه برای کاربر ارسال شد",
                        step="ATTACHMENTS_ABORTED")

                # بازگشت به فهرست
                await _click_goto_main(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۳. آماده‌سازی جهت دریافت وجه ────────────────────────────
            # ⭐ کلیک باکس از طریق _click_step_box (بدون safe_click_by_text —
            # که NavigationResetError می‌دهد و کل تسکِ ثبت‌شده را ری‌استارت می‌کند)
            prep_box_ok = await _click_step_box(sana_page, "آماده سازي جهت دريافت وجه", bot, user_id)
            if not prep_box_ok:
                logging.warning("[CHECK] باکس «آماده سازي جهت دريافت وجه» پیدا نشد — تلاش با متن کوتاه")
                prep_box_ok = await _click_step_box(sana_page, "آماده سازي", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # وارد کردن کد صلاحیت دادگاه
            if branch_code:
                await sana_page.evaluate('''(code) => {
                    const inp = document.querySelector('#txtSendUnitCode');
                    if (inp) {
                        inp.value = code;
                        inp.dispatchEvent(new Event("input", { bubbles: true }));
                        inp.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', branch_code)
                await asyncio.sleep(2)

            # کلیک «تایید اطلاعات»
            # ⚠️ بدون چک کردن متن پاپ‌آپ، دکمهٔ confirm زده نمی‌شود. اگر
            # همان لحظه پاپ‌آپ «ورود همزمان» یا خطای دیگری (نه تاییدیهٔ
            # عادی) نمایش داده می‌شد، دکمهٔ خطا هم به‌عنوان تایید بسته
            # می‌شد — طبق مشخصات: «اگر خطای دیگری داد دوباره تایید اطلاعات
            # را انتخاب کن» و «اگر ورود همزمان بود، مدیر باید لاگین مجدد
            # را انجام دهد».
            confirm_ok = False
            for confirm_attempt in range(4):
                clicked = await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnCalculateCash') ||
                                  Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes("تایید اطلاعات"));
                    if (btn && !btn.disabled) { btn.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    break  # دکمه اصلاً پیدا نشد — یعنی احتمالاً از قبل تایید شده

                await wait_for_horizontal_loading_bar(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                had_expiry = await check_and_handle_expiry(sana_page, bot, user_id)
                if had_expiry:
                    await asyncio.sleep(3)
                    continue

                popup_text = await sana_page.evaluate('''() => {
                    const popup = document.querySelector('.sweet-alert.showSweetAlert');
                    if (!popup) return null;
                    const h2 = popup.querySelector('h2');
                    const p = popup.querySelector('p');
                    return ((h2 ? h2.innerText : '') + ' ' + (p ? p.innerText : '')).trim();
                }''')

                if not popup_text:
                    # پاپ‌آپی نمایش داده نشد — یعنی مرحله بدون تاییدیهٔ جداگانه رد شده
                    confirm_ok = True
                    break

                if "تایید" in popup_text or "تاييد" in popup_text:
                    # پاپ‌آپ تاییدیهٔ «آیا اطلاعات مورد تایید است؟» → دکمهٔ تایید را بزن
                    await sana_page.evaluate('''() => {
                        const btns = Array.from(document.querySelectorAll('.sweet-alert button.confirm'));
                        const t = btns.find(b => b.innerText.includes("تایید"));
                        if (t) t.click();
                    }''')
                    await wait_for_horizontal_loading_bar(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 5, bot, user_id)

                    had_expiry2 = await check_and_handle_expiry(sana_page, bot, user_id)
                    if had_expiry2:
                        await asyncio.sleep(3)
                        continue

                    # بستن پاپ‌آپ موفقیت نهایی
                    await sana_page.evaluate('''() => {
                        const btn = document.querySelector('.sweet-alert .confirm');
                        if (btn) btn.click();
                    }''')
                    await asyncio.sleep(2)
                    confirm_ok = True
                    break

                # هر پاپ‌آپ دیگری (خطای سامانه غیر از ورود همزمان) → طبق
                # مشخصات، دوباره «تایید اطلاعات» را انتخاب کن
                logging.warning(
                    f"[CHECK] پاپ‌آپ غیرمنتظره در آماده‌سازی (تلاش {confirm_attempt+1}/4): {popup_text!r}"
                )
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('.sweet-alert .confirm, .sweet-alert .cancel');
                    if (btn) btn.click();
                }''')
                await asyncio.sleep(2)

            if not confirm_ok:
                logging.error(f"[CHECK] تایید اطلاعات آماده‌سازی پس از ۴ تلاش ناموفق ماند (user={user_id})")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CHECK] «تایید اطلاعات» (آماده‌سازی) برای کاربر {user_id} پس از ۴ تلاش ناموفق ماند. "
                    f"لطفاً این پرونده را دستی بررسی کنید. کد بایگانی: `{bill_no}`"
                )

            # بازگشت به فهرست
            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۴. محاسبه و دریافت هزینه ────────────────────────────────
            cost_box_ok = await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            if not cost_box_ok:
                logging.warning("[CHECK] باکس «محاسبه و دريافت هزينه» پیدا نشد — تلاش با متن کوتاه")
                await _click_step_box(sana_page, "محاسبه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            # استخراج هزینه‌ها — ⭐ فرمول جدید کارفرما (costSum از td والد +
            # ۴ ردیف خاص + ۵۵۰,۰۰۰ ریال + رند به بالا)
            cost_data = await _extract_cost_data(sana_page)
            final_total = cost_data.get("final_total", 0)
            _matched = cost_data.get("matched_rows_debug", [])
            logging.info(
                f"[CHECK] هزینه: costSum={cost_data.get('costSum')} "
                f"rowSum={cost_data.get('rowSum')} "
                f"fixedExtra={cost_data.get('fixedExtra')} final={final_total} "
                f"ردیف‌های منطبق‌شده ({len(_matched)}): {_matched}"
            )
            if len(_matched) != 4:
                # اگر ۴ ردیف هزینهٔ خاص پیدا نشد، یا ساختار جدول عوض شده یا
                # یکی از عناوین فرق کرده — باید فوراً به مدیر اطلاع داد.
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [CHECK] هشدار محاسبهٔ هزینه: انتظار ۴ ردیف هزینهٔ خاص می‌رفت، "
                    f"{len(_matched)} ردیف پیدا شد ({_matched}). "
                    f"لطفاً مبلغ نهایی ({final_total:,} ریال) را دستی با سامانه تطبیق دهید. کاربر: {user_id}"
                )

            # ── ۱۵. چاپ PDF ─────────────────────────────────────────────
            # ⭐ طبق مشخصات: چاپ از باکس «چاپ اوليه» انجام می‌شود، صفحهٔ جدید
            # باز می‌شود و PDF آن برای کاربر ارسال می‌گردد (الگوی اظهارنامه).
            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            pdf_path = await _print_check(sana_page, browser_context, bill_no, bot, user_id)

            # ── ۱۶. ارسال نتیجه + درگاه پرداخت + فعال‌سازی امضا ──────────
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
                        service_type="CHECK",
                        sign_menu_path=sign_menu_path)
                else:
                    # ⭐ مسیر منوی اخذ امضا برای پیگیریِ بعدی با کد رهگیری —
                    # دقیقاً همان مسیر منویی که در ابتدای این سناریو کلیک
                    # شده بود؛ پارامتر sign_menu_path حالا در کل زنجیرهٔ
                    # فاکتور → پرداخت → امضا پاس می‌شود (قبلاً TypeError
                    # می‌داد چون این پارامتر وجود نداشت).
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
                        service_type="CHECK",
                        sign_menu_path=sign_menu_path)
                await bot.send_message(
                    ADMIN_ID,
                    f"✅ [CHECK] ثبت دادخواست چک کاربر {user_id} موفق."
                    f" هزینه: {final_total:,} ریال"
                    + (f" (دسته‌جمعی — ردیف {bulk_row_index} — بچ {batch_tracking_code})" if is_bulk_check else "")
                )
            else:
                # چاپ PDF ناموفق — طبق مشخصات، درگاه پرداخت نسبت به مبلغ
                # به‌هرحال باید برای کاربر ارسال شود و پس از تایید پرداخت،
                # مرحلهٔ امضا فعال گردد.
                await bot.send_message(
                    user_id,
                    f"⚠️ دادخواست چک با کد بایگانی `{bill_no}` ثبت شد "
                    f"اما در چاپ PDF خطا رخ داد.\n"
                    f"برای دریافت نسخهٔ چاپی با مدیریت تماس بگیرید.")
                try:
                    from panel_sync import upsert_case_to_panel
                    await upsert_case_to_panel(
                        bale_user_id=user_id, full_name=str(user_id),
                        service_type="CHECK", status="PROCESSING",
                        tracking_code=bill_no or None,
                        document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                        error_details="ثبت در سامانه انجام شد اما چاپ PDF ناموفق بود — فاکتور پرداخت ارسال شد",
                        error_step="print_pdf",
                        result_summary="ثبت موفق؛ چاپ ناموفق؛ در انتظار پرداخت",
                    )
                except Exception as panel_err:
                    logging.warning(f"[CHECK] خطا در آپدیت پرونده در پنل: {panel_err!r}")

                # حتی وقتی چاپ PDF شکست خورد، ردیف دسته‌جمعی باید «تمام‌شده»
                # علامت بخورد وگرنه finalize_bulk_batch هرگز صدا زده نمی‌شود.
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
                else:
                    # ⭐ ارسال فاکتور پرداخت (درگاه) بدون PDF — پس از تایید
                    # پرداخت، مرحلهٔ امضا فعال می‌شود.
                    try:
                        await send_lavayeh_result(
                            bot, user_id, "", final_total,
                            tracking_code=bill_no,
                            national_ids=nat_ids,
                            lavayeh_title=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                            lavayeh_province="",
                            lavayeh_row_number=1,
                            lavayeh_persons=plaintiffs,
                            skip_fee_calc=True,
                            is_ezhharnameh=False,
                            service_type="CHECK",
                            sign_menu_path=sign_menu_path)
                    except Exception as inv_err:
                        logging.error(f"[CHECK] خطا در ارسال فاکتور پس از شکست چاپ: {inv_err}", exc_info=True)
                        await bot.send_message(
                            user_id,
                            f"💳 مبلغ قابل پرداخت: *{final_total:,} ریال*\n"
                            "برای پرداخت و دریافت لینک فاکتور به مدیریت پیام دهید.")

            return

        except CheckAbortError as abort_err:
            # ⭐ قطع بدون تلاش مجدد — پیام کاربر (در صورت وجود) + اطلاع مدیر +
            # ثبت شکست در پنل + علامت‌گذاری ردیف دسته‌جمعی
            logging.error(f"[CHECK] قطع فرآیند user={user_id} ({abort_err.step}): {abort_err}")
            if abort_err.user_msg:
                try:
                    await bot.send_message(user_id, abort_err.user_msg)
                except Exception:
                    pass
            await bot.send_message(
                ADMIN_ID,
                f"⛔ [CHECK] فرآیند کاربر {user_id} قطع شد ({abort_err.step}): {str(abort_err)[:400]}")
            try:
                from panel_sync import upsert_case_to_panel
                await upsert_case_to_panel(
                    bale_user_id=user_id, full_name=str(user_id),
                    service_type="CHECK", status="FAILED",
                    tracking_code=bill_no if bill_no else (tracking_no or None),
                    document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                    error_details=str(abort_err)[:300],
                    error_step=abort_err.step,
                )
            except Exception as panel_err:
                logging.warning(f"[CHECK] خطا در ثبت شکست پرونده در پنل: {panel_err!r}")

            # ردیف دسته‌جمعی باید «تمام‌شده» علامت بخورد وگرنه finalize_bulk_batch
            # برای کل بچ هرگز اجرا نمی‌شود.
            if is_bulk_check and batch_tracking_code:
                try:
                    from bulk_submissions import BULK_TASKS, mark_bulk_item_done
                    if batch_tracking_code in BULK_TASKS:
                        BULK_TASKS[batch_tracking_code].setdefault("failures", []).append({
                            "row_index": bulk_row_index,
                            "tracking_code": tracking_no,
                            "title": f"دادخواست چک — {request_title}",
                            "error": f"{abort_err.step}: {str(abort_err)[:150]}",
                        })
                    await mark_bulk_item_done(bot, user_id, batch_tracking_code)
                except Exception as log_err:
                    logging.error(f"[CHECK] خطا در mark_bulk_item_done (قطع فرآیند): {log_err}")
            return

        except Exception as e:
            logging.error(f"[CHECK] تلاش {attempt+1} ناموفق user={user_id}: {e}")
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [CHECK] تلاش {attempt+1} ناموفق. ریلود...\nخطا: {str(e)[:300]}"
                )
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
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
                    logging.warning(f"[CHECK] خطا در ثبت شکست پرونده در پنل: {panel_err!r}")

                # این ردیف دسته‌جمعی هم باید «تمام‌شده» علامت بخورد وگرنه
                # finalize_bulk_batch برای کل بچ هرگز اجرا نمی‌شود.
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
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="process_check_task", error=e,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════════════════════════════════

async def _click_goto_main(page, bot: Bot, user_id: int, max_retries: int = 4) -> bool:
    """کلیک «بازگشت به فهرست» — با هر دو id رایج (#gotoMainPage و
    #btnGotoMainPage)، فال‌بک AngularJS scope و جستجوی متنی (الگوی لایحه)."""
    for attempt in range(max_retries):
        try:
            await _uh_close_any_popup(page)
        except Exception:
            pass
        await asyncio.sleep(0.5)

        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#gotoMainPage') ||
                        document.querySelector('#btnGotoMainPage') ||
                        document.querySelector('[ng-click*="gotoMainStep"]');
            if (btn) {
                try {
                    if (typeof angular !== 'undefined') {
                        const scope = angular.element(btn).scope();
                        if (scope && scope.actions && scope.actions.gotoMainStep) {
                            scope.actions.gotoMainStep();
                            scope.$apply();
                            return true;
                        }
                    }
                } catch (e) {}
                if (!btn.disabled) { btn.click(); return true; }
            }
            const buttons = Array.from(document.querySelectorAll('button'));
            const target = buttons.find(b => b.innerText && b.innerText.includes("بازگشت به فهرست"));
            if (target && !target.disabled) { target.click(); return true; }
            return false;
        }''')
        if clicked:
            await asyncio.sleep(2.5)
            return True
        await asyncio.sleep(2)
    logging.warning("[CHECK] دکمهٔ «بازگشت به فهرست» پیدا/کلیک نشد")
    return False


async def _click_step_box(page, step_name: str, bot: Bot, user_id: int,
                          max_retries: int = 3) -> bool:
    """کلیک روی باکس (.box) مراحل با h5 مشخص — با retry.

    ⚠️ عمداً از safe_click_by_text استفاده نمی‌شود: آن تابع در صورت
    پیدا نشدن متن، NavigationResetError می‌دهد و کل تسک را ری‌استارت
    می‌کند — در حالی که بعد از «ثبت موقت» دادخواست از قبل ثبت شده و
    ری‌استارت یعنی ثبتِ تکراری پرونده!
    """
    for attempt in range(max_retries):
        clicked = await page.evaluate('''(name) => {
            const heads = Array.from(document.querySelectorAll('.box h5'));
            const t = heads.find(el => el.innerText && el.innerText.trim().includes(name));
            if (t) {
                const box = t.closest('.box');
                if (box) { box.click(); return true; }
            }
            return false;
        }''', step_name)
        if clicked:
            await asyncio.sleep(1.5)
            # چک انقضا بعد از کلیک باکس — اگر نشست تمدید شد، باکس دوباره کلیک شود
            try:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
            except NavigationResetError:
                # صفحه پرت شده — برگرد به فهرست و تلاش مجدد (نه ری‌استارت کل تسک)
                try:
                    await page.goto("https://sakha2.adliran.ir/Offices/Index")
                    await asyncio.sleep(4)
                except Exception:
                    pass
                continue
            if had_expiry:
                await asyncio.sleep(2)
                await page.evaluate('''(name) => {
                    const heads = Array.from(document.querySelectorAll('.box h5'));
                    const t = heads.find(el => el.innerText && el.innerText.trim().includes(name));
                    if (t) {
                        const box = t.closest('.box');
                        if (box) box.click();
                    }
                }''', step_name)
                await asyncio.sleep(1.5)
            return True
        # باکس هنوز رندر نشده — صبر و تلاش مجدد
        await asyncio.sleep(3)
    return False


async def _select_khasteh_option(page, request_title: str, bot: Bot, user_id: int,
                                   search_term: str = None,
                                   target_texts: list = None,
                                   fallback_texts: list = None,
                                   pick_first: bool = False,
                                   last_row: bool = False) -> bool:
    """باز کردن دراپ‌داون «خواسته»، تایپ عبارت جستجو، ۵ ثانیه صبر و انتخاب گزینهٔ درست.

    طبق مشخصات کارفرما:
      - کلیک روی دراپ‌داون خواسته (div.ui-select-match با placeholder="خواسته")
        و تایپ عبارت جستجو
      - ۵ ثانیه صبر
      - اجرائیه چک → تایپ «چک» → کلیک «درخواست صدور اجرائیه نسبت به چک بلامحل»
      - مطالبه وجه چک → تایپ «چک» → کلیک «مطالبه وجه چک»
      - مطالبه وجه بابت... → تایپ «وجه» → کلیک «مطالبه وجه بابت ...»
      - خواستهٔ فرعی تامین → تایپ «تامین» → کلیک گزینهٔ اول
      - خواستهٔ فرعی اعسار → تایپ «اعسار» → کلیک «اعسار از پرداخت هزینه دادرسی»

    پارامترها:
      search_term    عبارت تایپ‌شده در جستجو (پیش‌فرض از request_title)
      target_texts   متن‌های هدف دقیق (به‌ترتیب اولویت)
      fallback_texts متن‌های جایگزین
      pick_first     True → اولین گزینهٔ لیست انتخاب شود (فرمان تامین)
      last_row       True → ردیف «خواسته» *آخر* (خواستهٔ فرعیِ تازه‌افزوده) باز شود

    ⚠️ باگ قبلی: querySelector('.ui-select-toggle.btn-info') اولین toggle
    صفحه (دراپ‌داون «موضوع پرونده») را برمی‌گرداند نه دراپ‌داون «خواسته»؛
    و locator('.ui-select-search').first ممکن است input همیشه-مخفیِ همان
    دراپ‌داون باشد → wait_for(visible) تایم‌اوت («dropdown خواسته باز نشد»)
    و خواسته هرگز انتخاب نمی‌شد.
    """
    is_ejra = (request_title == "صدور اجرائیه چک")
    is_badane = (request_title == "مطالبه وجه بابت...")

    if search_term is None:
        # ⭐ طبق دستور کارفرما: برای «مطالبه وجه بابت...» عبارت «وجه» تایپ می‌شود
        search_term = "وجه" if is_badane else "چک"
    if target_texts is None:
        if is_badane:
            target_texts = ["مطالبه وجه بابت"]
        elif is_ejra:
            target_texts = ["درخواست صدور اجرائیه نسبت به چک بلامحل"]
        else:
            target_texts = ["مطالبه وجه چک"]
    if fallback_texts is None:
        if is_badane:
            fallback_texts = ["وجه بابت"]
        elif is_ejra:
            fallback_texts = ["صدور اجرائیه"]
        else:
            fallback_texts = ["مطالبه وجه"]

    for attempt in range(3):
        await wait_for_angular_idle(page)

        # ۱) کلیک روی toggle دراپ‌داون «خواسته» — بر اساس placeholder
        #    (last_row=True → آخرین ردیف خواسته، برای خواسته‌های فرعی)
        clicked = await page.evaluate('''(lastRow) => {
            let btn = null;
            const matches = Array.from(
                document.querySelectorAll('.ui-select-match[placeholder="خواسته"]')
            ).filter(m => m.offsetParent !== null);
            const match = matches.length > 0
                ? (lastRow ? matches[matches.length - 1] : matches[0])
                : null;
            if (match) btn = match.querySelector('button.ui-select-toggle');
            if (!btn) {
                const spans = Array.from(document.querySelectorAll('.ui-select-placeholder'))
                    .filter(s => (s.innerText || '').trim() === 'خواسته');
                const sp = spans.length > 0
                    ? (lastRow ? spans[spans.length - 1] : spans[0])
                    : null;
                if (sp) btn = sp.closest('button');
            }
            if (!btn) {
                // فال‌بک: آخرین toggle فعال صفحه (جدیدترین ردیفِ «افزودن»)
                const toggles = Array.from(document.querySelectorAll('button.ui-select-toggle'))
                    .filter(b => !b.disabled);
                if (toggles.length > 0) btn = toggles[toggles.length - 1];
            }
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''', last_row)
        if not clicked:
            logging.warning(f"[CHECK] toggle دراپ‌داون «خواسته» کلیک نشد (تلاش {attempt+1}/3)")
            await asyncio.sleep(2)
            continue

        await asyncio.sleep(1.5)

        # ۲) تایپ عبارت جستجو در فیلد دراپ‌داونِ باز (فقط input قابل‌مشاهده)
        try:
            search = page.locator('.ui-select-search:visible').first
            await search.wait_for(state="visible", timeout=6000)
            await search.fill("")
            await search.type(search_term, delay=120)
        except PlaywrightTimeoutError:
            logging.warning(f"[CHECK] فیلد جستجوی «خواسته» ظاهر نشد (تلاش {attempt+1}/3)")
            await asyncio.sleep(2)
            continue
        except Exception as e:
            logging.warning(f"[CHECK] خطا در تایپ «{search_term}» در جستجوی خواسته: {e}")
            await asyncio.sleep(2)
            continue

        # ۳) ۵ ثانیه صبر — طبق مشخصات
        await asyncio.sleep(5)

        # ۴) انتخاب گزینهٔ دقیق از لیست گزینه‌های قابل‌مشاهده
        picked = await page.evaluate('''(targets, fallbacks, pickFirst, searchTerm) => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            const items = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
            let target = null;
            if (pickFirst) {
                // گزینهٔ اول — ترجیحاً منطبق با عبارت جستجو
                target = items.find(el => norm(el.innerText).includes(searchTerm)) || items[0] || null;
            } else {
                target = items.find(el => targets.some(t => norm(el.innerText).includes(t)));
                if (!target) {
                    target = items.find(el => fallbacks.some(t => norm(el.innerText).includes(t)));
                }
            }
            if (target) {
                const row = target.closest('a, .ui-select-choices-row, li') || target;
                row.click();
                return norm(target.innerText);
            }
            return null;
        }''', target_texts, fallback_texts, pick_first, search_term)

        if picked:
            logging.info(f"[CHECK] گزینهٔ خواسته انتخاب شد: {picked}")
            await asyncio.sleep(3)
            return True

        logging.warning(f"[CHECK] گزینهٔ خواسته در لیست پیدا نشد (تلاش {attempt+1}/3)")
        await asyncio.sleep(2)

    return False


async def _add_secondary_khasteh(page, bot: Bot, user_id: int, search_term: str,
                                 pick_first: bool = False, target_texts: list = None,
                                 fallback_texts: list = None, label: str = "") -> bool:
    """افزودن خواستهٔ فرعی (تامین خواسته / اعسار از هزینه دادرسی).

    طبق دستور کارفرما (عیناً):
      «بعد از اینکه خواسته اصلی را وارد کردی، گزینهٔ [btnAddSection افزودن]
       را انتخاب کن، سپس فیلد [خواسته] را انتخاب کن و تایپ کن ...»
      - تامین: تایپ «تامین» و گزینهٔ اول
      - اعسار: تایپ «اعسار» و گزینهٔ «اعسار از پرداخت هزینه دادرسی»
    """
    # ۱) کلیک «افزودن» (#btnAddSection)
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        logging.warning(f"[CHECK] دکمهٔ «افزودن» برای خواستهٔ فرعی [{label}] کلیک نشد")
        return False
    await asyncio.sleep(3)
    await wait_for_angular_idle(page)
    await asyncio.sleep(1)

    # ۲) باز کردن دراپ‌داون «خواسته» ردیف جدید (آخرین ردیف) + تایپ + انتخاب
    ok = await _select_khasteh_option(
        page, request_title="", bot=bot, user_id=user_id,
        search_term=search_term, target_texts=target_texts,
        fallback_texts=fallback_texts, pick_first=pick_first, last_row=True)
    if ok:
        logging.info(f"[CHECK] خواستهٔ فرعی [{label}] با موفقیت اضافه شد")
    else:
        logging.warning(f"[CHECK] خواستهٔ فرعی [{label}] انتخاب نشد")
    return ok




async def _click_sana_inquiry_button(page, bot: Bot, user_id: int, role: str = "") -> bool:
    """کلیک دکمهٔ استعلام شخص (ثنا).

    ⚠️ باگ قبلی: کد `#btnCallNationalityCode` را کلیک می‌کرد؛ در بخش‌های
    خواهان/خوانده/مطلع/گواه دکمهٔ استعلام اصلاً id ندارد. طبق HTML مشخصات:
        <button class="btn btn-warning btn-sm" tooltip="استعلام شخص"
                ng-click="actions.callNationalityCode(...)">
            <i class="glyphicon glyphicon-refresh"></i>
        </button>
    """
    clicked = await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button[ng-click*="callNationalityCode"]'));
        const visible = btns.filter(b => !b.disabled && b.offsetParent !== null);
        const btn = (visible.length > 0) ? visible[0] : btns.find(b => !b.disabled);
        if (btn) { btn.click(); return true; }
        // فال‌بک: دکمهٔ warning با tooltip استعلام
        const warns = Array.from(document.querySelectorAll('button.btn-warning'));
        const w = warns.find(b => !b.disabled && (
            (b.getAttribute("tooltip") || "").includes("استعلام") ||
            (b.getAttribute("title") || "").includes("استعلام")
        ));
        if (w) { w.click(); return true; }
        return false;
    }''')
    if clicked:
        logging.info(f"[CHECK] دکمهٔ استعلام شخص کلیک شد (role={role})")
    else:
        logging.warning(f"[CHECK] دکمهٔ استعلام شخص پیدا نشد (role={role})")
    return clicked


def _sana_popup_kind(popup_text: str) -> str:
    """دسته‌بندی متن پاپ‌آپ استعلام ثنا."""
    if not popup_text:
        return ""
    if ("منقضی" in popup_text or "منقضي" in popup_text or
            "رایانه ای دیگر" in popup_text or "رایانه اي ديگر" in popup_text or
            "اعتبار ورود" in popup_text or "ورود قبلی" in popup_text or "ورود قبلي" in popup_text):
        return "session"
    if ("اطلاعاتی با این شناسه ملی ثبت نشده است" in popup_text or
            "اطلاعاتي با اين شناسه ملي ثبت نشده است" in popup_text):
        return "not_registered"
    if ("تاریخ تولد" in popup_text and "اشتباه" in popup_text) or \
       ("تاريخ تولد" in popup_text and "اشتباه" in popup_text):
        return "birthdate"
    return "other"


async def _query_sana_check(page, ng_click: str, bot: Bot, user_id: int,
                            role: str = "", national_id: str = "",
                            max_retries: int = 3) -> str:
    """استعلام شخص از ثنا با الگوی اظهارنامه — کلیک درست، انتظار لودینگ،
    بررسی پاپ‌آپ‌ها و تشخیص موفقیت (غیرفعال شدن فیلد کدملی).

    خروجی: 'ok' | 'not_registered' | 'no_response'
    """
    for attempt in range(max_retries):
        try:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                await asyncio.sleep(2)
                continue
        except NavigationResetError:
            raise  # ری‌استارت امن است — هنوز ثبت موقت انجام نشده

        # کلیک استعلام (ng-click + فال‌بک tooltip)
        clicked = await page.evaluate(f'''() => {{
            const btns = Array.from(document.querySelectorAll('button[ng-click*="{ng_click}"]'));
            const visible = btns.filter(b => !b.disabled && b.offsetParent !== null);
            const btn = (visible.length > 0) ? visible[0] : btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            const warns = Array.from(document.querySelectorAll('button.btn-warning'));
            const w = warns.find(b => !b.disabled && (
                (b.getAttribute("tooltip") || "").includes("استعلام") ||
                (b.getAttribute("title") || "").includes("استعلام")
            ));
            if (w) {{ w.click(); return true; }}
            return false;
        }}''')
        if not clicked:
            logging.warning(f"[CHECK] دکمهٔ استعلام ({ng_click}) پیدا نشد — تلاش {attempt+1}")
            await asyncio.sleep(3)
            continue

        # صبر اولیه + لودینگ افقی
        await asyncio.sleep(5)
        await wait_for_horizontal_loading_bar(page, bot, user_id)
        await asyncio.sleep(2)

        # بررسی انقضای نشست بعد از استعلام
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(3)
            continue

        # بررسی پاپ‌آپ خطا
        popup_text = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            return ((h2 ? h2.innerText : '') + ' ' + (p ? p.innerText : '')).trim() || null;
        }''')

        if popup_text:
            kind = _sana_popup_kind(popup_text)
            # بستن پاپ‌آپ
            await page.evaluate('''() => {
                const btn = document.querySelector('.sweet-alert .confirm, .sweet-alert .cancel');
                if (btn) btn.click();
            }''')
            await asyncio.sleep(1)

            if kind == "session":
                # مدیریت شده توسط check_and_handle_expiry — تلاش مجدد
                continue

            if kind in ("not_registered", "birthdate"):
                logging.warning(
                    f"[CHECK][{role}] خطای استعلام ثنا برای کدملی {national_id}: {popup_text!r}")
                return "not_registered"

            logging.warning(f"[CHECK][{role}] پاپ‌آپ استعلام (تلاش {attempt+1}): {popup_text!r}")
            await asyncio.sleep(3)
            continue

        # تشخیص موفقیت: فیلد کدملی ExtractedFromSana → غیرفعال
        success = await page.evaluate('''() => {
            const inp = document.querySelector('#txtRealIrNationalityCode1, #txtRealIrNationalityCode');
            if (inp && inp.disabled) return true;
            const disabled = document.querySelector('input[ng-disabled*="ExtractedFromSana"]');
            return disabled !== null;
        }''')
        if success:
            logging.info(f"[CHECK][{role}] استعلام ثنا موفق (کدملی {national_id})")
            return "ok"

        await asyncio.sleep(4)

    logging.warning(f"[CHECK][{role}] استعلام ثنا پس از {max_retries} تلاش پاسخ قطعی نداد")
    return "no_response"


async def _notify_sana_query_failure(bot: Bot, user_id: int, national_id: str,
                                     role: str, error_text: str):
    """پیام خطای استعلام ثنا برای کاربر و مدیر (قطع فرآیند بدون تلاش مجدد)."""
    user_msg = (
        f"⚠️ *خطا در استعلام {role}*\n\n"
        f"کدملی: `{national_id}`\n"
        f"خطای سامانه ثنا: «{error_text[:200]}»\n\n"
        "در حال حاضر امکان ادامهٔ ثبت دادخواست وجود ندارد.\n"
        "لطفاً پس از رفع مشکل (احتمالاً ثبت‌نام/تکمیل اطلاعات در سامانه ثنا) "
        "مجدداً تلاش فرمایید."
    )
    try:
        await bot.send_message(user_id, user_msg)
    except Exception:
        pass
    try:
        await bot.send_message(
            ADMIN_ID,
            f"❌ [CHECK] استعلام ثنا ناموفق — کاربر {user_id} | {role} | "
            f"کدملی {national_id} | خطا: {error_text[:200]}")
    except Exception:
        pass
    return user_msg


async def _fill_real_person(page, national_id: str, bot: Bot, user_id: int,
                            role: str = "", idx: int = 0):
    """پر کردن کدملی شخص حقیقی + استعلام ثنا (با دکمهٔ درست — بدون id).

    طبق مشخصات: کدملی در فیلد وارد شود و سپس «گزینه استعلام» زده شود؛
    این گزینه قبلاً انتخاب نمی‌شد چون دکمه id ندارد.
    در صورت خطای ثنا (ثبت‌نام نشده و ...) فرآیند با پیام مناسب قطع می‌شود.
    """
    # پر کردن فیلد کدملی
    for sel in ["#txtRealIrNationalityCode1", "#txtRealIrNationalityCode"]:
        elem_count = await page.locator(sel).count()
        if elem_count > 0:
            await page.evaluate('''(sel, val) => {
                const inp = document.querySelector(sel);
                if (inp && inp.offsetParent !== null) {
                    inp.focus();
                    inp.value = "";
                    inp.value = val;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', sel, national_id)
            await asyncio.sleep(1)
            break

    # ⭐ استعلام ثنا — دکمهٔ استعلام از طریق ng-click (id ندارد!)
    status = await _query_sana_check(page, "actions.callNationalityCode", bot, user_id,
                                     role=role, national_id=national_id)
    if status == "not_registered":
        # قطع فرآیند — پیام کاربر/مدیر + CheckAbortError (بدون تلاش مجدد)
        user_msg = await _notify_sana_query_failure(
            bot, user_id, national_id, role,
            "اطلاعاتی با این شناسه ملی در سامانه ثنا ثبت نشده است")
        raise CheckAbortError(
            f"استعلام ثنا برای {role} (کدملی {national_id}) ثبت‌نشده/ناموفق",
            step="SANA_QUERY_FAILED", user_msg=user_msg)
    if status == "no_response":
        # پاسخ قطعی نگرفتیم — هشدار و ادامه (اگر فرم واقعاً نامعتبر باشد،
        # bill_no خالی در ثبت موقت قطعش می‌کند)
        logging.warning(f"[CHECK][{role}] استعلام بدون پاسخ — ادامه با احتیاط")


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int,
                             role: str = "", idx: int = 0):
    """پر کردن اطلاعات شخص حقوقی + استعلام شرکت و نماینده"""
    company_id = person.get("company_id", "")
    nat_id = person.get("national_id", "")
    rep_type = person.get("representative_type", "")

    agent_value = "0091000010000008" if rep_type == "مدیرعامل" else "0091000010000010"

    # انتخاب نوع نماینده
    await page.evaluate('''(val) => {
        const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
        if (sel && !sel.disabled) {
            sel.value = val;
            sel.dispatchEvent(new Event("input", { bubbles: true }));
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }''', agent_value)
    await asyncio.sleep(2)

    # وارد کردن شناسه ملی شرکت
    await page.evaluate('''(val) => {
        const inp = document.querySelector('#txtLegalNationalityCode');
        if (inp && inp.offsetParent !== null) {
            inp.value = val;
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }''', company_id)
    await asyncio.sleep(1)

    # ⭐ استعلام شرکت — با دکمهٔ درست (ng-click)
    company_status = await _query_sana_check(
        page, "actions.callLegalNationalityCode", bot, user_id,
        role=f"{role} (شرکت)", national_id=company_id)
    if company_status == "not_registered":
        user_msg = await _notify_sana_query_failure(
            bot, user_id, company_id, f"{role} (شناسه ملی شرکت)",
            "اطلاعاتی با این شناسه ملی در سامانه ثنا ثبت نشده است")
        raise CheckAbortError(
            f"استعلام ثنا برای شرکت {role} (شناسه {company_id}) ناموفق",
            step="SANA_QUERY_FAILED", user_msg=user_msg)

    # وارد کردن کدملی نماینده
    if nat_id:
        for _try in range(5):
            set_ok = await page.evaluate('''(val) => {
                const inp = document.querySelector('#txtRealIrNationalityCode');
                if (inp && !inp.disabled) {
                    inp.value = val;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                    return true;
                }
                return false;
            }''', nat_id)
            if set_ok:
                break
            await asyncio.sleep(3)

        # ⭐ استعلام نماینده
        rep_status = await _query_sana_check(
            page, "actions.callNationalityCode", bot, user_id,
            role=f"{role} (نماینده)", national_id=nat_id)
        if rep_status == "not_registered":
            user_msg = await _notify_sana_query_failure(
                bot, user_id, nat_id, f"{role} (نماینده)",
                "اطلاعاتی با این شناسه ملی در سامانه ثنا ثبت نشده است")
            raise CheckAbortError(
                f"استعلام ثنا برای نمایندهٔ {role} (کدملی {nat_id}) ناموفق",
                step="SANA_QUERY_FAILED", user_msg=user_msg)


async def _fill_lawyer_person(page, national_id: str, bot: Bot, user_id: int):
    """پر کردن کدملی وکیل + استعلام"""
    await _fill_real_person(page, national_id, bot, user_id, role="وکیل")


async def _download_check_images(bot: Bot, images: list, user_id: int) -> list:
    """دانلود تصاویر چک از بله — هر دو فرمت dict{file_id} و file_id خام"""
    file_ids = []
    for img in (images or []):
        if isinstance(img, dict):
            fid = img.get("file_id")
        else:
            fid = img
        if fid:
            file_ids.append(fid)
    paths = []
    if file_ids:
        paths = await download_images_from_bale(bot, file_ids, user_id, prefix="CHECK")
    return paths


async def _enter_attachments_section(page, bot: Bot, user_id: int, bill_no: str) -> bool:
    """ورود به مرحلهٔ «منضمات» با retry و بررسی پاپ‌آپ خطای سامانه (الگوی اظهارنامه).

    ⚠️ از safe_click_by_text استفاده نمی‌شود (NavigationResetError →
    ری‌استارت کل تسکِ ثبت‌شده = ثبت تکراری).
    """
    for attempt in range(3):
        clicked = await _click_step_box(page, "منضمات", bot, user_id)
        if clicked:
            await resilient_sleep(page, 5, bot, user_id)

            # بررسی خطای سامانه (پاپ‌آپ خطا مثل «خطای دسترسی به اطلاعات»)
            has_error = await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (!popup) return false;
                const icon = popup.querySelector('.sa-icon.sa-error');
                return icon && window.getComputedStyle(icon).display !== 'none';
            }''')
            if not has_error:
                return True

            # بستن پاپ‌آپ خطا و تلاش مجدد
            await page.evaluate('''() => {
                const btn = document.querySelector('.sweet-alert .confirm');
                if (btn) btn.click();
            }''')
            await asyncio.sleep(1)
            logging.warning(f"[CHECK][منضمات] خطای سامانه در ورود به منضمات (تلاش {attempt+1}/3)")

        # بازگشت به فهرست و تلاش مجدد
        await _click_goto_main(page, bot, user_id)
        await resilient_sleep(page, 4, bot, user_id)

    await bot.send_message(
        user_id,
        f"⚠️ *خطا در بخش منضمات*\nکد بایگانی: `{bill_no}`\n"
        f"با شماره *{SUPPORT_PHONE}* در واتساپ یا بله پیام دهید.")
    await bot.send_message(
        ADMIN_ID,
        f"❌ [CHECK] خطا در ورود به منضمات (۳ تلاش ناموفق) کاربر {user_id} | کد: {bill_no}")
    return False


async def _select_attachment_type(page, label: str) -> bool:
    """انتخاب نوع پیوست از #attachmentType — تطبیق دقیق برچسب تا
    «تصوير چك» با «تصوير چك و گواهينامه عدم پرداخت» اشتباه گرفته نشد."""
    ok = await page.evaluate('''(label) => {
        const sel = document.querySelector('#attachmentType');
        if (!sel || sel.disabled) return false;
        const opts = Array.from(sel.options);
        const target = opts.find(o => (o.innerText || '').trim() === label)
                      || opts.find(o => (o.innerText || '').includes(label));
        if (target) {
            sel.value = target.value;
            sel.dispatchEvent(new Event("input", { bubbles: true }));
            sel.dispatchEvent(new Event("change", { bubbles: true }));
            return true;
        }
        return false;
    }''', label)
    if ok:
        logging.info(f"[CHECK][منضمات] نوع پیوست انتخاب شد: {label}")
        await asyncio.sleep(3)
        await wait_for_angular_idle(page)
        await asyncio.sleep(1)
    else:
        logging.warning(f"[CHECK][منضمات] نوع پیوست «{label}» در لیست پیدا نشد")
    return ok


async def _central_bank_inquiry(page, tracking_no: str, bot: Bot, user_id: int,
                                bill_no: str) -> str:
    """استعلام از بانک مرکزی برای کدرهگیری چک (فقط «صدور اجرائیه چک»).

    طبق مشخصات کارفرما:
      - کدرهگیری در #txtInqueryNo وارد شود
      - دکمهٔ استعلام (#inqueryNo0 — tooltip «استعلام از بانک مرکزی») زده شود
      - ۱۵ ثانیه صبر شود
      - پیام «استعلام از بانک مرکزی با موفقیت انجام شد .» → ادامهٔ مراحل
      - پیام ورود همزمان («با این شناسه ... منقضی شده است») → به مدیر گفته
        شود مجدداً لاگین کند و دوباره استعلام زده شود
      - خطای کدرهگیری → به کاربر گفته شود کدرهگیری چک اشتباه است +
        کد بایگانی ارسال شود + شمارهٔ پشتیبانی
      - هر خطای دیگر → حداکثر ۳ بار تلاش مجدد؛ اگر نشد، کد بایگانی ارسال
        شود و «در بخش منضمات سامانه قطع می‌باشد» + شمارهٔ پشتیبانی

    خروجی: 'ok' | 'wrong_code' | 'failed'
    """
    # ۱) وارد کردن کدرهگیری
    if tracking_no:
        filled = await page.evaluate('''(val) => {
            const inp = document.querySelector('#txtInqueryNo');
            if (inp && !inp.disabled) {
                inp.focus();
                inp.value = "";
                inp.value = val;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
            return false;
        }''', tracking_no)
        if filled:
            logging.info("[CHECK][منضمات] کدرهگیری چک در فیلد درج شد")
            await asyncio.sleep(1)
        else:
            logging.warning("[CHECK][منضمات] فیلد کدرهگیری (#txtInqueryNo) پیدا نشد")
    else:
        logging.warning("[CHECK][منضمات] کدرهگیری چک از کاربر دریافت نشده — استعلام تلاش می‌شود")

    # ۲) حلقهٔ استعلام — حداکثر ۳ تلاش
    for inquiry_attempt in range(3):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#inqueryNo0') ||
                         document.querySelector('button[ng-click*="checkDocumentDataAndComplete"]');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            logging.warning(
                f"[CHECK][منضمات] دکمهٔ استعلام بانک مرکزی (#inqueryNo0) پیدا/کلیک نشد — "
                f"تلاش {inquiry_attempt+1}/3")
            await asyncio.sleep(2)
            continue

        await wait_for_horizontal_loading_bar(page, bot, user_id)
        await resilient_sleep(page, 15, bot, user_id)  # ⭐ طبق مشخصات: ۱۵ ثانیه صبر

        # ورود همزمان/انقضا؟ → مدیر لاگین مجدد می‌کند و همان استعلام دوباره زده می‌شود
        try:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
        except NavigationResetError:
            try:
                await page.goto("https://sakha2.adliran.ir/Offices/Index")
                await asyncio.sleep(4)
            except Exception:
                pass
            had_expiry = False
        if had_expiry:
            logging.warning(
                "[CHECK][منضمات] نشست حین استعلام بانک مرکزی منقضی شد — مدیر مجدداً "
                "لاگین کرد؛ استعلام دوباره زده می‌شود")
            await asyncio.sleep(3)
            continue

        popup_text = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            return ((h2 ? h2.innerText : '') + ' ' + (p ? p.innerText : '')).trim() || null;
        }''')

        # بستن پاپ‌آپ (در همهٔ حالت‌ها لازم است)
        close_popup_js = '''() => {
            const btn = document.querySelector('.sweet-alert .confirm, .sweet-alert .cancel');
            if (btn) btn.click();
        }'''

        if popup_text and "موفق" in popup_text and "بانک مرکزی" in popup_text:
            # ✅ پیام موفقیت — طبق مشخصات: برو ادامهٔ مراحل
            logging.info("[CHECK][منضمات] استعلام بانک مرکزی موفق")
            await page.evaluate(close_popup_js)
            await asyncio.sleep(2)
            return "ok"

        if popup_text and "موفق" in popup_text:
            # پیام موفقیت با متن کمی متفاوت
            logging.info(f"[CHECK][منضمات] استعلام بانک مرکزی موفق: {popup_text!r}")
            await page.evaluate(close_popup_js)
            await asyncio.sleep(2)
            return "ok"

        if popup_text:
            kind = _sana_popup_kind(popup_text)
            if kind == "session":
                # پیام «ورود به سامانه در صفحه یا رایانه ای دیگر ... منقضی شده است»
                # طبق مشخصات: به مدیر گفته شود مجدداً لاگین کند و استعلام دوباره زده شود
                await page.evaluate(close_popup_js)
                await asyncio.sleep(1)
                await bot.send_message(
                    ADMIN_ID,
                    "⚠️ [CHECK] خطای ورود همزمان در استعلام بانک مرکزی — لطفاً مجدداً "
                    f"لاگین کنید؛ استعلام دوباره زده می‌شود. کاربر: {user_id} | کد: {bill_no}")
                await handle_session_expired(bot, user_id, page=page)
                await asyncio.sleep(3)
                continue

            # خطای کدرهگیری اشتباه — تشخیص با کلیدواژه‌های محتمل
            # (متن دقیق این خطا در مشخصات ذکر نشده بود)
            is_wrong_code = (
                ("رهگیری" in popup_text and any(k in popup_text for k in
                    ("اشتباه", "نامعتبر", "صحیح", "موجود نیست", "یافت نشد", "تعریف نشده"))) or
                ("شناسه" in popup_text and any(k in popup_text for k in
                    ("اشتباه", "نامعتبر", "صحیح", "موجود نیست", "یافت نشد", "تعریف نشده"))) or
                "کدرهگیری" in popup_text or "کد رهگیری" in popup_text
            )
            if is_wrong_code:
                logging.warning(f"[CHECK][منضمات] کدرهگیری اشتباه: {popup_text!r}")
                await page.evaluate(close_popup_js)
                await asyncio.sleep(1)
                # ⭐ طبق مشخصات: سریعاً به کاربر بگو کدرهگیری چک اشتباه است +
                # کد بایگانی ثبت دادخواست + شمارهٔ پشتیبانی
                await bot.send_message(
                    user_id,
                    "⚠️ کدرهگیری چک اشتباه است.\n"
                    f"🔢 کد بایگانی دادخواست ثبت‌شدهٔ شما: `{bill_no}`\n"
                    f"جهت ادامه تکمیل ثبت دادخواست به شماره {SUPPORT_PHONE} "
                    "در بله یا واتس‌اپ پیام دهید.")
                return "wrong_code"

            # هر خطای دیگر → طبق مشخصات: مجدداً استعلام تا ۳ بار
            logging.warning(
                f"[CHECK][منضمات] استعلام بانک مرکزی ناموفق "
                f"(تلاش {inquiry_attempt+1}/3): {popup_text!r}")
            await page.evaluate(close_popup_js)
            await asyncio.sleep(2)
            continue

        # پاپ‌آپی نبود — شاید هنوز لودینگ است؛ تلاش مجدد
        logging.warning(
            f"[CHECK][منضمات] پاسخی از استعلام بانک مرکزی دریافت نشد (تلاش {inquiry_attempt+1}/3)")
        await asyncio.sleep(3)

    # ⛔ پس از ۳ تلاش هم موفق نشد — طبق مشخصات: کد بایگانی برای کاربر ارسال
    # شود و اعلام شود در بخش منضمات سامانه قطع می‌باشد + شمارهٔ پشتیبانی
    logging.error(f"[CHECK][منضمات] استعلام بانک مرکزی پس از ۳ تلاش ناموفق ماند (user={user_id})")
    await bot.send_message(
        ADMIN_ID,
        f"❌ [CHECK] استعلام بانک مرکزی برای کاربر {user_id} پس از ۳ تلاش ناموفق ماند. "
        f"تصاویر چک آپلود نشدند — این پرونده را دستی بررسی کنید. کد بایگانی: `{bill_no}`"
    )
    await bot.send_message(
        user_id,
        "⚠️ در بخش منضمات سامانه قطع می‌باشد.\n"
        f"🔢 کد بایگانی دادخواست ثبت‌شدهٔ شما: `{bill_no}`\n"
        f"به شماره {SUPPORT_PHONE} در واتس‌اپ یا بله پیام دهید."
    )
    return "failed"


async def _fill_check_document_fields(page) -> None:
    """تکمیل فیلدهای سند پیوست چک — طبق مشخصات کارفرما:
      - #txtDeductionAmount (Amount): عدد ۱
      - #txtExporter (Lookup): آخرین گزینه — «هیچکدام»
      - #txtHolder (YesNo): اولین گزینه — «بله»
      - #txtRejectReason (Lookup): اولین گزینه — «کسرموجودی»
      - #txtReasonForIssuance (Lookup): آخرین گزینه — «بابت پرداخت بدهی»

    فیلدها فقط در صورت وجود پر می‌شوند (مسیر مطالبه وجه ممکن است برخی را
    نداشته باشد — «مسیر درج اطلاعات کمی متفاوت است»).
    """

    async def _select_option(select_id: str, mode: str):
        """انتخاب اولین/آخرین گزینهٔ واقعیِ select (بدون placeholder/خالی)."""
        ok = await page.evaluate('''(sid, mode) => {
            const sel = document.querySelector('#' + sid);
            if (!sel || sel.disabled) return false;
            const opts = Array.from(sel.options).filter(o => {
                const v = (o.value || '').trim();
                const t = (o.text || '').trim();
                if (!v || v === "?" || v === "0" || v.startsWith("? string")) return false;
                if (!t) return false;
                return true;
            });
            if (opts.length === 0) return false;
            const target = (mode === 'last') ? opts[opts.length - 1] : opts[0];
            sel.focus();
            sel.value = target.value;
            sel.dispatchEvent(new Event("input", { bubbles: true }));
            sel.dispatchEvent(new Event("change", { bubbles: true }));
            return true;
        }''', select_id, mode)
        if ok:
            logging.info(f"[CHECK][منضمات] {select_id} → گزینهٔ {mode} انتخاب شد")
        else:
            logging.warning(f"[CHECK][منضمات] فیلد {select_id} پیدا نشد/غیرفعال است — رد شد")
        await asyncio.sleep(1)
        return ok

    # ۱) Amount → عدد ۱
    amount_ok = await page.evaluate('''() => {
        const inp = document.querySelector('#txtDeductionAmount');
        if (inp && !inp.disabled) {
            inp.focus();
            inp.value = "";
            inp.value = "1";
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            return true;
        }
        return false;
    }''')
    if amount_ok:
        logging.info("[CHECK][منضمات] فیلد Amount (= #txtDeductionAmount) روی ۱ قرار گرفت")
    else:
        logging.warning("[CHECK][منضمات] فیلد Amount (#txtDeductionAmount) پیدا نشد — رد شد")
    await asyncio.sleep(1)

    # ۲) Exporter → آخرین گزینه («هیچکدام»)
    await _select_option("txtExporter", "last")

    # ۳) Holder → اولین گزینه («بله»)
    await _select_option("txtHolder", "first")

    # ۴) RejectReason → اولین گزینه («کسرموجودی»)
    await _select_option("txtRejectReason", "first")

    # ۵) ReasonForIssuance → آخرین گزینه («بابت پرداخت بدهی»)
    await _select_option("txtReasonForIssuance", "last")


async def _click_edit_document_last_row(page, doc_title: str, bot: Bot, user_id: int,
                                        table_wait_timeout: int = 20,
                                        uploader_wait_timeout: int = 15) -> bool:
    """کلیک روی دکمهٔ editDocument آخرین ردیفِ منطبق با doc_title + انتظار آپلودر.

    ⚠️ چرا آخرین ردیف؟ برای فقرات متعدد چک، همهٔ ردیف‌های جدول پیوست عنوان
    یکسان («تصوير چك» / «تصوير چك و گواهينامه عدم پرداخت») دارند؛ ردیفِ
    تازه‌ذخیره‌شده همیشه در انتهای جدول اضافه می‌شود — پس باید آخرین تطبیق
    کلیک شود (الگوی upload_helpers اولین تطبیق را می‌زند).

    روش کلیک: Playwright → فال‌بک AngularJS scope (actions.editDocument) →
    کلیک JS ساده — سپس انتظار ظاهر شدن #files_multipleFileUploader.
    """
    # ۱) پیدا کردن آخرین ردیف منطبق و علامت‌گذاری دکمهٔ ویرایش آن
    found = False
    for i in range(table_wait_timeout * 2):
        if i % 10 == 0:
            try:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
                if had_expiry:
                    await asyncio.sleep(2)
            except NavigationResetError:
                return False

        marked = await page.evaluate('''(label) => {
            // پاک‌سازی علامت قبلی
            document.querySelectorAll('button[data-check-edit]').forEach(
                b => b.removeAttribute('data-check-edit'));
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            let target = null;
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                for (const cell of cells) {
                    const text = (cell.innerText || '').trim();
                    if (text.includes(label)) {
                        const editBtn = row.querySelector('button[ng-click*="editDocument"]');
                        if (editBtn && !editBtn.disabled) target = editBtn;
                    }
                }
            }
            if (target) { target.setAttribute('data-check-edit', '1'); return true; }
            return false;
        }''', doc_title)
        if marked:
            found = True
            break
        await asyncio.sleep(0.5)

    if not found:
        logging.warning(f"[CHECK][منضمات] ردیف [{doc_title}] در جدول پیوست‌ها ظاهر نشد")
        return False

    # ۲) کلیک روی دکمهٔ علامت‌خورده — Playwright، سپس AngularJS، سپس JS
    try:
        target = page.locator('button[data-check-edit]')
        await target.scroll_into_view_if_needed(timeout=5000)
        await asyncio.sleep(0.5)
        await target.click(timeout=10000)
        logging.info(f"[CHECK][منضمات] دکمهٔ editDocument ردیف [{doc_title}] کلیک شد")
    except Exception as e:
        logging.warning(f"[CHECK][منضمات] کلیک Playwright ناموفق ({e}) — تلاش با AngularJS")
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[data-check-edit]');
            if (!btn) return false;
            try {
                if (typeof angular !== 'undefined') {
                    const scope = angular.element(btn).scope();
                    if (scope && scope.$parent && scope.$parent.actions) {
                        const $index = scope.$parent.$index !== undefined ? scope.$parent.$index : 0;
                        scope.$apply(() => { scope.$parent.actions.editDocument($index); });
                        return true;
                    }
                    if (scope && scope.actions) {
                        const $index = scope.$index !== undefined ? scope.$index : 0;
                        scope.$apply(() => { scope.actions.editDocument($index); });
                        return true;
                    }
                }
            } catch (err) {}
            btn.click();
            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            return true;
        }''')
        if not clicked:
            logging.error("[CHECK][منضمات] هیچ روشی برای کلیک editDocument کار نکرد")
            await page.evaluate('''() => {
                const btn = document.querySelector('button[data-check-edit]');
                if (btn) btn.removeAttribute('data-check-edit');
            }''')
            return False

    # ۳) انتظار برای ظاهر شدن آپلودر (#files_multipleFileUploader)
    for i in range(uploader_wait_timeout * 2):
        if i % 10 == 0:
            try:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
                if had_expiry:
                    await asyncio.sleep(2)
            except NavigationResetError:
                return False
        uploader_count = await page.evaluate(
            "() => document.querySelectorAll('#files_multipleFileUploader').length")
        if uploader_count and int(uploader_count) > 0:
            await asyncio.sleep(1)
            logging.info("[CHECK][منضمات] #files_multipleFileUploader ظاهر شد")
            await page.evaluate('''() => {
                const btn = document.querySelector('button[data-check-edit]');
                if (btn) btn.removeAttribute('data-check-edit');
            }''')
            return True
        await asyncio.sleep(0.5)

    logging.warning("[CHECK][منضمات] #files_multipleFileUploader ظاهر نشد")
    await page.evaluate('''() => {
        const btn = document.querySelector('button[data-check-edit]');
        if (btn) btn.removeAttribute('data-check-edit');
    }''')
    return False


async def _upload_check_files(page, doc_title: str, image_paths: list,
                              bot: Bot, user_id: int, bill_no: str) -> dict:
    """آپلود تصاویر یک پیوست چک با لایهٔ مقاوم upload_helpers (الگوی
    اظهارنامه/لایحه):

      ۱. آماده‌سازی فایل‌ها (فشرده‌سازی + JPEG)
      ۲. کلیک editDocument روی آخرین ردیف منطبق + انتظار آپلودر
         (⚠️ باگ قبلی: کلیک ویرایش با querySelector عمومی انجام می‌شد و
         #files_multipleFileUploader هرگز ظاهر نمی‌شد → Timeout)
      ۳. انتخاب فایل‌ها با #files_multipleFileUploader
      ۴. کلیک «آپلود همه» (#btnUploadAll) + انتظار کامل اتمام آپلود
      ۵. کلیک «تایید همه» (#btnApplyAll) + انتظار تایید
    """
    result = {"success": False, "error": None, "error_type": None}

    if not image_paths:
        result["error"] = "هیچ فایلی برای آپلود وجود ندارد"
        return result

    prepared, validation_errors = await prepare_files_for_upload(
        image_paths, bot, user_id, prefix="CHECK", compress=True, convert_to_jpeg=True)
    if not prepared:
        result["error"] = "هیچ فایل معتبری برای آپلود وجود ندارد"
        if validation_errors:
            result["error"] += ": " + "; ".join(e.get("error", "") for e in validation_errors)
        result["error_type"] = "validation"
        return result
    if validation_errors:
        logging.warning(
            f"[CHECK][منضمات] {len(validation_errors)} فایل نامعتبر حذف شد، "
            f"{len(prepared)} فایل باقی مانده")

    image_count = len(prepared)

    for attempt in range(1, 4):
        logging.info(f"[CHECK][منضمات] ─── آپلود [{doc_title}] — تلاش {attempt}/3 ───")

        try:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                await asyncio.sleep(2)

            # کلیک editDocument روی آخرین ردیف منطبق + انتظار آپلودر
            # ⚠️ برای فقرات متعدد چک همهٔ ردیف‌ها عنوان یکسان دارند؛ ردیفِ
            # تازه‌ذخیره‌شده آخرین ردیف جدول است → آخرین تطبیق کلیک می‌شود
            # (click_edit_document_for_title اولین تطبیق را می‌زند).
            edit_ok = await _click_edit_document_last_row(
                page, doc_title, bot, user_id)
            if not edit_ok:
                logging.warning(
                    f"[CHECK][منضمات] editDocument/آپلودر برای [{doc_title}] ظاهر نشد (تلاش {attempt}/3)")
                await asyncio.sleep(4)
                continue

            # انتخاب فایل‌ها
            try:
                file_input = page.locator('#files_multipleFileUploader')
                await file_input.set_input_files(prepared)
                logging.info(
                    f"[CHECK][منضمات] {image_count} فایل با #files_multipleFileUploader انتخاب شد")
            except Exception as e:
                logging.warning(f"[CHECK][منضمات] خطا در انتخاب فایل‌ها: {e}")
                await asyncio.sleep(3)
                continue
            await asyncio.sleep(3)

            # آپلود همه
            upload_all = await click_upload_all_with_retry(
                page, expected_file_count=image_count, bot=bot, user_id=user_id,
                doc_title=doc_title, prefix="CHECK")
            if not upload_all.get("success"):
                logging.error(
                    f"[CHECK][منضمات] آپلود همه [{doc_title}] ناموفق: "
                    f"{upload_all.get('error')} (نوع: {upload_all.get('error_type')})")
                if upload_all.get("error_type") == "session":
                    continue  # پس از لاگین مجدد مدیر، تلاش مجدد
                result["error"] = upload_all.get("error")
                result["error_type"] = upload_all.get("error_type")
                return result

            # تایید همه
            apply_all = await click_apply_all_with_retry(
                page, expected_count=image_count, bot=bot, user_id=user_id,
                doc_title=doc_title, prefix="CHECK")
            if not apply_all.get("success"):
                logging.error(
                    f"[CHECK][منضمات] تایید همه [{doc_title}] ناموفق: "
                    f"{apply_all.get('error')} (نوع: {apply_all.get('error_type')})")
                result["error"] = apply_all.get("error")
                result["error_type"] = apply_all.get("error_type")
                return result

            result["success"] = True
            logging.info(f"[CHECK][منضمات] آپلود [{doc_title}] با موفقیت کامل شد")
            return result

        except NavigationResetError:
            # صفحه پرت شده — برگرد به فهرست و تلاش مجدد (نه ری‌استارت کل تسک)
            try:
                await page.goto("https://sakha2.adliran.ir/Offices/Index")
                await asyncio.sleep(4)
            except Exception:
                pass
            continue
        except Exception as e:
            logging.error(f"[CHECK][منضمات] خطا در آپلود [{doc_title}] (تلاش {attempt}/3): {e}")
            await asyncio.sleep(4)
            continue

    result.setdefault("error", "آپلود پس از ۳ تلاش ناموفق ماند")
    result.setdefault("error_type", "timeout")
    return result


async def _fill_extra_attachment_form(page, doc_title: str, prepared_paths: list,
                                      force_page_count: int = None) -> bool:
    """فرم پیوست‌های اضافی چک — «تصوير مدرک نمايندگي» برای مدرک نمایندگی،
    وگرنه «ساير ضمائم» + عنوان دلخواه (الگوی upload_helpers)."""
    page_count = force_page_count if force_page_count else len(prepared_paths or [])

    if "نمایندگی" in doc_title or "نمايندگي" in doc_title:
        ok = await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (!sel || sel.disabled) return false;
            const opts = Array.from(sel.options);
            const opt = opts.find(o => (o.text || '').includes("مدرک نمايندگي") ||
                                        (o.text || '').includes("مدرک نمایندگی"));
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event("input", { bubbles: true }));
                sel.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
            return false;
        }''')
        if ok:
            logging.info("[CHECK][منضمات] نوع پیوست «تصوير مدرک نمايندگي» انتخاب شد")
            await asyncio.sleep(3)
            await wait_for_angular_idle(page)
            await asyncio.sleep(1)
        return ok

    return await _default_fill_other_attachment_form(page, doc_title, page_count)




# شناسهٔ فیلدهای فرم «استشهاديه محلي» — طبق دستور کارفرما در همهٔ این فیلدها
# عدد ۱ قرار می‌گیرد:
#   txtName, txtNationalityCode, txtFatherName, txtHomeAddress (شخص اول)
#   txtName2, txtFatherName2, txtNationalityCode2, txtHomeAddress2 (شخص دوم)
ESTESHADIEH_FIELD_IDS = [
    "txtName", "txtNationalityCode", "txtFatherName", "txtHomeAddress",
    "txtName2", "txtFatherName2", "txtNationalityCode2", "txtHomeAddress2",
]


async def _fill_esteshahadieh_fields(page) -> None:
    """تکمیل فرم استشهادیه محلی — در تمام فیلدهای زیر عدد ۱ قرار می‌گیرد:

    txtName, txtNationalityCode, txtFatherName, txtHomeAddress,
    txtName2, txtFatherName2, txtNationalityCode2, txtHomeAddress2
    """
    for field_id in ESTESHADIEH_FIELD_IDS:
        ok = await page.evaluate('''(fid) => {
            const inp = document.querySelector('#' + fid);
            if (inp && !inp.disabled) {
                inp.focus();
                inp.value = "";
                inp.value = "1";
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
            return false;
        }''', field_id)
        if ok:
            logging.info(f"[CHECK][استشهادیه] فیلد #{field_id} = ۱")
        else:
            logging.warning(f"[CHECK][استشهادیه] فیلد #{field_id} پیدا نشد — رد شد")
        await asyncio.sleep(0.7)


async def _upload_esteshahadieh_attachment(page, image_paths: list, bot: Bot,
                                           user_id: int, bill_no: str) -> bool:
    """ثبت پیوست «استشهاديه محلي» — طبق دستور کارفرما (عیناً):

      ۱. در قسمت منضمات، نوع پیوست «استشهاديه محلي» انتخاب شود
      ۲. در تمام فیلدهای txtName / txtNationalityCode / txtFatherName /
         txtHomeAddress / txtName2 / txtFatherName2 / txtNationalityCode2 /
         txtHomeAddress2 عدد ۱ قرار بگیرد
      ۳. «ثبت و ویرایش پیوست» (#btnSaveDoc)
      ۴. آپلود تصاویر استشهادیه (همان الگوی فقرات چک)
    """
    # ۱) انتخاب نوع پیوست «استشهاديه محلي»
    if not await _select_attachment_type(page, "استشهاديه محلي"):
        await bot.send_message(
            ADMIN_ID,
            f"❌ [CHECK] نوع پیوست «استشهاديه محلي» در لیست پیدا نشد — کاربر {user_id} | "
            f"کد: {bill_no}")
        return False

    # ۲) درج عدد ۱ در تمام فیلدهای استشهادیه
    await _fill_esteshahadieh_fields(page)

    # ۳) «ثبت و ویرایش پیوست»
    save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix="CHECK")
    if not save_ok:
        error_text = await _uh_error_popup_text(page)
        logging.error(f"[CHECK][استشهادیه] ذخیرهٔ پیوست ناموفق: {error_text!r}")
        await bot.send_message(
            ADMIN_ID,
            f"❌ [CHECK] ذخیرهٔ پیوست استشهادیه ناموفق — کاربر {user_id} | کد: {bill_no} | "
            f"خطا: {(error_text or 'نامشخص')[:200]}")
        await bot.send_message(
            user_id,
            "⚠️ ثبت پیوست استشهادیه در بخش منضمات با خطا مواجه شد.\n"
            f"🔢 کد بایگانی: `{bill_no}`\n"
            f"لطفاً به شماره {SUPPORT_PHONE} در واتساپ یا بله پیام دهید.")
        return False

    await resilient_sleep(page, 5, bot, user_id)

    # ۴) آپلود تصاویر استشهادیه
    upload_result = await _upload_check_files(
        page, "استشهاديه محلي", image_paths, bot, user_id, bill_no)
    if not upload_result.get("success"):
        logging.error(f"[CHECK][استشهادیه] آپلود ناموفق: {upload_result.get('error')}")
        await bot.send_message(
            ADMIN_ID,
            f"❌ [CHECK] آپلود تصاویر استشهادیه ناموفق — کاربر {user_id} | کد: {bill_no} | "
            f"خطا: {(upload_result.get('error') or 'نامشخص')[:200]}")
        await bot.send_message(
            user_id,
            "⚠️ آپلود تصاویر استشهادیه در بخش منضمات ناموفق بود.\n"
            f"🔢 کد بایگانی: `{bill_no}`\n"
            f"لطفاً به شماره {SUPPORT_PHONE} در واتساپ یا بله پیام دهید.")
        return False

    return True


async def _process_check_attachments(
    page,
    request_title: str,
    cheque_items: list,
    attachment_groups: list,
    bot: Bot,
    user_id: int,
    bill_no: str) -> bool:
    """اجرای کامل مرحلهٔ «منضمات» دادخواست چک — طبق مشخصات کارفرما.

    مسیر:
      ۱. ورود به باکس «منضمات» (با retry)
      ۲. برای هر فقره چک:
         - (فقره‌های بعد از اولی) کلیک «پیوست جدید» (#newAttachmentType)
         - انتخاب نوع پیوست: اجرائیه → «تصوير چك و گواهينامه عدم پرداخت» /
           مطالبه وجه → «تصوير چك»
         - دانلود تصاویر همان فقره از بله
         - (فقط اجرائیه) کدرهگیری + استعلام بانک مرکزی با تحلیل پاپ‌آپ:
           موفق → ادامه | ورود همزمان → لاگین مجدد مدیر + تلاش مجدد |
           کدرهگیری اشتباه → پیام و توقف | خطای دیگر → ۳ تلاش → پیام قطعی
         - تکمیل فیلدهای سند (Amount=1، Exporter=هیچکدام، Holder=بله،
           RejectReason=کسرموجودی، ReasonForIssuance=بابت پرداخت بدهی)
         - «ثبت و ویرایش پیوست» (#btnSaveDoc) + انتظار پیام تایید
         - آپلود و تایید تصاویر (همان الگو/اخطارهای منضمات قبلی)
      ۳. پیوست‌های اضافی کاربر (check_attachment_groups) با «سایر ضمائم»
         (و «تصوير مدرک نمايندگي» برای مدرک نمایندگی) — الگوی اظهارنامه

    خروجی: True = ادامهٔ فرآیند | False = قطع (پیام‌ها ارسال شده‌اند)
    """
    is_ejra = (request_title == "صدور اجرائیه چک")
    attachment_label = ("تصوير چك و گواهينامه عدم پرداخت" if is_ejra else "تصوير چك")

    # ۱) ورود به منضمات
    if not await _enter_attachments_section(page, bot, user_id, bill_no):
        return False

    # ۲) فقرات چک
    for item_idx, cheque in enumerate(cheque_items):
        item_tracking = (cheque.get("tracking_no") or "").strip()
        item_images = cheque.get("images") or []

        # فقره‌های بعد از اولی → «پیوست جدید»
        if item_idx > 0:
            await asyncio.sleep(2)
            clicked = await page.evaluate('''() => {
                const btn = document.querySelector('#newAttachmentType');
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if clicked:
                logging.info(f"[CHECK][منضمات] کلیک «پیوست جدید» قبل از فقرهٔ {item_idx+1}")
                await asyncio.sleep(3)
                await wait_for_angular_idle(page)
                await asyncio.sleep(1)
            else:
                logging.warning("[CHECK][منضمات] دکمهٔ «پیوست جدید» (#newAttachmentType) پیدا نشد")

        # ۲.۱) انتخاب نوع پیوست (اجرائیه/مطالبه وجه → برچسب متفاوت)
        if not await _select_attachment_type(page, attachment_label):
            await bot.send_message(
                ADMIN_ID,
                f"❌ [CHECK] نوع پیوست «{attachment_label}» در لیست منضمات پیدا نشد — "
                f"کاربر {user_id} | کد: {bill_no} | فقره: {item_idx+1}")
            # ادامه نمی‌دهیم — این فقره رد شد ولی فرآیند کلی ادامه می‌یابد
            continue

        # ۲.۲) استعلام بانک مرکزی — فقط برای اجرائیه
        if is_ejra:
            inquiry_status = await _central_bank_inquiry(
                page, item_tracking, bot, user_id, bill_no)
            if inquiry_status == "wrong_code":
                # پیام کاربر داخل _central_bank_inquiry ارسال شده — توقف کل فرآیند
                return False
            if inquiry_status == "failed":
                # پیام «سامانه قطع» برای کاربر ارسال شده — توقف کل فرآیند
                return False
            # 'ok' → ادامهٔ مراحل (فیلدها + ثبت + آپلود)
        else:
            # مطالبه وجه چک — بدون کدرهگیری/استعلام بانک مرکزی؛ فقط درج
            # کدرهگیری در صورت وجود فیلد
            if item_tracking:
                await page.evaluate('''(val) => {
                    const inp = document.querySelector('#txtInqueryNo');
                    if (inp && !inp.disabled) {
                        inp.value = val;
                        inp.dispatchEvent(new Event("input", { bubbles: true }));
                        inp.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', item_tracking)
                await asyncio.sleep(1)

        # ۲.۳) دانلود تصاویر این فقره از بله
        image_paths = await _download_check_images(bot, item_images, user_id)
        if not image_paths:
            logging.warning(
                f"[CHECK][منضمات] تصویری برای فقرهٔ {item_idx+1} دانلود نشد")
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ [CHECK] تصاویر فقرهٔ {item_idx+1} کاربر {user_id} دانلود نشد — "
                f"پیوست تصویری ثبت نشد. کد: {bill_no}")
            # فرم سند ثبت شود ولی بدون تصویر — ادامه
            image_paths = []

        # ۲.۴) تکمیل فیلدهای سند (بعد از پیام تایید استعلام)
        await _fill_check_document_fields(page)

        # ۲.۵) کلیک «ثبت و ویرایش پیوست» (#btnSaveDoc) + انتظار پیام تایید
        save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix="CHECK")
        if not save_ok:
            error_text = await _uh_error_popup_text(page)
            logging.error(
                f"[CHECK][منضمات] ذخیرهٔ سند فقرهٔ {item_idx+1} ناموفق: {error_text!r}")
            await bot.send_message(
                ADMIN_ID,
                f"❌ [CHECK] ذخیرهٔ پیوست فقرهٔ {item_idx+1} ناموفق — کاربر {user_id} | "
                f"کد: {bill_no} | خطا: {(error_text or 'نامشخص')[:200]}")
            await bot.send_message(
                user_id,
                f"⚠️ ثبت پیوست فقرهٔ {item_idx+1} در بخش منضمات با خطا مواجه شد.\n"
                f"🔢 کد بایگانی: `{bill_no}`\n"
                f"لطفاً به شماره {SUPPORT_PHONE} در واتساپ یا بله پیام دهید.")
            continue  # فقرهٔ بعدی را امتحان کن

        await resilient_sleep(page, 5, bot, user_id)

        # ۲.۶) آپلود تصاویر — «همان موارد منضمات که قبلا بوده»: کلیک ویرایش،
        # انتخاب فایل‌ها، آپلود همه، تایید همه + چک همان اخطارها (session و ...)
        if image_paths:
            upload_result = await _upload_check_files(
                page, attachment_label, image_paths, bot, user_id, bill_no)
            if not upload_result.get("success"):
                logging.error(
                    f"[CHECK][منضمات] آپلود فقرهٔ {item_idx+1} ناموفق: "
                    f"{upload_result.get('error')}")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CHECK] آپلود تصاویر فقرهٔ {item_idx+1} ناموفق — کاربر {user_id} | "
                    f"کد: {bill_no} | خطا: {(upload_result.get('error') or 'نامشخص')[:200]}")
                await bot.send_message(
                    user_id,
                    f"⚠️ آپلود تصاویر فقرهٔ {item_idx+1} در بخش منضمات ناموفق بود.\n"
                    f"🔢 کد بایگانی: `{bill_no}`\n"
                    f"لطفاً به شماره {SUPPORT_PHONE} در واتساپ یا بله پیام دهید.")
                # آپلود ناموفق → فرآیند کلی ادامه می‌یابد (ثبت/هزینه/چاپ/پرداخت)

        # پاکسازی فایل‌های موقت این فقره
        for p in image_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    # ۳) پیوست‌های اضافی کاربر (غیر از تصاویر فقرات چک)
    for g_idx, group in enumerate(attachment_groups):
        group_title = group.get("title", "مستندات")
        group_images = group.get("images") or []

        # «پیوست جدید» برای هر گروه اضافی
        await asyncio.sleep(2)
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#newAttachmentType');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if clicked:
            await asyncio.sleep(3)
            await wait_for_angular_idle(page)
            await asyncio.sleep(1)
        else:
            logging.warning("[CHECK][منضمات] دکمهٔ «پیوست جدید» برای پیوست اضافی پیدا نشد")

        group_paths = await _download_check_images(bot, group_images, user_id)
        if not group_paths:
            logging.warning(f"[CHECK][منضمات] تصویری برای پیوست «{group_title}» دانلود نشد")
            continue

        # ⭐ استشهادیه محلی — فقط وقتی کاربر درخواست اعسار داده است؛
        # طبق دستور کارفرما: نوع پیوست «استشهاديه محلي» + تمام فیلدها = ۱
        is_estesh = bool(group.get("is_esteshahadieh")) or ("استشهاد" in group_title)
        if is_estesh:
            estesh_ok = await _upload_esteshahadieh_attachment(
                page, group_paths, bot, user_id, bill_no)
            if not estesh_ok:
                logging.error("[CHECK][استشهادیه] ثبت/آپلود استشهادیه ناموفق بود")
            else:
                logging.info("[CHECK][استشهادیه] پیوست «استشهاديه محلي» ثبت و آپلود شد")
        else:
            # آپلود با resilient_upload_attachment (فرم سفارشی: نمایندگی/سایر ضمائم)
            upload_result = await resilient_upload_attachment(
                page, group_title, group_paths, bot, user_id,
                prefix="CHECK", form_fill_fn=_fill_extra_attachment_form)
            if not upload_result.get("success"):
                logging.error(
                    f"[CHECK][منضمات] آپلود پیوست اضافی [{group_title}] ناموفق: "
                    f"{upload_result.get('error')}")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CHECK] آپلود پیوست [{group_title}] ناموفق — کاربر {user_id} | "
                    f"کد: {bill_no} | خطا: {(upload_result.get('error') or 'نامشخص')[:200]}")
            else:
                logging.info(f"[CHECK][منضمات] پیوست اضافی [{group_title}] آپلود شد")

        # پاکسازی فایل‌های موقت
        for p in group_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    return True


async def _extract_cost_data(page) -> dict:
    """استخراج و محاسبهٔ هزینه — ⭐ فرمول جدید کارفرما:

    ۱. مبلغ اصلی = «جمع کل هزینه» (td سبزرنگ پایین جدول)
       ⚠️ باگ قبلی: عدد از div خالیِ [ng-model="viewModel.costSum"] خوانده
       می‌شد؛ عدد واقعی text-node داخل td والد است → همیشه costSum=0!
    ۲. جمع مبالغ ۴ ردیف خاص:
       - «هزينه ثبت اطلاعات اشخاص در خدمات قضايي»
       - «هزينه تنظيم دادخواست/شكواييه در خدمات قضايي»
       - «افزودن پيوست در خدمات قضايي»
       - «هزينه خدمات الكترونيك قضايي»
    ۳. جمع ۴ ردیف + ۵۵۰,۰۰۰ ریال
    ۴. مبلغ نهایی = مبلغ اصلی + جمع بالا → رند به بالا (۱۰,۰۰۰ ریال)
    """
    WANTED_LABELS = [
        "هزينه ثبت اطلاعات اشخاص در خدمات قضايي",
        "هزينه ثبت اطلاعات اشخاص در خدمات قضایی",
        "هزينه تنظيم دادخواست",  # پوشش «هزينه تنظيم دادخواست/شكواييه در خدمات قضايي»
        "هزینه تنظیم دادخواست",
        "افزودن پيوست در خدمات قضايي",
        "افزودن پیوست در خدمات قضایی",
        "هزينه خدمات الكترونيك قضايي",
        "هزینه خدمات الکترونیک قضایی",
    ]
    FIXED_EXTRA_RIAL = 550_000  # ⭐ طبق مشخصات جدید (قبلاً اشتباهاً ۵۵ ریال بود)
    ROUND_STEP = 10_000

    cost_data = await page.evaluate('''(wantedLabels) => {
        // ۲) جمع ۴ ردیف خاص از جدول هزینه
        const rows = Array.from(document.querySelectorAll('table.table-bordered tbody tr'));
        let rowSum = 0;
        const matchedLabels = [];
        for (const row of rows) {
            const cells = row.querySelectorAll('td');
            if (cells.length < 3) continue;
            const label = (cells[1].innerText || cells[1].textContent || '').trim();
            const amountText = (cells[2].innerText || cells[2].textContent || '').trim();
            const amount = parseInt(amountText.replace(/[^0-9]/g, '')) || 0;
            const isWanted = wantedLabels.some(w => label.includes(w));
            if (isWanted) {
                rowSum += amount;
                matchedLabels.push(label + ':' + amount);
            }
        }

        // ۱) مبلغ اصلی — td والدِ div جمع کل (عدد text-node داخل td است،
        // نه داخل div!) — با فال‌بک td سبزرنگ
        let costSum = 0;
        const costDiv = document.querySelector('[ng-model="viewModel.costSum"]');
        if (costDiv) {
            const td = costDiv.closest('td');
            const text = td ? (td.innerText || td.textContent || '') : '';
            const nums = text.replace(/,/g, '').match(/[0-9]+/);
            if (nums) costSum = parseInt(nums[0]);
        }
        if (!costSum) {
            const greenTds = Array.from(document.querySelectorAll('table td.color-green'));
            for (const td of greenTds) {
                const t = (td.innerText || '').replace(/,/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(t) && parseInt(t) > 0) {
                    costSum = parseInt(t);
                }
            }
        }

        return {
            costSum: costSum,
            rowSum: rowSum,
            matched_rows_debug: matchedLabels,
        };
    }''', WANTED_LABELS)

    main_amount = cost_data.get("costSum", 0)
    row_sum = cost_data.get("rowSum", 0)
    total = main_amount + row_sum + FIXED_EXTRA_RIAL
    # رند به بالا تا نزدیک‌ترین ۱۰,۰۰۰ ریال
    final_total = ((total + ROUND_STEP - 1) // ROUND_STEP) * ROUND_STEP

    return {
        "costSum": main_amount,
        "rowSum": row_sum,
        "fixedExtra": FIXED_EXTRA_RIAL,
        "total": total,
        "final_total": final_total,
        "matched_rows_debug": cost_data.get("matched_rows_debug", []),
    }


async def _print_check(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    """چاپ PDF دادخواست چک — ⭐ طبق مشخصات کارفرما:

    برای چاپ باید وارد باکس «چاپ اوليه» شد؛ یک صفحهٔ جدید باز می‌شود و آن
    را باید برای کاربر ارسال کرد. خطا و الگوهای چاپ از بخش اظهارنامه
    برداشته شده است (کلیک باکس → expect_page → PDF → بستن صفحهٔ جدید).
    """
    pdf_path = f"check_{bill_no or user_id}_{int(time.time())}.pdf"
    try:
        async def click_print():
            await page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && (
                    el.innerText.includes("چاپ اوليه") || el.innerText.includes("چاپ اولیه")
                ));
                if (t) {
                    const box = t.closest('.box');
                    if (box) box.click();
                }
            }''')

        async with browser_context.expect_page(timeout=25000) as new_page_info:
            await click_print()

        print_page = await new_page_info.value
        await print_page.wait_for_load_state("load", timeout=30000)
        await asyncio.sleep(8)
        # بررسی انقضا روی صفحهٔ چاپ — بدون ریسک ری‌استارت کل تسکِ ثبت‌شده
        try:
            await check_and_handle_expiry(print_page, bot, user_id)
        except Exception:
            pass
        await print_page.pdf(path=pdf_path, format="A4")
        logging.info(f"[CHECK] PDF چاپ اولیه ذخیره شد: {pdf_path}")
        try:
            await print_page.close()
        except Exception:
            pass
        return pdf_path

    except Exception as e:
        logging.error(f"[CHECK] خطا در چاپ PDF: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="check_print", error=e,
                             user_id=user_id, page=page)
        except Exception:
            pass
        return ""
