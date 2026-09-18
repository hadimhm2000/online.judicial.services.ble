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
    _default_fill_other_attachment_form,
    JS_NORMALIZE_FN)


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


class CheckSanaDataError(CheckAbortError):
    """⭐ اصلاحیهٔ کارفرما — خطای داده‌ای ثنا در ثبت دادخواست چک که با ویرایش
    کدملی شخص قابل رفع است (تاریخ تولد ارسالی مربوط به شماره ملی ... اشتباه
    است / اطلاعاتی با این شناسه ملی ثبت نشده است).

    طبق دستور کارفرما: کاربر ۳۰ دقیقه فرصت دارد کدملی را ویرایش کند؛ در غیر
    این صورت پس از ۳۰ دقیقه نصف مبلغ پیش‌پرداخت برای موارد بعدی او از هزینه
    کسر می‌گردد (مدیریت در nid_fix_window + هندلرهای check_handlers).
    """

    def __init__(self, message: str, kind: str = "other", national_id: str = "",
                 role: str = ""):
        super().__init__(message, step="SANA_DATA_ERROR")
        self.kind = kind            # birthdate | not_registered | other
        self.national_id = national_id
        self.role = role


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


def _check_temp_title(request_title: str, success: bool = True) -> str:
    """عنوان پیام ثبت موقت — فقط برای عناوین چک «دادخواست چک»؛ برای سایر
    عناوین (اعسار/خانواده/مطالبه وجه بابت...) عبارت «چک» حذف می‌شود.

    نمونه:
      - «صدور اجرائیه چک» → «ثبت موقت دادخواست چک موفق»
      - «اعسار از پرداخت محکوم به» → «ثبت موقت دادخواست موفق»
    """
    is_cheque_title = request_title in ("صدور اجرائیه چک", "مطالبه وجه چک")
    tail = " موفق" if success else ""
    if is_cheque_title:
        return f"ثبت موقت دادخواست چک{tail}"
    return f"ثبت موقت دادخواست{tail}"


async def _notify_check_partial_failure(bot: Bot, user_id: int, bill_no: str,
                                        request_title: str, issues: list) -> None:
    """⭐ دور ۳ (دستور کارفرما): وقتی ثبت دادخواست به باگ می‌خورد و «هزینه»
    یا «چاپ» به‌طور کامل انجام نمی‌شود:
      ۱. به مدیر اطلاع داده می‌شود که پرونده را دستی بررسی کند و کد رهگیری
         را برای کاربر ارسال کند.
      ۲. به کاربر گفته می‌شود اگر تا ۴۵ دقیقهٔ دیگر نسخهٔ چاپی و فاکتور
         هزینه برایش ارسال نشد، به شمارهٔ پشتیبانی در واتساپ یا بله پیام دهد.
    """
    issues_text = " و ".join(issues) if issues else "اختلال در تکمیل مراحل پایانی"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ [CHECK] ثبت ناقص — کاربر {user_id} | نوع: {request_title} | "
            f"کد رهگیری/بایگانی: {bill_no or 'نامشخص'}\n"
            f"مشکل: {issues_text}\n"
            "👉 لطفاً پرونده را در سامانه *دستی بررسی* کن و کد رهگیری و "
            "فاکتور هزینه را برای کاربر ارسال کن.\n"
            f"⏰ اگر تا ۴۵ دقیقهٔ دیگر ارسال نشود، کاربر به {SUPPORT_PHONE} "
            "پیام خواهد داد.")
    except Exception as e:
        logging.error(f"[CHECK] خطا در ارسال اطلاع ناقص به مدیر: {e}")

    try:
        await bot.send_message(
            user_id,
            f"📋 *کد رهگیری دادخواست شما:* `{bill_no or 'در حال استخراج'}`\n\n"
            f"⚠️ ثبت دادخواست شما انجام شد اما {issues_text}.\n"
            "تیم پشتیبانی مطلع شد و به‌زودی نسخهٔ چاپی و فاکتور هزینه را "
            "برای شما ارسال می‌کند.\n\n"
            f"⏰ اگر تا *۴۵ دقیقهٔ دیگر* چاپ و هزینه برای شما ارسال نشد، "
            f"لطفاً به شمارهٔ *{SUPPORT_PHONE}* در *واتساپ یا بله* پیام دهید.")
    except Exception as e:
        logging.error(f"[CHECK] خطا در ارسال اطلاع ناقص به کاربر: {e}")


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
    # ⭐ عناوین اعسار — نوع دادگاه از کاربر پرسیده شده (حقوقی / صلح)
    court_type = (data.get("check_court_type") or "").strip()
    is_aasar_title = request_title in CHECK_AASAR_TITLES
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

    has_lawyer = any(p.get("person_type") == "وکیل" for p in plaintiffs) or \
                 any(p.get("person_type") == "وکیل" for p in defendants)
    has_legal_plaintiff = any(p.get("person_type") == "شخص حقوقی" for p in plaintiffs)
    has_legal_defendant = any(p.get("person_type") == "شخص حقوقی" for p in defendants)
    is_high_amount = amount > 1_000_000_000  # بیش از ۱ میلیارد ریال
    # ⭐ طلاق×۳ و «الزام به تمکین» مبلغ ندارند و همیشه دادخواست بدوی ثبت می‌شوند
    if request_title in CHECK_NO_AMOUNT_TITLES:
        is_high_amount = True

    # ⭐ عناوین اعسار — مسیر منو بر اساس انتخاب کاربر تعیین می‌شود:
    #   دادگاه حقوقی → ارایه و پیگیری دادخواست → دادخواست بدوی
    #   دادگاه صلح  → دعاوی دادگاههای صلح → دعاوی حقوقی
    # (مبلغ/تامین خواسته/اعسارِ فرعی برای این عناوین حذف شده است)
    if is_aasar_title:
        is_high_amount = (court_type != "صلح")

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
        f"is_high_amount={is_high_amount} branch={branch_code} "
        f"court_type={court_type!r} witnesses={len(witnesses)}"
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

    # ⭐ عناوین اعسار مبلغ ندارند — پیام بدون خط «مبلغ»
    if is_aasar_title:
        await bot.send_message(
            user_id,
            f"🏦 *در حال ثبت دادخواست...*\n"
            f"نوع خواسته: *{request_title}*\n"
            f"🏛 دادگاه: *دادگاه {court_type or 'حقوقی'}*")
    else:
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
        + (f" | دادگاه: {court_type}" if is_aasar_title else "")
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
            elif has_legal_plaintiff or has_legal_defendant:
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

            # ⭐ برای طلاق×۳ و «الزام به تمکین» گزینهٔ مبلغ حذف می‌شود
            # ⭐ عناوین اعسار نیز مبلغ ندارند (گزینهٔ مبلغ حذف شده است)
            if request_title not in CHECK_NO_AMOUNT_TITLES and not is_aasar_title:
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
            if request_title in ("مطالبه وجه چک", "مطالبه وجه بابت..."):
                await sana_page.evaluate('''() => {
                    const rdbJudge = document.querySelector('#rdbJudgePrice');
                    if (rdbJudge && !rdbJudge.checked && !rdbJudge.disabled) rdbJudge.click();
                    const rdbDelay = document.querySelector('#rdbDelayPrice');
                    if (rdbDelay && !rdbDelay.checked && !rdbDelay.disabled) rdbDelay.click();
                }''')
                await asyncio.sleep(1)
            # ۴.۸ ⭐ خواستهٔ فرعی «تامین خواسته» — طبق دستور کارفرما:
            # بعد از خواستهٔ اصلی، دکمهٔ «افزودن» → فیلد «خواسته» → تایپ «تامین»
            # → انتخاب گزینهٔ اول → سپس در فیلد «موضوع خواسته مرتبط» که
            # ظاهر می‌شود، مجدداً گزینهٔ «تامین خواسته» انتخاب می‌شود و در
            # فیلد شرح، متن ثابت درج می‌گردد.
            if tamin_khasteh:
                tamin_ok = await _add_secondary_khasteh(
                    sana_page, bot, user_id,
                    search_term="تامین",
                    target_texts=["تامین خواسته"],
                    fallback_texts=["تامین"],
                    pick_first=True,
                    label="تامین خواسته")
                if not tamin_ok:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⚠️ [CHECK] خواستهٔ فرعی «تامین خواسته» برای کاربر {user_id} "
                        "ثبت نشد — لطفاً در سامانه به‌صورت دستی بررسی/افزودن کنید.")
                else:
                    # ⭐ فیلد «موضوع خواسته مرتبط» (jssPetitionRelief2) —
                    # انتخاب «تامین خواسته» با همان روال دراپ‌داون
                    related_ok = await _select_tamin_related_relief(sana_page, bot, user_id)
                    if not related_ok:
                        await bot.send_message(
                            ADMIN_ID,
                            f"⚠️ [CHECK] فیلد «موضوع خواسته مرتبط» برای تامین خواستهٔ "
                            f"کاربر {user_id} تنظیم نشد — لطفاً در سامانه بررسی کنید.")
                    # ⭐ متن شرح ثابت تامین خواسته در #txtDescription1
                    await _fill_tamin_description(sana_page)

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
            # ⭐ باگ ۵: وضعیت ثبتِ نمایندهٔ اول هر شخص حقوقی ذخیره می‌شود تا
            # تب «نماينده» در صورت ثبت‌نشدن، آن را دوباره ثبت کند.
            plaintiff_first_rep_registered = False
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
                    rep_ok = await _fill_legal_person(sana_page, person, bot, user_id, role="خواهان", idx=idx)
                    if rep_ok:
                        plaintiff_first_rep_registered = True
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

            defendant_first_rep_registered = False
            for idx, person in enumerate(defendants):
                ptype = person.get("person_type", "شخص حقیقی")

                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('#btnAddSection');
                    if (btn && !btn.disabled) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                if ptype == "شخص حقوقی":
                    rep_ok = await _fill_legal_person(sana_page, person, bot, user_id, role="خوانده", idx=idx)
                    if rep_ok:
                        defendant_first_rep_registered = True
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

                for idx, person in enumerate(list(plaintiffs) + list(defendants)):
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
            # ⭐ فلو جدید: همهٔ مدیرعامل/نمایندگان شرکت خواهان و خوانده حقوقی
            # (هرکدام تا ۵ نفر) در این مرحله ثبت می‌شوند — قبلاً این حلقه
            # فقط برای شرکت خواهان اجرا می‌شد و نمایندگان شرکت خوانده اصلاً
            # به سامانه ارسال نمی‌شدند.
            if has_legal_plaintiff or has_legal_defendant:
                clicked = await sana_page.evaluate('''() => {
                    const steps = Array.from(document.querySelectorAll('.step'));
                    const t = steps.find(el => el.innerText && el.innerText.trim() === "نماينده");
                    if (t) { t.click(); return true; }
                    return false;
                }''')
                if not clicked:
                    await safe_click_by_text(sana_page, "نماينده", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                def _collect_legal_reps(persons, first_registered: bool):
                    """جمع‌آوری نمایندگان شخص حقوقی برای تب «نماينده».

                    ⭐ اصلاحیه ۱۴۰۵/۰۶ (باگ ۵ — دعاوی اعسار): قبلاً همیشه
                    «reps[1:]» برگردانده می‌شد — یعنی نمایندهٔ اول کورکورانه
                    اسکیپ می‌شد حتی اگر در مرحلهٔ خواهان/خوانده واقعاً ثبت
                    نشده بود؛ نتیجه: بخش نماینده اسکیپ و کدملی مدیرعامل/
                    نماینده اصلاً وارد نمی‌شد. حالا نمایندهٔ اول فقط وقتی
                    اسکیپ می‌شود که «first_registered» (خروجی _fill_legal_person)
                    True باشد؛ در غیر این صورت همهٔ نمایندگان از اول ثبت می‌شوند.
                    """
                    legal_person = next((p for p in persons if p.get("person_type") == "شخص حقوقی"), {})
                    if not legal_person:
                        return []

                    reps = list(legal_person.get("representatives") or [])

                    if not reps:
                        # ساختار قدیمی (تک‌نماینده در فیلدهای تخت)
                        rep_type_legacy = legal_person.get("representative_type", "")
                        nat_id_legacy = legal_person.get("national_id", "")
                        if not nat_id_legacy:
                            return []
                        reps = [{
                            "representative_type": rep_type_legacy,
                            "national_id": nat_id_legacy,
                        }]
                        # در ساختار قدیمی، نمایندهٔ اول فقط اگر واقعاً در
                        # مرحلهٔ خواهان/خوانده ثبت شده بود، اسکیپ می‌شود.
                        return reps[1:] if first_registered else reps

                    # ساختار جدید (لیست representatives):
                    # اگر نمایندهٔ اول در مرحلهٔ خواهان/خوانده واقعاً ثبت شده
                    # (flat national_id همان reps[0])، از دوم به بعد؛ وگرنه
                    # همهٔ نمایندگان از اول ثبت می‌شوند تا هیچ‌کس جا نماند.
                    flat_nid = (legal_person.get("national_id") or "").strip()
                    if first_registered and reps and \
                       (reps[0].get("national_id") or "").strip() == flat_nid and flat_nid:
                        return reps[1:]
                    return reps

                # ⭐ لیست نمایندگان — فال‌بک به ساختار قدیمی تک‌نماینده
                legal_reps = (_collect_legal_reps(plaintiffs, plaintiff_first_rep_registered) +
                              _collect_legal_reps(defendants, defendant_first_rep_registered))

                for rep_idx, rep in enumerate(legal_reps):
                    rep_type = rep.get("representative_type", "")
                    nat_id = rep.get("national_id", "")
                    if not nat_id:
                        continue

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

                    # ⭐ استعلام ثنا با مدیریت خطا (خطا → یکبار retry →
                    # ارسال متن خطا به کاربر/مدیر) — الگوی سایر اشخاص
                    rep_status = await _query_sana_check(
                        sana_page, "actions.callNationalityCode", bot, user_id,
                        role=f"نماینده {rep_idx + 1}", national_id=nat_id)
                    if rep_status == "failed":
                        raise CheckAbortError(
                            f"استعلام ثنا برای نماینده {rep_idx + 1} "
                            f"(کدملی {nat_id}) ناموفق",
                            step="SANA_QUERY_FAILED")
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
            # ⭐ فلو جدید (طبق دستور کارفرما):
            #   ۱. کلیک «ثبت موقت»
            #   ۲. انتظار برای پاپ‌آپ موفقیت («...ثبت شد .») → کلیک «بستن»
            #   ۳. خطای دیگر → بستن و تلاش مجدد ثبت موقت؛ اگر دوباره خطا
            #      آمد → اطلاع به کاربر/مدیر و توقف
            #   ۴. کدرهگیری از #txtPetitionNo (فال‌بک #txtBillNo)
            #   ۵. کلیک «بازگشت به فهرست» (#btnGotoMainPage)
            bill_no = await _click_save_temp_check(
                sana_page, bot, user_id, max_retries=3)

            # ⭐ اعتبارسنجی bill_no — قبلاً با کد خالی به منضمات/هزینه/چاپ
            # ادامه داده می‌شد و همهٔ مراحل بعدی روی صفحهٔ نامعتبر fail می‌شد
            # («Option 'منضمات' not found» → ری‌استارت بی‌پایان).
            # پیام‌های کاربر/مدیر داخل تابع ارسال شده‌اند.
            if not bill_no:
                raise CheckAbortError(
                    f"{_check_temp_title(request_title, success=False)} پس از "
                    "تلاش‌های مجدد موفق نشد (کد رهگیری قابل استخراج نبود)",
                    step="TEMP_SAVE_NO_BILL")

            # ⭐ اصلاحیه: عنوان پیام مدیر — فقط برای عناوین چک «دادخواست چک»؛
            # برای اعسار/خانواده/«مطالبه وجه بابت...» عبارت «چک» حذف می‌شود و
            # پیام «ثبت موقت دادخواست موفق» ارسال می‌گردد (قبلاً برای پروندهٔ
            # «اعسار از پرداخت محکوم به» هم «ثبت موقت دادخواست چک موفق» ارسال
            # می‌شد که غلط بود).
            await log_event("ثبت موقت", "دادخواست", str(user_id), user_id,
                            tracking_code=bill_no, note=f"{request_title} | مبلغ: {amount:,}")
            await bot.send_message(
                ADMIN_ID,
                f"📋 *{_check_temp_title(request_title, success=True)}*\n"
                f"👤 کاربر: {user_id}\n"
                f"🔢 کد بایگانی: `{bill_no}`\n"
                f"📝 نوع: {request_title}")

            # بازگشت به فهرست
            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۲. مرحله «منضمات» — آپلود تصاویر چک (برای هر فقره) ────
            # ⭐ حتی بدون فقره چک/پیوست اضافی، اگر وکیل داریم برای ثبت
            # وکالت‌نامه الکترونیک وارد منضمات می‌شویم.
            if cheque_items or attachment_groups or has_lawyer:
                try:
                    attachments_ok, contract_fix_lawyer = await _process_check_attachments(
                        sana_page,
                        request_title=request_title,
                        cheque_items=cheque_items,
                        attachment_groups=attachment_groups,
                        bot=bot,
                        user_id=user_id,
                        bill_no=bill_no,
                        plaintiffs=plaintiffs,
                        defendants=defendants)
                except CheckAbortError:
                    raise  # قطع‌های آگاهانه همان‌طور پاس داده می‌شوند
                except Exception as att_err:
                    # ⭐ خطای غیرمنتظره در منضمات (مثل evaluate خراب) نباید
                    # باعث retry کل فرآیند شود — پرونده از قبل ثبت موقت شده
                    # و کدرهگیری گرفته؛ تکرار یعنی ثبتِ تکراری! پیام به
                    # مدیر و توقف قطعی.
                    logging.error(
                        f"[CHECK] خطای غیرمنتظره در منضمات user={user_id}: {att_err}",
                        exc_info=True)
                    await bot.send_message(
                        ADMIN_ID,
                        f"❌ [CHECK] خطای غیرمنتظره در منضمات کاربر {user_id} | "
                        f"کد بایگانی: `{bill_no}` | خطا: {str(att_err)[:300]}\n"
                        "تصاویر/پیوست‌ها را در سامانه دستی تکمیل کنید.")
                    raise CheckAbortError(
                        f"خطای غیرمنتظره در منضمات: {att_err}",
                        step="ATTACHMENTS_UNEXPECTED_ERROR")

                if not attachments_ok:
                    # پیام‌های مربوطه (کدرهگیری اشتباه / قطعی سامانه) داخل
                    # _process_check_attachments ارسال شده‌اند — فقط توقف:
                    raise CheckAbortError(
                        "مرحلهٔ منضمات چک کامل نشد — پیام مربوطه برای کاربر ارسال شد",
                        step="ATTACHMENTS_ABORTED")

                # ══════════════════════════════════════════════════════════
                # ⭐ اصلاحیه ۱۴۰۵/۰۶ — شماره قرارداد وکالت نامعتبر بود:
                # پس از انجام سایر پیوست‌ها، پنجرهٔ ۴۵ دقیقه‌ای ارسال کد
                # قرارداد جدید باز می‌شود و آماده‌سازی/هزینه/چاپ تا پس از
                # ثبت قرارداد جدید (تسک CONTRACT_FIX_SUBMIT) به تعویق می‌افتد.
                # ══════════════════════════════════════════════════════════
                if attachments_ok == "contract_fix":
                    try:
                        import nid_fix_window
                        cf_lawyer = contract_fix_lawyer or {}
                        cf_task_data = dict(data)
                        # مسیر منو برای استعلام کدرهگیری در سناریوی قرارداد جدید
                        cf_task_data["_contract_fix_menu_path"] = list(sign_menu_path)
                        nid_fix_window.start_contract_fix(
                            user_id, flow="check", task_data=cf_task_data,
                            bill_no=bill_no or "",
                            old_contract=cf_lawyer.get("contract_number", ""),
                            stamp_amount_value=int(cf_lawyer.get("stamp_amount_value", 0) or 0),
                            error_text="شماره قرارداد الکترونیک وکالت معتبر نمی باشد")
                        from contract_fix_handlers import contract_fix_inline_kb
                        await bot.send_message(
                            user_id,
                            f"❌ *شماره قرارداد اشتباه می باشد.*\n\n"
                            f"شماره قرارداد وکالت «{cf_lawyer.get('contract_number', '')}» "
                            f"در سامانه معتبر نیست و ثبت نشد.\n"
                            f"🔢 کد بایگانی دادخواست: `{bill_no}`\n\n"
                            f"{nid_fix_window.contract_fix_deadline_text()}\n\n"
                            f"پس از ارسال کد قرارداد جدید، ثبت قرارداد و ادامهٔ "
                            f"آماده‌سازی، هزینه و چاپ به‌صورت خودکار انجام می‌شود.",
                            parse_mode="Markdown",
                            reply_markup=contract_fix_inline_kb(user_id))
                        await bot.send_message(
                            ADMIN_ID,
                            f"⚠️ [CHECK] شماره قرارداد وکالت «{cf_lawyer.get('contract_number', '')}» "
                            f"برای کاربر {user_id} معتبر نبود | کد بایگانی: {bill_no}\n"
                            f"پنجرهٔ ۴۵ دقیقه‌ای کد قرارداد جدید باز شد.")
                    except Exception as cf_err:
                        logging.error(f"[CHECK] خطا در شروع پنجرهٔ کد قرارداد جدید: {cf_err}")
                    raise CheckAbortError(
                        "ثبت قرارداد وکالت ناموفق (شماره قرارداد نامعتبر) — "
                        "ادامه پس از دریافت کد قرارداد جدید",
                        step="CONTRACT_FIX_PENDING")

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
            # ⭐ دور ۳ — جمع‌آوری مشکلات هزینه برای اطلاع‌رسانی «ثبت ناقص»
            _cost_issues = []
            if len(_matched) != 4:
                _cost_issues.append(
                    f"هزینهٔ سامانه کامل استخراج نشد ({len(_matched)} ردیف از ۴)"
                )
            if not int(cost_data.get("costSum") or 0):
                _cost_issues.append("مبلغ هزینهٔ سامانه (costSum) خوانده نشد")
            if _cost_issues:
                # اگر ۴ ردیف هزینهٔ خاص پیدا نشد، یا ساختار جدول عوض شده یا
                # یکی از عناوین فرق کرده — باید فوراً به مدیر اطلاع داد.
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [CHECK] هشدار محاسبهٔ هزینه: انتظار ۴ ردیف هزینهٔ خاص می‌رفت، "
                    f"{len(_matched)} ردیف پیدا شد ({_matched}). costSum={cost_data.get('costSum')}. "
                    f"لطفاً مبلغ نهایی ({final_total:,} ریال) را دستی با سامانه تطبیق دهید. کاربر: {user_id}"
                )

            # ── گرفتن شناسه پرداخت از بخش هزینه (فقط ذخیره در شیت + پیام به مدیر) ──
            # ⭐ رفع باگ: amount باید «هزینهٔ واقعی سامانه» (costSum، پیش از
            # اعمال فرمول سود دفتر) باشد، نه final_total که مبلغ نهایی
            # دریافتی از کاربر است — وگرنه در پنل «هزینه سامانه» با «هزینه»
            # برابر می‌شود و سود همیشه صفر نمایش داده می‌شود.
            from payment_id_capture import capture_and_report_payment_ids
            await capture_and_report_payment_ids(
                sana_page, bot, user_id,
                service_name="دادخواست چک",
                tracking_code=bill_no,
                amount=cost_data.get("costSum", 0),
                exclude_values=[bill_no],
                log_prefix="CHECK")

            # ── ۱۵. چاپ PDF ─────────────────────────────────────────────
            # ⭐ طبق مشخصات: چاپ از باکس «چاپ اوليه» انجام می‌شود، صفحهٔ جدید
            # باز می‌شود و PDF آن برای کاربر ارسال می‌گردد (الگوی اظهارنامه).
            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            pdf_path = await _print_check(sana_page, browser_context, bill_no, bot, user_id)

            # ⭐ دور ۳ (دستور کارفرما): اگر ثبت به باگ خورده و هزینه/چاپ کامل
            # انجام نشده باشد — به مدیر اطلاع داده می‌شود که پرونده را دستی
            # بررسی کند و کد رهگیری را برای کاربر بفرستد؛ و به کاربر گفته
            # می‌شود اگر تا ۴۵ دقیقهٔ دیگر چاپ و هزینه ارسال نشد به شمارهٔ
            # پشتیبانی در واتساپ/بله پیام دهد.
            _pdf_ok = bool(pdf_path and os.path.exists(pdf_path))
            _partial_issues = list(_cost_issues)
            if not _pdf_ok:
                _partial_issues.append("چاپ نسخهٔ PDF ناموفق بود")
            if _partial_issues:
                await _notify_check_partial_failure(
                    bot, user_id, bill_no, request_title, _partial_issues)

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
                # ⭐ دور ۳: پیام قدیمی «برای دریافت نسخهٔ چاپی با مدیریت تماس
                # بگیرید» حذف شد — پیام کامل‌تر «ثبت ناقص» (کد رهگیری + مهلت
                # ۴۵ دقیقه + شمارهٔ پشتیبانی واتساپ/بله) بالاتر در
                # _notify_check_partial_failure برای کاربر ارسال شده است.
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

        except CheckSanaDataError as sana_err:
            # ⭐ اصلاحیهٔ کارفرما: خطای داده‌ای ثنا در دادخواست چک («تاریخ تولد
            # ارسالی مربوط به شماره ملی ... اشتباه است» / شناسه ملی ثبت نشده)
            # — پنجرهٔ ۳۰ دقیقه‌ای ویرایش کدملی + جریمهٔ نصف پیش‌پرداخت برای
            # موارد بعدی. پنجره در persistence ذخیره می‌شود تا حتی پس از
            # کرش/قطعی ربات برای هر درخواست بعدیِ کاربر محاسبه گردد.
            # (فقط برای ثبت تکی؛ ردیف‌های دسته‌جمعی همان رفتار قبلی را دارند.)
            logging.error(
                f"[CHECK] خطای داده‌ای ثنا user={user_id} (kind={sana_err.kind}): {sana_err}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [CHECK] خطای داده‌ای ثنا کاربر {user_id} "
                    f"(kind={sana_err.kind}, nid={sana_err.national_id}, "
                    f"role={sana_err.role}): {str(sana_err)[:200]}")
            except Exception:
                pass

            if is_bulk_check and batch_tracking_code:
                # ردیف دسته‌جمعی — رفتار قبلی: علامت‌گذاری ردیف و ادامهٔ بچ
                try:
                    from bulk_submissions import BULK_TASKS, mark_bulk_item_done
                    if batch_tracking_code in BULK_TASKS:
                        BULK_TASKS[batch_tracking_code].setdefault("failures", []).append({
                            "row_index": bulk_row_index,
                            "tracking_code": tracking_no,
                            "title": f"دادخواست چک — {request_title}",
                            "error": f"خطای داده‌ای ثنا: {str(sana_err)[:150]}",
                        })
                    await mark_bulk_item_done(bot, user_id, batch_tracking_code)
                except Exception as log_err:
                    logging.error(f"[CHECK] خطا در mark_bulk_item_done: {log_err}")
                return

            task_data_snapshot = dict(data)
            task_data_snapshot["_sana_error_national_id"] = sana_err.national_id
            task_data_snapshot["_sana_error_role"] = sana_err.role
            task_data_snapshot["_sana_error_kind"] = sana_err.kind

            try:
                import nid_fix_window
                _win = nid_fix_window.start_window(
                    user_id, flow=nid_fix_window.FLOW_CHECK,
                    task_data=task_data_snapshot, error_text=str(sana_err),
                    national_id=sana_err.national_id)
            except Exception as _win_err:
                logging.error(f"[CHECK] خطا در شروع پنجرهٔ ویرایش کدملی: {_win_err}")
                _win = None

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            chk_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ ویرایش کدملی",
                    callback_data=f"chk_nid_fix:{user_id}")],
                [InlineKeyboardButton(
                    text="🗑 حذف درخواست",
                    callback_data=f"chk_nid_cancel:{user_id}")],
            ])
            await bot.send_message(
                user_id,
                f"⚠️ *خطای استعلام ثنا:*\n\n«{str(sana_err)[:250]}»\n\n"
                f"❌ کدملی ({sana_err.role or 'شخص'}) اشتباه می باشد.\n\n"
                f"⏰ شما *۳۰ دقیقه* فرصت دارید کدملی شخص را ویرایش کنید؛ در غیر این "
                f"صورت پس از ۳۰ دقیقه، *نصف مبلغ پیش‌پرداخت* برای موارد بعدی شما "
                f"از هزینه کسر می‌گردد.\n"
                f"✅ پس از ویرایش، ثبت با همان اطلاعات سیو شده ادامه می‌یابد.",
                reply_markup=chk_kb)
            try:
                from panel_sync import upsert_case_to_panel
                await upsert_case_to_panel(
                    bale_user_id=user_id, full_name=str(user_id),
                    service_type="CHECK", status="FAILED",
                    tracking_code=tracking_no or None,
                    document_category=f"دادخواست چک — {request_title}{_doc_category_suffix}",
                    error_details=f"خطای داده‌ای ثنا: {str(sana_err)[:200]}",
                    error_step="SANA_DATA_ERROR")
            except Exception as panel_err:
                logging.warning(f"[CHECK] خطا در ثبت شکست در پنل: {panel_err!r}")
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
                # ⭐ ریلود با قاعدهٔ جدید: ۱۰ ثانیه صبر + بررسی نمایش محتوا
                await _reload_page_with_settle(sana_page, prefix="CHECK")
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


async def _close_sweet_popup(page) -> None:
    """بستن پاپ‌آپ sweet-alert (دکمهٔ confirm/بستن) اگر باز باشد."""
    try:
        await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) {
                const btn = popup.querySelector('button.confirm') ||
                            popup.querySelector('button.cancel');
                if (btn) btn.click();
            }
        }''')
        await asyncio.sleep(1.5)
    except Exception:
        pass


async def _read_save_popup(page) -> dict | None:
    """خواندن وضعیت پاپ‌آپ ثبت موقت.

    خروجی:
      None                — پاپ‌آپی نیست
      {"success": True}   — پاپ‌آپ موفقیت (آیکون success یا متن «ثبت شد»)
      {"text": "..."}     — پاپ‌آپ خطا/هشدار (متن h2+p)
    """
    try:
        return await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const visible = window.getComputedStyle(popup).display !== 'none';
            if (!visible) return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            const text = ((h2 ? h2.innerText : '') + ' ' + (p ? p.innerText : '')).trim();
            const successIcon = popup.querySelector('.sa-icon.sa-success');
            const hasSuccess = successIcon &&
                window.getComputedStyle(successIcon).display !== 'none';
            if (hasSuccess) return {success: true, text: text};
            // پاپ‌آپ موفقیت گاهی فقط متن «ثبت شد» دارد (مثل
            // «دادخواست بدوی با موفقیت ثبت شد .»)
            if (text && text.includes("ثبت شد") && !text.includes("خطا")) {
                return {success: true, text: text};
            }
            return {success: false, text: text};
        }''')
    except Exception:
        return None


async def _click_save_temp_check(page, bot: Bot, user_id: int,
                                 max_retries: int = 3) -> str:
    """کلیک «ثبت موقت» دادخواست چک — طبق دستور کارفرما (عیناً):

      ۱. کلیک ثبت موقت
      ۲. انتظار برای پاپ‌آپ موفقیت («دادخواست بدوی با موفقیت ثبت شد .»)
         و کلیک روی دکمهٔ «بستن»
      ۳. اگر هر خطای دیگری ظاهر شد → بستن و یکبار دیگر تلاش؛ اگر دوباره
         خطا آمد → اطلاع به کاربر/مدیر و توقف (خروجی "")
      ۴. کدرهگیری (شماره دادخواست) از #txtPetitionNo (فال‌بک #txtBillNo)
      ۵. کلیک «بازگشت به فهرست» (#btnGotoMainPage)

    خروجی: کد رهگیری (رشتهٔ خالی یعنی شکست — پیام‌ها ارسال شده‌اند).

    ⚠️ باگ قبلی (TEMP_SAVE_NO_BILL): بعد از کلیک ثبت موقت فقط ۸ ثانیه صبر
    می‌شد و #txtBillNo خوانده می‌شد — در فلو جدید سامانه بعد از ثبت موقت،
    پاپ‌آپ موفقیت نمایش داده می‌شود و کدرهگیری در #txtPetitionNo است؛
    به همین دلیل قبلاً bill_no همیشه خالی می‌ماند و فرآیند به‌اشتباه
    قطع می‌شد.
    """
    last_error = ""
    for attempt in range(max_retries):
        # بررسی انقضای نشست قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(3)
            continue

        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnSave') ||
                        Array.from(document.querySelectorAll('button')).find(
                            b => b.innerText && b.innerText.includes("ثبت موقت"));
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            try:
                await safe_click_by_text(page, "ثبت موقت", bot, user_id)
            except NavigationResetError:
                raise  # هنوز ثبت موقت انجام نشده — ری‌استارت امن است
            except Exception:
                pass

        # صبر اولیه + لودینگ افقی (طبق دستور کارفرما: اگر لودینگ هنوز
        # نمایان است، منتظر می‌مانیم — این کار را
        # wait_for_horizontal_loading_bar انجام می‌دهد)
        await asyncio.sleep(5)
        loading_result = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if loading_result == "SESSION_EXPIRED":
            # نشست تمدید شده — تلاش مجدد
            continue
        elif loading_result:
            # خطای واقعی سامانه → بستن و تلاش مجدد ثبت موقت
            last_error = str(loading_result)
            logging.warning(
                f"[CHECK] خطای ثبت موقت (تلاش {attempt + 1}): {last_error[:200]}")
            await _close_sweet_popup(page)
            await asyncio.sleep(3)
            continue

        # بررسی انقضای نشست بعد از ثبت
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(3)
            continue

        # بررسی پاپ‌آپ موفقیت/خطا
        popup = await _read_save_popup(page)
        if popup and popup.get("success"):
            # ✅ موفقیت → کلیک «بستن»
            logging.info(f"[CHECK] پاپ‌آپ موفقیت ثبت موقت: {popup.get('text', '')[:120]}")
            await _close_sweet_popup(page)
            await asyncio.sleep(2)

            # ⭐ استخراج کدرهگیری از #txtPetitionNo (فال‌بک #txtBillNo)
            bill_no = ""
            for _try in range(6):
                bill_no = await page.evaluate('''() => {
                    const inp = document.querySelector('#txtPetitionNo') ||
                                document.querySelector('#txtBillNo');
                    if (inp) return inp.value || "";
                    const sp = document.querySelector('[ng-model*="BillNo"]');
                    if (sp) return sp.innerText || sp.textContent || "";
                    return "";
                }''') or ""
                bill_no = bill_no.strip()
                if bill_no:
                    break
                await asyncio.sleep(3)

            logging.info(f"[CHECK] petition_no={bill_no}")

            if bill_no:
                # ⭐ کلیک «بازگشت به فهرست» (#btnGotoMainPage)
                await _click_goto_main(page, bot, user_id)
                return bill_no

            # ثبت موفق بود ولی کدرهگیری استخراج نشد — تلاش مجدد ثبتِ
            # موقت خطر ثبت تکراری دارد → قطع با اطلاع
            last_error = ("ثبت موقت با موفقیت انجام شد ولی کد رهگیری "
                          "(شماره دادخواست) از فیلد قابل استخراج نبود.")
            break

        if popup and popup.get("text"):
            # ⭐ خطا → بستن و تلاش مجدد؛ اگر دوباره خطا آمد → اطلاع
            last_error = str(popup.get("text"))
            logging.warning(
                f"[CHECK] پاپ‌آپ خطای ثبت موقت (تلاش {attempt + 1}): {last_error[:200]}")
            await _close_sweet_popup(page)
            await asyncio.sleep(3)
            continue

        # هیچ پاپ‌آپی نیست — کمی صبر و تلاش مجدد
        logging.warning(f"[CHECK] پاسخی برای ثبت موقت نیامد (تلاش {attempt + 1})")
        await asyncio.sleep(5)

    # ═══ همهٔ تلاش‌ها شکست خورد — پیام به کاربر و مدیر ═══
    if not last_error:
        last_error = "سامانه پس از چند تلاش، پاسخ قطعی برای «ثبت موقت» نداد."
    user_msg = (
        "⚠️ *خطا در ثبت موقت دادخواست:*\n\n"
        "«" + last_error[:300] + "»\n\n"
        "لطفا 30 دقیقه دیگر مجددا مورد خود را ارسال بفرمائید.\n"
        "باتشکر"
    )
    try:
        await bot.send_message(user_id, user_msg)
    except Exception:
        pass
    try:
        await bot.send_message(
            ADMIN_ID,
            f"❌ [CHECK] قطع فرآیند ثبت موقت user={user_id}: {last_error[:400]}")
    except Exception:
        pass
    logging.error(f"[CHECK] قطع فرآیند user={user_id} (TEMP_SAVE): {last_error[:300]}")
    return ""


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



# ⭐ عناوین جدید خانواده — ثبت عین «مطالبه وجه» طبق دستور کارفرما
CHECK_FAMILY_TITLES = ("دادخواست طلاق توافقی", "دادخواست طلاق به درخواست زوجه",
                       "دادخواست طلاق به درخواست زوج", "دادخواست نفقه",
                       "دادخواست الزام به تمکین", "دادخواست مهریه")
# طلاق×۳ و «الزام به تمکین»: بدون مبلغ و همیشه دادخواست بدوی
CHECK_NO_AMOUNT_TITLES = ("دادخواست طلاق توافقی", "دادخواست طلاق به درخواست زوجه",
                          "دادخواست طلاق به درخواست زوج", "دادخواست الزام به تمکین")
# ⭐ عناوین اعسار — در فیلد «خواسته» عبارت «اعسار» تایپ و گزینهٔ دقیقِ همان
# عنوان انتخاب می‌شود؛ مبلغ/تامین/اعسار فرعی ندارند و مسیر منو بر اساس
# انتخاب کاربر (دادگاه حقوقی / صلح) تعیین می‌گردد.
CHECK_AASAR_TITLES = ("اعسار از پرداخت هزینه دادرسی",
                      "اعسار از پرداخت محکوم به",
                      "اعسار از پرداخت مهریه")
# دراپ‌داون سامانه (getReliefFromJSSPetitionType) برای جستجوی «اعسار»:
#   «اعسار از پرداخت محکوم به» / «اعسار از پرداخت مهریه» /
#   «اعسار از پرداخت هزینه دادرسی»
_AASAR_SEARCH = {t: "اعسار" for t in CHECK_AASAR_TITLES}
_AASAR_TARGET = {
    "اعسار از پرداخت هزینه دادرسی": ["اعسار از پرداخت هزینه دادرسی"],
    "اعسار از پرداخت محکوم به": ["اعسار از پرداخت محکوم به"],
    "اعسار از پرداخت مهریه": ["اعسار از پرداخت مهریه"],
}
_AASAR_FALLBACK = {t: ["اعسار"] for t in CHECK_AASAR_TITLES}
_FAMILY_SEARCH = {"دادخواست طلاق توافقی": "طلاق", "دادخواست طلاق به درخواست زوجه": "طلاق",
                  "دادخواست طلاق به درخواست زوج": "طلاق", "دادخواست نفقه": "نفقه",
                  "دادخواست الزام به تمکین": "تمکین", "دادخواست مهریه": "مهریه"}
# ⭐ اصلاحیه (کارفرما — دور ۳): گزینهٔ درست خواستهٔ مهریه «مطالبه مهریه»
# است؛ قبلاً target «پرداخت مهریه» بود و چون تطبیق «includes» بود، اولین
# ردیف حاوی «مهریه» (مثلاً «اثبات رجوع از بذل مهریه») به‌اشتباه انتخاب
# می‌شد و سامانه سند طلاق می‌خواست. حالا target دقیق + تطبیق exact-first.
_FAMILY_TARGET = {"دادخواست طلاق توافقی": ["طلاق توافقی"],
                  "دادخواست طلاق به درخواست زوجه": ["طلاق به درخواست زوجه"],
                  "دادخواست طلاق به درخواست زوج": ["طلاق به درخواست زوج"],
                  "دادخواست نفقه": ["مطالبه نفقه", "پرداخت نفقه", "نفقه"],
                  "دادخواست الزام به تمکین": ["الزام به تمکین", "تمکین"],
                  "دادخواست مهریه": ["مطالبه مهریه"]}
_FAMILY_FALLBACK = {"دادخواست طلاق توافقی": ["طلاق"], "دادخواست طلاق به درخواست زوجه": ["زوجه"],
                    "دادخواست طلاق به درخواست زوج": ["زوج"], "دادخواست نفقه": ["نفقه"],
                    "دادخواست الزام به تمکین": ["تمکین"], "دادخواست مهریه": ["مهریه"]}




async def _reload_page_with_settle(page, prefix: str = "CHECK") -> bool:
    """
    ریلود صفحه طبق قاعدٔ جدید کارفرما:
      ۱. ریلود صفحه
      ۲. حتماً ۱۰ ثانیه صبر
      ۳. بررسی اینکه صفحه واقعاً چیزی نمایش می‌دهد (منو/محتوای بدنه)
      ۴. اگر چیزی نمایش داده نشد → یک بار دیگر ریلود + ۱۰ ثانیه صبر
    قبلاً ریلود با ۵–۶ ثانیه صبر انجام می‌شد و گاهی صفحه هنوز خالی بود.
    """
    for reload_round in range(1, 3):
        try:
            await page.reload()
        except Exception as e:
            logging.warning(f"[{prefix}] خطا در ریلود صفحه (دور {reload_round}): {e}")
        await asyncio.sleep(10)
        try:
            loaded = await page.evaluate("""() => {
                const menu = document.querySelector('a.list-group-item, li.list-group-item');
                const bodyText = document.body ? (document.body.innerText || "").trim() : "";
                return !!menu || bodyText.length > 50;
            }""")
        except Exception:
            loaded = False
        if loaded:
            logging.info(f"[{prefix}] صفحه پس از ریلود محتوا نمایش داد (دور {reload_round}).")
            return True
        logging.warning(
            f"[{prefix}] پس از ریلود هنوز چیزی نمایش داده نشد (دور {reload_round}/2) — ریلود مجدد...")
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
    is_family = request_title in CHECK_FAMILY_TITLES
    is_aasar = request_title in CHECK_AASAR_TITLES

    if search_term is None:
        # ⭐ طبق دستور کارفرما: برای «مطالبه وجه بابت...» عبارت «وجه» تایپ می‌شود
        if is_aasar:
            # ⭐ عناوین اعسار — در فیلد «خواسته» عبارت «اعسار» تایپ و گزینهٔ
            # دقیقِ همان عنوان (اعسار از پرداخت محکوم به/مهریه/هزینه دادرسی)
            # از دراپ‌داون سامانه انتخاب می‌شود.
            search_term = _AASAR_SEARCH.get(request_title, "اعسار")
        elif is_badane:
            search_term = "وجه"
        elif is_family:
            search_term = _FAMILY_SEARCH.get(request_title, "خواسته")
        else:
            search_term = "چک"
    if target_texts is None:
        if is_aasar:
            target_texts = _AASAR_TARGET.get(request_title, [])
        elif is_badane:
            target_texts = ["مطالبه وجه بابت"]
        elif is_family:
            target_texts = _FAMILY_TARGET.get(request_title, [])
        elif is_ejra:
            target_texts = ["درخواست صدور اجرائیه نسبت به چک بلامحل"]
        else:
            target_texts = ["مطالبه وجه چک"]
    if fallback_texts is None:
        if is_aasar:
            fallback_texts = _AASAR_FALLBACK.get(request_title, [])
        elif is_badane:
            fallback_texts = ["وجه بابت"]
        elif is_family:
            fallback_texts = _FAMILY_FALLBACK.get(request_title, [])
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
        #    ⚠️ باگ قبلی: page.evaluate(js, targets, fallbacks, pickFirst, searchTerm)
        #    با ۴ آرگومان جدا صدا زده می‌شد؛ Playwright فقط «یک» آرگومان اضافه
        #    می‌پذیرد → TypeError: Page.evaluate() takes from 2 to 3 positional
        #    arguments but 6 were given → هیچ‌گاه روی گزینهٔ خواسته کلیک نمی‌شد.
        #    اصلاح: همهٔ پارامترها در «یک دیکشنری» پاس می‌شوند.
        #    منطق انتخاب (طبق مشخصات کارفرما — اولویت‌دار):
        #      ۱) متن هدف دقیق (targets) ۲) متن جایگزین (fallbacks)
        #      ۳) pickFirst → اولین گزینهٔ منطبق با عبارت جستجو
        picked = await page.evaluate('''(args) => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            const targets = (args.targets || []).map(norm);
            const fallbacks = (args.fallbacks || []).map(norm);
            const pickFirst = !!args.pickFirst;
            const searchTerm = norm(args.searchTerm);
            const items = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
            // ⭐ دور ۳ — تطبیق exact-first با اولویت targetها: برای هر متن هدف
            // ابتدا تساوی کامل، سپس «شروع‌شونده با»، در آخر «شامل». قبلاً فقط
            // «includes» بود و برای مهریه اولین ردیف حاوی مهریه (مثل «اثبات
            // رجوع از بذل مهریه») به‌اشتباه انتخاب می‌شد.
            const normText = (el) => norm(el.innerText);
            const findBy = (t, mode) => items.find(el => {
                const s = normText(el);
                if (mode === 'exact') return s === t;
                if (mode === 'starts') return s.startsWith(t);
                return s.includes(t);
            });
            const matchByPriority = (t) => findBy(t, 'exact') || findBy(t, 'starts') || findBy(t, 'includes');
            let target = null;
            for (const t of targets) {
                if (!t) continue;
                target = matchByPriority(t);
                if (target) break;
            }
            if (!target) {
                for (const t of fallbacks) {
                    if (!t) continue;
                    target = matchByPriority(t);
                    if (target) break;
                }
            }
            if (!target && pickFirst) {
                // گزینهٔ اول — ترجیحاً منطبق با عبارت جستجو
                target = items.find(el => normText(el).includes(searchTerm)) || items[0] || null;
            }
            if (target) {
                const row = target.closest('a, .ui-select-choices-row, li') || target;
                row.click();
                return normText(target);
            }
            return null;
        }''', {"targets": target_texts or [], "fallbacks": fallback_texts or [],
                "pickFirst": bool(pick_first), "searchTerm": search_term or ""})

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


async def _select_tamin_related_relief(page, bot: Bot, user_id: int) -> bool:
    """انتخاب «تامین خواسته» در فیلد «موضوع خواسته مرتبط» (jssPetitionRelief2).

    ⭐ طبق دستور کارفرما: بعد از افزودن خواستهٔ فرعی «تامین خواسته»، فیلد
    «موضوع خواسته مرتبط» ظاهر می‌شود و باید مجدداً (با همان روال دراپ‌داون)
    گزینهٔ «تامین خواسته» در آن انتخاب شود.

    ساختار فیلد (از HTML سامانه):
      - div.ui-select-match با placeholder="موضوع خواسته مرتبط"
      - دکمهٔ ui-select-toggle
      - input.ui-select-search با placeholder="موضوع خواسته مرتبط"
      - گزینه‌ها از actions.getReliefFromJSSPetitionType(searchValue)
    """
    for attempt in range(3):
        await wait_for_angular_idle(page)

        # ۱) کلیک روی toggle دراپ‌داون «موضوع خواسته مرتبط» (آخرین نمونه)
        clicked = await page.evaluate('''() => {
            let btn = null;
            const matches = Array.from(
                document.querySelectorAll('.ui-select-match[placeholder="موضوع خواسته مرتبط"]')
            ).filter(m => m.offsetParent !== null);
            const match = matches.length > 0 ? matches[matches.length - 1] : null;
            if (match) btn = match.querySelector('button.ui-select-toggle');
            if (!btn) {
                const spans = Array.from(document.querySelectorAll('.ui-select-placeholder'))
                    .filter(s => (s.innerText || '').trim() === 'موضوع خواسته مرتبط');
                const sp = spans.length > 0 ? spans[spans.length - 1] : null;
                if (sp) btn = sp.closest('button');
            }
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            logging.warning(
                f"[CHECK] toggle «موضوع خواسته مرتبط» کلیک نشد (تلاش {attempt + 1}/3)")
            await asyncio.sleep(2)
            continue

        await asyncio.sleep(1.5)

        # ۲) تایپ «تامین» در فیلد جستجویِ باز
        try:
            search = page.locator('.ui-select-search:visible').last
            await search.wait_for(state="visible", timeout=6000)
            await search.fill("")
            await search.type("تامین", delay=120)
        except PlaywrightTimeoutError:
            logging.warning(
                f"[CHECK] فیلد جستجوی «موضوع خواسته مرتبط» ظاهر نشد (تلاش {attempt + 1}/3)")
            await asyncio.sleep(2)
            continue
        except Exception as e:
            logging.warning(f"[CHECK] خطا در تایپ «تامین» در فیلد مرتبط: {e}")
            await asyncio.sleep(2)
            continue

        # ۳) ۵ ثانیه صبر (همان روال دراپ‌داون خواسته)
        await asyncio.sleep(5)

        # ۴) انتخاب گزینهٔ «تامین خواسته» (اولین گزینهٔ منطبق)
        picked = await page.evaluate('''() => {
            const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            const items = Array.from(
                document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]')
            ).filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
            let target = items.find(el => norm(el.innerText).includes("تامین خواسته"));
            if (!target) target = items.find(el => norm(el.innerText).includes("تامین"));
            if (!target) target = items[0] || null;
            if (target) {
                const row = target.closest('a, .ui-select-choices-row, li') || target;
                row.click();
                return norm(target.innerText);
            }
            return null;
        }''')

        if picked:
            logging.info(f"[CHECK] گزینهٔ «موضوع خواسته مرتبط» انتخاب شد: {picked}")
            await asyncio.sleep(3)
            return True

        logging.warning(
            f"[CHECK] گزینهٔ فیلد «موضوع خواسته مرتبط» پیدا نشد (تلاش {attempt + 1}/3)")
        await asyncio.sleep(2)

    return False


async def _fill_tamin_description(page) -> None:
    """درج متن ثابت شرح تامین خواسته در #txtDescription1.

    ⭐ طبق دستور کارفرما — متن عیناً:
      «بدوا تقاضای صدور قرار تامین خواسته نسبت به اصل خواسته و اجرای قبل از ابلاغ»
    """
    try:
        ok = await page.evaluate('''(text) => {
            const inp = document.querySelector('#txtDescription1');
            if (inp) {
                inp.focus();
                inp.value = "";
                inp.value = text;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
            return false;
        }''', "بدوا تقاضای صدور قرار تامین خواسته نسبت به اصل خواسته و اجرای قبل از ابلاغ")
        if ok:
            logging.info("[CHECK] متن شرح تامین خواسته در #txtDescription1 درج شد")
        else:
            logging.warning("[CHECK] فیلد #txtDescription1 برای شرح تامین پیدا نشد")
        await asyncio.sleep(1)
    except Exception as e:
        logging.warning(f"[CHECK] خطا در درج شرح تامین خواسته: {e}")




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

    ⭐ منطق لودینگ/خطا (طبق دستور کارفرما):
      - به لودینگ بالای صفحه دقت می‌شود: تا لودینگ نمایان است منتظر
        می‌مانیم (wait_for_horizontal_loading_bar) و به تسک بعدی نمی‌رویم.
      - اگر خطای انقضای نشست/ورود همزمان ظاهر شد → مدیر باید مجدد لاگین
        کند (check_and_handle_expiry تمدید می‌کند) و تلاش مجدد می‌شود.
      - اگر بعد از لودینگ خطای دیگری نمایش داده شد → بسته می‌شود و
        یکبار دیگر امتحان می‌شود؛ اگر دوباره خطا ظاهر شد، متن همان خطا
        برای کاربر و مدیر ارسال می‌شود و خروجی 'failed' است.

    خروجی: 'ok' | 'failed' (پیام‌ها ارسال شده‌اند) | 'no_response'
    """
    error_seen = False
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

        # صبر اولیه + لودینگ افقی — تا وقتی لودینگ نمایان است منتظر می‌مانیم
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
                # مدیریت شده توسط check_and_handle_expiry — تمدید و تلاش مجدد
                continue

            # ⭐ اصلاحیهٔ کارفرما: خطای «تاریخ تولد ارسالی مربوط به شماره ملی
            # ... اشتباه است» یا «اطلاعاتی با این شناسه ملی ثبت نشده است» —
            # retry بی‌فایده است؛ بلافاصله CheckSanaDataError پرتاب می‌شود تا
            # پنجرهٔ ۳۰ دقیقه‌ای ویرایش کدملی برای کاربر باز شود.
            if kind in ("birthdate", "not_registered"):
                logging.warning(
                    f"[CHECK][{role}] خطای داده‌ای ثنا برای کدملی {national_id}: "
                    f"{popup_text!r}")
                raise CheckSanaDataError(
                    popup_text, kind=kind, national_id=national_id, role=role)

            # خطای غیر نشست دیگر: یکبار retry؛ اگر دوباره خطا آمد →
            # متن خطا برای کاربر و مدیر ارسال می‌شود
            logging.warning(
                f"[CHECK][{role}] خطای استعلام ثنا برای کدملی {national_id} "
                f"(تلاش {attempt+1}): {popup_text!r}")
            if error_seen:
                # دفعهٔ دوم → قطعی؛ متن خطا برای کاربر و مدیر ارسال می‌شود
                await _notify_sana_query_failure(
                    bot, user_id, national_id, role, popup_text)
                return "failed"
            error_seen = True
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
            # ⚠️ Playwright فقط یک آرگومان اضافی می‌پذیرد — sel/val در یک دیکشنری
            await page.evaluate('''(a) => {
                const inp = document.querySelector(a.sel);
                if (inp && inp.offsetParent !== null) {
                    inp.focus();
                    inp.value = "";
                    inp.value = a.val;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', {"sel": sel, "val": national_id})
            await asyncio.sleep(1)
            break

    # ⭐ استعلام ثنا — دکمهٔ استعلام از طریق ng-click (id ندارد!)
    status = await _query_sana_check(page, "actions.callNationalityCode", bot, user_id,
                                     role=role, national_id=national_id)
    if status == "failed":
        # ⭐ خطای قطعی — پیام‌های کاربر/مدیر داخل _query_sana_check ارسال
        # شده‌اند؛ فقط قطع فرآیند بدون تلاش مجدد
        raise CheckAbortError(
            f"استعلام ثنا برای {role} (کدملی {national_id}) ناموفق",
            step="SANA_QUERY_FAILED")
    if status == "no_response":
        # پاسخ قطعی نگرفتیم — هشدار و ادامه (اگر فرم واقعاً نامعتبر باشد،
        # bill_no خالی در ثبت موقت قطعش می‌کند)
        logging.warning(f"[CHECK][{role}] استعلام بدون پاسخ — ادامه با احتیاط")


async def _set_legal_record_no_zero_check(page):
    """شماره ثبت شخص حقوقی (#txtLegalIrShSabt / RecordNo) را روی «0» می‌گذارد.

    ⚠️ این مرحله در نسخهٔ قبلی _fill_legal_person در چک به‌کل حذف شده بود.
    مطابق الگوی اظهارنامه (_set_legal_record_no_zero در
    ezhharnameh_scenario.py)، وقتی شخص حقوقی خصوصی است، سامانه این فیلد
    را اجباری می‌کند و بدون آن، ثبت با خطای اعتبارسنجی مواجه می‌شود. این
    فیلد فقط پس از استعلام موفق شرکت رندر می‌شود، پس باید بعد از
    callLegalNationalityCode صدا زده شود.
    """
    for _ in range(10):
        done = await page.evaluate('''() => {
            const inp = document.querySelector('#txtLegalIrShSabt');
            if (!inp) return false;
            inp.value = "0";
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            try {
                if (typeof angular !== 'undefined') {
                    const ctrl = angular.element(inp).controller('ngModel');
                    if (ctrl) { ctrl.$setViewValue("0"); ctrl.$render(); }
                }
            } catch(e) {}
            return true;
        }''')
        if done:
            logging.info("[CHECK] شماره ثبت شخص حقوقی روی «0» تنظیم شد")
            await asyncio.sleep(1)
            return True
        await asyncio.sleep(0.5)
    logging.warning("[CHECK] فیلد شماره ثبت (#txtLegalIrShSabt) یافت نشد — رد شد")
    return False


async def _set_legal_economic_code_one_check(page):
    """کد اقتصادی شخص حقوقی (#txtLegalIrECode / EconomicCode) را روی «1» می‌گذارد.

    ⭐ طبق دستور کارفرما: در کلیه بخش‌های ربات، هر جا شخص حقوقی وارد شد،
    بعد از استعلام موفق شناسه ملی شرکت باید در فیلد کد اقتصادی عدد 1
    وارد شود:
        <input id="txtLegalIrECode" ... maxlength="11"
         ng-model="viewModel.currentPetitionPerson.EconomicCode">
    این فیلد فقط پس از استعلام موفق شرکت در صفحه رندر می‌شود، پس باید
    بعد از callLegalNationalityCode صدا زده شود.
    """
    for _ in range(10):
        done = await page.evaluate('''() => {
            const inp = document.querySelector('#txtLegalIrECode, input[ng-model$=".EconomicCode"]');
            if (!inp || inp.disabled) return false;
            inp.focus();
            inp.value = "1";
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            try {
                if (typeof angular !== 'undefined') {
                    const ctrl = angular.element(inp).controller('ngModel');
                    if (ctrl) { ctrl.$setViewValue("1"); ctrl.$render(); }
                    const scope = angular.element(inp).scope();
                    if (scope && scope.$root && !scope.$root.$$phase) scope.$apply();
                }
            } catch(e) {}
            return true;
        }''')
        if done:
            logging.info("[CHECK] کد اقتصادی شخص حقوقی (#txtLegalIrECode) روی «1» تنظیم شد")
            await asyncio.sleep(1)
            return True
        await asyncio.sleep(0.5)
    logging.warning("[CHECK] فیلد کد اقتصادی (#txtLegalIrECode) یافت نشد — رد شد")
    return False


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int,
                             role: str = "", idx: int = 0) -> bool:
    """پر کردن اطلاعات شخص حقوقی + استعلام شرکت و نماینده.

    ⭐ رفع باگ: این تابع دقیقاً مطابق _fill_legal_person در
    ezhharnameh_scenario.py بازنویسی شد (طبق درخواست صریح، فلوی چک باید
    عیناً همان مراحل اظهارنامه را برای خواهان/خوانده شخص حقوقی طی کند).
    مشکلات نسخهٔ قبلی که باعث شکست ثبت خواهان حقوقی در چک می‌شد:
      ۱. هیچ‌کدام از رادیوباتن‌های «شخص حقوقی» و «غیردولتی/خصوصی» کلیک
         نمی‌شدند — روی این سامانه، فرم به‌طور پیش‌فرض روی «شخص حقیقی»
         است و بدون این کلیک‌ها، فیلد شناسه ملی شرکت اصلاً رندر نمی‌شود.
      ۲. فیلد «شماره ثبت» شخص حقوقی خصوصی (که سامانه پس از استعلام
         موفق شرکت اجباری می‌کند) هرگز پر نمی‌شد.
      ۳. نوع نماینده (دراپ‌داون AgentTypeId) قبل از استعلام شرکت انتخاب
         می‌شد، در حالی که این فیلد معمولاً فقط بعد از پاسخ موفق استعلام
         شرکت در صفحه ظاهر می‌شود.

    ⭐ اصلاحیه ۱۴۰۵/۰۶ (باگ ۵ — دعاوی اعسار): خروجی تابع نشان می‌دهد آیا
    نمایندهٔ اول واقعاً در همین مرحله ثبت/استعلام شده است یا نه — تا حلقهٔ
    تب «نماينده» در صورت ثبت‌نشدن، نمایندهٔ اول را هم ثبت کند (قبلاً
    نمایندهٔ اول کورکورانه اسکیپ می‌شد و کدملی مدیرعامل/نماینده وارد
    نمی‌شد).

    خروجی: True اگر نمایندهٔ اول با موفقیت وارد و استعلام شد؛ در غیر این
    صورت False (شامل حالت «بدون کدملی نماینده»).
    """
    company_id = person.get("company_id", "")
    nat_id = person.get("national_id", "")
    rep_type = person.get("representative_type", "نماینده")

    # ── انتخاب رادیوباتن «شخص حقوقی» (مشابه اظهارنامه) ──────────────
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdb3, input[value="3"][name="personType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # ── انتخاب «غیردولتی / خصوصی» ────────────────────────────────────
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdbPrivate, input[value="4"][name="LegalPersonType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # وارد کردن شناسه ملی شرکت (چند سلکتور برای اطمینان از تطبیق فرم)
    await page.evaluate('''(val) => {
        const inp = document.querySelector('#txtLegalNationalityCode, #txtLegalIrNationalityCode');
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
    if company_status == "failed":
        # پیام‌ها داخل _query_sana_check ارسال شده‌اند — فقط قطع
        raise CheckAbortError(
            f"استعلام ثنا برای شرکت {role} (شناسه {company_id}) ناموفق",
            step="SANA_QUERY_FAILED")

    # شماره ثبت شخص حقوقی — همیشه صفر (مشابه اظهارنامه)
    await _set_legal_record_no_zero_check(page)

    # ⭐ کد اقتصادی شخص حقوقی — طبق دستور کارفرما بعد از استعلام شناسه ملی،
    # عدد 1 در فیلد #txtLegalIrECode (EconomicCode) وارد می‌شود.
    await _set_legal_economic_code_one_check(page)

    if not nat_id:
        # بدون کدملی نماینده — فقط ثبت شناسه ملی شرکت کافی است
        logging.info(f"[CHECK] شخص حقوقی {role} بدون کدملی نماینده — فقط شناسه ملی شرکت ثبت شد")
        return False

    await asyncio.sleep(3)

    # انتخاب نوع نماینده (مدیرعامل یا نماینده) — بعد از استعلام موفق شرکت،
    # چون این دراپ‌داون معمولاً فقط پس از پاسخ موفق شرکت رندر می‌شود
    # ⭐ باگ ۵: انتخاب دراپ‌داون چندتلاشی شد (قبلاً یک‌بارِ بی‌retry بود و
    # اگر فیلد دیر رندر می‌شد، نمایندهٔ اول هرگز وارد نمی‌شد)
    agent_value = "0091000010000008" if rep_type == "مدیرعامل" else "0091000010000010"
    agent_set = False
    for _agent_try in range(5):
        agent_set = await page.evaluate('''(val) => {
            const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
            if (sel && !sel.disabled) {
                sel.focus();
                sel.value = val;
                sel.dispatchEvent(new Event("input", { bubbles: true }));
                sel.dispatchEvent(new Event("change", { bubbles: true }));
                try {
                    if (typeof angular !== 'undefined') {
                        const ctrl = angular.element(sel).controller('ngModel');
                        if (ctrl) { ctrl.$setViewValue(val); ctrl.$render(); }
                        const scope = angular.element(sel).scope();
                        if (scope && scope.$root && !scope.$root.$$phase) scope.$apply();
                    }
                } catch(e) {}
                return true;
            }
            return false;
        }''', agent_value)
        if agent_set:
            break
        logging.warning(
            f"[CHECK] دراپ‌داون نوع نماینده ({role}) آماده نشد — تلاش {_agent_try + 1}/5")
        await asyncio.sleep(3)
    await asyncio.sleep(2)

    # وارد کردن کدملی نماینده
    rep_set = False
    for _try in range(5):
        rep_set = await page.evaluate('''(val) => {
            const inp = document.querySelector('#txtRealIrNationalityCode');
            if (inp && !inp.disabled) {
                inp.focus();
                inp.value = val;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                try {
                    if (typeof angular !== 'undefined') {
                        const ctrl = angular.element(inp).controller('ngModel');
                        if (ctrl) { ctrl.$setViewValue(val); ctrl.$render(); }
                        const scope = angular.element(inp).scope();
                        if (scope && scope.$root && !scope.$root.$$phase) scope.$apply();
                    }
                } catch(e) {}
                return true;
            }
            return false;
        }''', nat_id)
        if rep_set:
            break
        await asyncio.sleep(3)

    if not rep_set or not agent_set:
        logging.error(
            f"[CHECK] کدملی نمایندهٔ {role} ({nat_id}) در مرحلهٔ "
            f"خواهان/خوانده وارد نشد (agent_set={agent_set}, rep_set={rep_set}) — "
            f"در تب «نماينده» دوباره تلاش می‌شود")
        # ⭐ باگ ۵: بدون استعلامِ بی‌فایده — نمایندهٔ اول در تب «نماينده»
        # دوباره کامل (دراپ‌داون + کدملی + استعلام) ثبت خواهد شد.
        return False

    # ⭐ استعلام نماینده
    rep_status = await _query_sana_check(
        page, "actions.callNationalityCode", bot, user_id,
        role=f"{role} (نماینده)", national_id=nat_id)
    if rep_status == "failed":
        # پیام‌ها داخل _query_sana_check ارسال شده‌اند — فقط قطع
        raise CheckAbortError(
            f"استعلام ثنا برای نمایندهٔ {role} (کدملی {nat_id}) ناموفق",
            step="SANA_QUERY_FAILED")

    # نمایندهٔ اول فقط در صورتی «ثبت‌شده» محسوب می‌شود که کدملی واقعاً
    # وارد شده باشد؛ در غیر این صورت تب «نماينده» آن را دوباره ثبت می‌کند.
    return True


async def _fill_lawyer_person(page, national_id: str, bot: Bot, user_id: int):
    # ⭐ اصلاحیه: در فرم «وکيل» دادخواست، فیلد کدملی وکیل #txtNationalityCode
    # است (ng-model=viewModel.currentPetitionPerson.NationalityCode) و استعلام
    # با actions.getLawyerDataWithSana(viewModel.currentPetitionPerson,false)
    # انجام می‌شود — نه #txtRealIrNationalityCode + callNationalityCode.
    # قبلاً به‌اشتباه از مسیر شخص حقیقی استفاده می‌شد و کدملی وکیل هرگز
    # وارد/استعلام نمی‌شد.

    # ۱) وارد کردن کدملی وکیل در #txtNationalityCode
    filled = await page.evaluate('''(val) => {
        const inp = document.querySelector('#txtNationalityCode');
        if (!inp || inp.disabled) return false;
        inp.focus();
        inp.value = "";
        inp.value = val;
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        inp.dispatchEvent(new Event("change", { bubbles: true }));
        try {
            if (typeof angular !== 'undefined') {
                const el = angular.element(inp);
                const ctrl = el.controller('ngModel');
                if (ctrl) { ctrl.$setViewValue(val); ctrl.$render(); }
                const scope = el.scope();
                if (scope && scope.$root && !scope.$root.$$phase) scope.$apply();
            }
        } catch (e) {}
        return true;
    }''', national_id)
    if not filled:
        raise CheckAbortError(
            "فیلد کدملی وکیل (#txtNationalityCode) در فرم «وکيل» پیدا نشد",
            step="LAWYER_FIELD_NOT_FOUND")
    await asyncio.sleep(1)

    # ۲) استعلام وکیل — دکمهٔ «استعلام»:
    #    ng-click="actions.getLawyerDataWithSana(viewModel.currentPetitionPerson,false)"
    status = await _query_sana_check(
        page, "actions.getLawyerDataWithSana", bot, user_id,
        role="وکیل", national_id=national_id)
    if status == "failed":
        raise CheckAbortError(
            f"استعلام ثنا برای وکیل (کدملی {national_id}) ناموفق",
            step="SANA_QUERY_FAILED")
    if status == "no_response":
        logging.warning(
            f"[CHECK][وکیل] استعلام وکیل {national_id} پاسخ قطعی نداد — ادامه با احتیاط")


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
    «تصوير چك» با «تصوير چك و گواهينامه عدم پرداخت» اشتباه گرفته نشد.

    ⭐ دور ۳: اگر گزینه پیدا نشد، فهرست کامل گزینه‌های موجود در لاگ
    ثبت می‌شود تا علت واقعی (تغییر برچسب سامانه/نوع خواستهٔ اشتباه)
    قابل تشخیص باشد.
    """
    ok = await page.evaluate('''(label) => {
        const sel = document.querySelector('#attachmentType');
        if (!sel || sel.disabled) return false;
        if (sel.tagName !== 'SELECT') return false;
        const opts = Array.from(sel.options || []);
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
        # ⭐ دور ۳ — dump گزینه‌های موجود برای عیبیابی
        try:
            available = await page.evaluate('''() => {
                const sel = document.querySelector('#attachmentType');
                if (!sel || sel.tagName !== 'SELECT') return [];
                return Array.from(sel.options || [])
                    .map(o => (o.innerText || '').trim()).filter(t => t);
            }''')
            logging.warning(
                f"[CHECK][منضمات] نوع پیوست «{label}» در لیست پیدا نشد — "
                f"گزینه‌های موجود ({len(available)}): {available}")
        except Exception:
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
        ok = await page.evaluate('''(a) => {
            const sel = document.querySelector('#' + a.sid);
            if (!sel || sel.disabled) return false;
            if (sel.tagName !== 'SELECT') return false;
            const opts = Array.from(sel.options || []).filter(o => {
                const v = (o.value || '').trim();
                const t = (o.text || '').trim();
                if (!v || v === "?" || v === "0" || v.startsWith("? string")) return false;
                if (!t) return false;
                return true;
            });
            if (opts.length === 0) return false;
            const target = (a.mode === 'last') ? opts[opts.length - 1] : opts[0];
            sel.focus();
            sel.value = target.value;
            sel.dispatchEvent(new Event("input", { bubbles: true }));
            sel.dispatchEvent(new Event("change", { bubbles: true }));
            return true;
        }''', {"sid": select_id, "mode": mode})
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
            ''' + JS_NORMALIZE_FN + '''
            const normLabel = _normFa(label);
            // پاک‌سازی علامت قبلی
            document.querySelectorAll('button[data-check-edit]').forEach(
                b => b.removeAttribute('data-check-edit'));
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            let target = null;
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                for (const cell of cells) {
                    const text = _normFa(cell.innerText || '');
                    if (text.includes(normLabel)) {
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
    وگرنه «ساير ضمائم» + عنوان دلخواه (الگوی upload_helpers).

    ⭐ اصلاحیه (طبق الگوی اظهارنامهٔ کارِکرده): قبلاً برای «مدرک نمایندگی»
    فقط نوع پیوست انتخاب می‌شد و بقیهٔ فیلدهای الزامی فرم (#txtNo=۰،
    #txtName، تقویم=امروز و تعداد صفحات #txt001/#incAttach0) خالی می‌ماند؛
    در نتیجه #btnSaveDoc غیرفعال می‌ماند یا ردیف ناقص ثبت می‌شد. حالا عیناً
    مسیر `_upload_representative_doc` اظهارنامه اجرا می‌شود:
      ۱. انتخاب «تصوير مدرک نمايندگي» از #attachmentType
      ۲. #txtNo = ۰
      ۳. #txtName = عنوان مدرک (الزامی)
      ۴. تقویم = امروز
      ۵. تعداد صفحات: >۱ فایل → #txt001 + #incAttach0 | ۱ فایل → #txt001='1'
    """
    page_count = force_page_count if force_page_count else len(prepared_paths or [])

    if "نمایندگی" in doc_title or "نمايندگي" in doc_title:
        # ۱) انتخاب نوع پیوست «تصوير مدرک نمايندگي»
        ok = await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (!sel || sel.disabled) return false;
            if (sel.tagName !== 'SELECT') return false;
            const opts = Array.from(sel.options || []);
            const opt = opts.find(o => (o.text || '').includes("مدرک نمايندگي") ||
                                        (o.text || '').includes("مدرک نمایندگی"));
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event("input", { bubbles: true }));
                sel.dispatchEvent(new Event("change", { bubbles: true }));
                try {
                    if (typeof angular !== 'undefined') {
                        const el = angular.element(sel);
                        const ctrl = el.controller('ngModel');
                        if (ctrl) { ctrl.$setViewValue(opt.value); ctrl.$render(); }
                        const scope = el.scope();
                        if (scope) scope.$apply();
                    }
                } catch (e) {}
                return true;
            }
            return false;
        }''')
        if not ok:
            logging.warning("[CHECK][منضمات] گزینهٔ «تصوير مدرک نمايندگي» پیدا نشد")
            return False
        logging.info("[CHECK][منضمات] نوع پیوست «تصوير مدرک نمايندگي» انتخاب شد")
        await asyncio.sleep(3)
        await wait_for_angular_idle(page)
        await asyncio.sleep(1)

        # ۲) شماره مدرک — #txtNo = ۰ (الگوی اظهارنامه)
        await page.evaluate('''() => {
            const inp = document.querySelector('#txtNo');
            if (inp) {
                inp.focus();
                inp.value = "0";
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                try {
                    if (typeof angular !== 'undefined') {
                        const el = angular.element(inp);
                        const ctrl = el.controller('ngModel');
                        if (ctrl) { ctrl.$setViewValue("0"); ctrl.$render(); }
                        const scope = el.scope();
                        if (scope) scope.$apply();
                    }
                } catch (e) {}
            }
        }''')
        await asyncio.sleep(1)

        # ۳) عنوان مدرک — #txtName (الزامی — الگوی اظهارنامه)؛ عنوانِ گروه
        # (مثل «مدرک نمایندگی (مدیرعامل ۱)») درج می‌شود تا هم فیلد الزامی پر
        # شود و هم ردیف‌های چند نماینده از هم قابل تشخیص باشند.
        await page.evaluate('''(val) => {
            const inp = document.querySelector('#txtName');
            if (inp) {
                inp.focus();
                inp.value = val;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                try {
                    if (typeof angular !== 'undefined') {
                        const el = angular.element(inp);
                        const ctrl = el.controller('ngModel');
                        if (ctrl) { ctrl.$setViewValue(val); ctrl.$render(); }
                        const scope = el.scope();
                        if (scope) scope.$apply();
                    }
                } catch (e) {}
            }
        }''', doc_title)
        await asyncio.sleep(1)

        # ۴) تقویم = امروز (الگوی اظهارنامه)
        try:
            await page.evaluate('''() => {
                const calBtn = document.querySelector('button.btn-primary i.glyphicon-calendar');
                if (calBtn) calBtn.closest('button').click();
            }''')
            await asyncio.sleep(2)
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const todayBtn = btns.find(b => b.innerText && b.innerText.trim() === "امروز");
                if (todayBtn) todayBtn.click();
            }''')
            await asyncio.sleep(1)
        except Exception as cal_err:
            logging.warning(f"[CHECK][منضمات] تنظیم تقویم مدرک نمایندگی ناموفق: {cal_err}")

        # ۵) تعداد صفحات — >۱ فایل: #txt001 + افزودن (#incAttach0) |
        #    ۱ فایل: #txt001='1' (فعال‌سازی #btnSaveDoc) و اسکیپ افزودن
        if page_count > 1:
            await page.evaluate('''(val) => {
                const inp = document.querySelector('#txt001');
                if (inp) {
                    inp.focus();
                    inp.value = String(val);
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                    try {
                        if (typeof angular !== 'undefined') {
                            const el = angular.element(inp);
                            const ctrl = el.controller('ngModel');
                            if (ctrl) { ctrl.$setViewValue(String(val)); ctrl.$render(); }
                            const scope = el.scope();
                            if (scope) scope.$apply();
                        }
                    } catch (e) {}
                }
            }''', page_count)
            await asyncio.sleep(1)
            await page.evaluate('''() => {
                const btn = document.querySelector('#incAttach0');
                if (btn && !btn.disabled) btn.click();
            }''')
            await asyncio.sleep(3)
        else:
            await page.evaluate('''() => {
                const inp = document.querySelector('#txt001');
                if (inp) {
                    inp.focus();
                    inp.value = "1";
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                    try {
                        if (typeof angular !== 'undefined') {
                            const el = angular.element(inp);
                            const ctrl = el.controller('ngModel');
                            if (ctrl) { ctrl.$setViewValue("1"); ctrl.$render(); }
                            const scope = el.scope();
                            if (scope) scope.$apply();
                        }
                    } catch (e) {}
                }
            }''')
            logging.info(
                f"[CHECK][منضمات] مدرک نمایندگی تک‌برگ ({page_count} فایل) — "
                "#txt001='1' پر شد، #incAttach0 اسکیپ شد")
        return True

    return await _default_fill_other_attachment_form(page, doc_title, page_count)




async def _fill_doc_field_angular(page, field_name: str, value, prefix: str = "CHECK") -> bool:
    """پر کردن یک فیلد فرم سند (#txtNo/#txtIssueDate/#txtUnit/#txtCourt/#txt001...)
    با setter امن + سینک کامل AngularJS.

    ⭐ اصلاحیه (کارفرما — دور ۳): رفع خطای
      Page.evaluate: TypeError: Illegal invocation
    هنگام وارد کردن اطلاعات دادنامه در منضمات. علت: فرمول
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
    روی عنصری که inputِ همان realm نیست (یا textarea است) با
    «Illegal invocation» شکست می‌خورد و کل مرحلهٔ منضمات قطع می‌شد
    (ATTACHMENTS_UNEXPECTED_ERROR). حالا:
      ۱) نوع عنصر تشخیص داده می‌شود (input / textarea)
      ۲) setter بومی داخل try/catch با فال‌بک انتساب مستقیم el.value
      ۳) سینک AngularJS از طریق $setViewValue/$render + $apply (الگوی
         اظهارنامهٔ کارکرده)
    """
    val = "" if value is None else str(value)
    ok = await page.evaluate('''(a) => {
        const el = document.querySelector('#' + a.n) ||
                   document.querySelector('input[name="' + a.n + '"]') ||
                   document.querySelector('textarea[name="' + a.n + '"]');
        if (!el) return false;
        let set_ok = false;
        try {
            const proto = (el.tagName === 'TEXTAREA')
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const d = Object.getOwnPropertyDescriptor(proto, 'value');
            if (d && d.set) { d.set.call(el, a.v); set_ok = true; }
        } catch (e) { set_ok = false; }
        if (!set_ok) {
            try { el.value = a.v; } catch (e) {}
        }
        try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
        try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
        try {
            if (typeof angular !== 'undefined' && angular.element) {
                const ngEl = angular.element(el);
                const ctrl = ngEl.controller('ngModel');
                if (ctrl) { ctrl.$setViewValue(a.v); ctrl.$render(); }
                const scope = ngEl.scope();
                if (scope) scope.$apply();
            }
        } catch (e) {}
        return true;
    }''', {"n": field_name, "v": val})
    if not ok:
        logging.warning(f"[{prefix}] فیلد #{field_name} پیدا نشد")
    return bool(ok)


async def _fill_attachment_count_and_add(page, count: int, prefix: str = "CHECK") -> None:
    """⭐ دور ۳ — پر کردن «تعداد پیوست‌ها» (#txt001) و کلیک «افزودن پیوست»
    (#incAttach0) قبل از «ثبت و ویرایش پیوست» (#btnSaveDoc).

    طبق تشخیص کارفرما: بدون پر کردن فیلد تعداد و زدن «افزودن پیوست»،
    سامانه فقط یک اسلات آپلود می‌سازد — مثلاً برای استشهادیه‌ای که ۲ تصویر
    داشت فقط ۱ تصویر پیوست شد. الگو (عین اظهارنامه):
      تعداد > ۱ → #txt001 = تعداد + کلیک #incAttach0
      تعداد = ۱ → #txt001 = '1' (بدون incAttach0)
    """
    count = max(1, int(count or 1))
    if count > 1:
        await _fill_doc_field_angular(page, "txt001", count, prefix=prefix)
        await asyncio.sleep(1)
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#incAttach0');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if clicked:
            logging.info(f"[{prefix}] تعداد پیوست‌ها={count} + «افزودن پیوست» کلیک شد")
            await asyncio.sleep(3)
            await wait_for_angular_idle(page)
            await asyncio.sleep(1)
        else:
            logging.warning(f"[{prefix}] دکمهٔ «افزودن پیوست» (#incAttach0) پیدا/کلیک نشد")
    else:
        await _fill_doc_field_angular(page, "txt001", "1", prefix=prefix)
        logging.info(f"[{prefix}] تک‌برگ — #txt001='1' پر شد (#incAttach0 اسکیپ شد)")


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

    # ۲.۵) ⭐ دور ۳ — تعداد پیوست‌ها (#txt001) + «افزودن پیوست» (#incAttach0):
    # طبق تشخیص کارفرما، بدون این مرحله فقط یک اسلات آپلود ساخته می‌شود و
    # از چند تصویر فقط تصویر اول پیوست می‌شود (۲ تصویر ارسال شد، ۱ تصویر
    # ثبت شد). ترتیب طبق مشخصات سامانه: فیلدها → تعداد → افزودن پیوست →
    # ثبت و ویرایش پیوست.
    await _fill_attachment_count_and_add(page, len(image_paths or []), prefix="CHECK")

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


async def _upload_electronic_vakalaht_check(
        page, contract_number: str, lawyer_amount_value: int,
        bot: Bot, user_id: int, bill_no: str = "") -> str:
    """آپلود وکالت‌نامه الکترونیک برای دادخواست چک (الگوی اظهارنامه/لایحه).

    ⭐ طبق دستور کارفرما: وقتی وکیل انتخاب شده، شماره قرارداد وکالت و
    مقدار تمبر (خودکار محاسبه‌شده) در فرم «تصوير الكترونيك وكالت نامه»
    درج می‌شود:
      - #txtNo ← شماره قرارداد (۱۶ رقمی)
      - #txtLawyerAmount ← مقدار تمبر (ریال)
    سپس «ثبت و ویرایش پیوست» (#btnSaveDoc) کلیک و با انتظار قطعی
    (پولینگ تا ۴۵ ثانیه) پاپ‌آپ نتیجه بسته می‌شود.

    ⭐ اصلاحیه ۱۴۰۵/۰۶:
      - «شماره قرارداد الکترونیک وکالت «...» معتبر نمی باشد» → "invalid_contract"
      - «ورود به سامانه در صفحه یا رایانه ای دیگر...» → لاگین مجدد و تلاش دوباره

    خروجی: "success" | "invalid_contract" | "failed"
    """
    from upload_helpers import (
        click_save_doc_once, wait_save_doc_popup_result, close_save_doc_popup,
        fill_input_angular)

    try:
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(2)

        for attempt in range(3):
            # ۱) انتخاب «تصوير الكترونيك وكالت نامه» از نوع پیوست
            selected = await page.evaluate('''() => {
                const sel = document.querySelector('#attachmentType');
                if (!sel || sel.disabled) return false;
                if (sel.tagName !== 'SELECT') return false;
                const opts = Array.from(sel.options || []);
                const opt = opts.find(o =>
                    (o.text || '').includes("تصوير الكترونيك وكالت نامه") ||
                    (o.text || '').includes("تصویر الکترونیک وکالت نامه")
                );
                if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change")); return true; }
                return false;
            }''')
            if not selected:
                logging.warning(f"[CHECK] گزینه «تصویر الکترونیک وکالت‌نامه» پیدا نشد (تلاش {attempt+1})")
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(3)
            await wait_for_angular_idle(page)
            await asyncio.sleep(1)

            # ۲) ⭐ شماره قرارداد وکالت در #txtNo — همگام‌سازی کامل AngularJS؛
            #    اگر قرارداد خالی باشد «۰»
            await fill_input_angular(page, "#txtNo", contract_number or "0", prefix="CHECK")
            await asyncio.sleep(1)

            # ۳) ⭐ مقدار تمبر در #txtLawyerAmount — بلافاصله قبل از ثبت؛
            #    در صورت نبود مقدار، «۱» درج می‌شود (الگوی لایحه/اعلام) تا فیلد
            #    الزامی (ng-required) فرم را بی‌صدا رد نکند
            if not lawyer_amount_value or lawyer_amount_value <= 0:
                logging.warning("[CHECK][منضمات] مقدار تمبر صفر بود — مقدار «۱» درج می‌شود")
                lawyer_amount_value = 1
            await fill_input_angular(page, "#txtLawyerAmount", lawyer_amount_value, prefix="CHECK")
            await asyncio.sleep(1)

            # ۴) کلیک «ثبت و ویرایش پیوست» (#btnSaveDoc) — تک‌کلیک + انتظار قطعی پاپ‌آپ
            clicked = await click_save_doc_once(page, prefix="CHECK")
            if not clicked:
                logging.warning(f"[CHECK][منضمات] کلیک #btnSaveDoc انجام نشد (تلاش {attempt+1})")
                await asyncio.sleep(5)
                continue

            popup = await wait_save_doc_popup_result(page, timeout_sec=45, prefix="CHECK")

            if popup["status"] == "success":
                from upload_helpers import close_success_popup as _uh_close_success
                await _uh_close_success(page)
                logging.info("[CHECK] وکالت‌نامه الکترونیک با موفقیت ثبت شد")
                return "success"

            if popup["status"] == "invalid_contract":
                await close_save_doc_popup(page)
                logging.error(
                    f"[CHECK] شماره قرارداد وکالت «{popup.get('contract_no') or contract_number}» "
                    f"معتبر نمی باشد: {popup['text'][:200]}")
                return "invalid_contract"

            if popup["status"] == "session":
                logging.warning(f"[CHECK][منضمات] ورود همزمان/انقضای نشست — لاگین مجدد: {popup['text'][:150]}")
                await close_save_doc_popup(page)
                try:
                    from browser_helpers import handle_session_expired
                    await handle_session_expired(bot, user_id, page=page)
                except Exception:
                    pass
                await asyncio.sleep(5)
                continue

            if popup["status"] == "error":
                logging.warning(f"[CHECK] خطای ثبت وکالت‌نامه: {popup['text'][:200]} (تلاش {attempt+1})")
                await close_save_doc_popup(page)
                await asyncio.sleep(5)
                continue

            logging.warning(f"[CHECK][منضمات] پس از کلیک #btnSaveDoc پاپ‌آپی ظاهر نشد (تلاش {attempt+1})")
            await asyncio.sleep(5)

        return "failed"

    except Exception as e:
        logging.error(f"[CHECK] خطا در آپلود وکالت‌نامه الکترونیک: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="_upload_electronic_vakalaht_check", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        return "failed"



async def _register_marriage_certificate(page, group, group_paths, bot, user_id, bill_no) -> bool:
    """⭐ ثبت «سند ازدواج» طبق مسیر ارسالی کارفرما:
    انتخاب «سند ازدواج» در attachmentType → شماره سند (txtNo) → تاریخ عقد (txtIssueDate)
    → مقدار ثابت ۱ (txtCourt) → تعداد برگ (txt001) → «افزودن پیوست» (incAttach0)
    → «ثبت و ویرایش پیوست» (btnSaveDoc) با مدیریت خطا → آپلود تصاویر عین سایر منضمات."""
    cert_no = str(group.get("cert_no", "") or "").strip()
    cert_date = str(group.get("cert_date", "") or "").strip()
    logging.info(
        f"[CHECK][منضمات] ثبت سند ازدواج — شماره:{cert_no} تاریخ:{cert_date} "
        f"تصویر:{len(group_paths)}")

    # ۱) «پیوست جدید»
    clicked = await page.evaluate("""() => {
        const btn = document.querySelector('#newAttachmentType');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }""")
    if clicked:
        await asyncio.sleep(3)
        await wait_for_angular_idle(page)
        await asyncio.sleep(1)

    # ۲) انتخاب «سند ازدواج» در فهرست نوع سند
    #    ⭐ دور ۳: چند نامزد امتحان می‌شود — قبلاً اگر نوع خواستهٔ سامانه
    #    اشتباه انتخاب می‌شد (مثل «اثبات رجوع از بذل مهریه»)، فهرست نوع
    #    سند اصلاً «سند ازدواج» نداشت و ثبت متوقف می‌شد. با انتخاب درستِ
    #    «مطالبه مهریه» (fix دور ۳ در _select_khasteh_option) این لیست
    #    درست می‌شود؛ نامزدهای جایگزین برای مقاوم‌سازی بیشتر است.
    _MARRIAGE_CERT_LABELS = ("سند ازدواج", "سند ازداج", "سند نکاح دائم", "سند نکاح")
    type_selected = False
    for _label in _MARRIAGE_CERT_LABELS:
        if await _select_attachment_type(page, _label):
            type_selected = True
            break
    if not type_selected:
        err = "گزینه «سند ازدواج» در فهرست نوع سند یافت نشد"
        logging.error(f"[CHECK][منضمات] {err}")
        try:
            await bot.send_message(ADMIN_ID, f"❌ [CHECK] {err} — کاربر {user_id} | کد: {bill_no}")
        except Exception:
            pass
        return False
    await asyncio.sleep(1)

    # ۳) شماره سند + تاریخ عقد + فیلد ثابت «1» + تعداد برگ
    #    ⭐ دور ۳: پر کردن فیلدها با setter امن + سینک AngularJS — رفع خطای
    #    «Page.evaluate: TypeError: Illegal invocation» که احتمالاً در همین
    #    فرمول setter بومی رخ می‌داد.
    if cert_no:
        await _fill_doc_field_angular(page, "txtNo", cert_no)
    if cert_date:
        await _fill_doc_field_angular(page, "txtIssueDate", cert_date)
        await asyncio.sleep(0.5)
        try:
            await page.evaluate(
                "() => { document.querySelectorAll('.dropdown-menu, ul.dropdown-menu')"
                ".forEach(m => m.remove()); }")
        except Exception:
            pass
    await _fill_doc_field_angular(page, "txtCourt", "1")
    await _fill_doc_field_angular(page, "txt001", str(len(group_paths or [])))
    await asyncio.sleep(0.5)

    # ۴) «افزودن پیوست»
    added = await page.evaluate("""() => {
        const btn = document.querySelector('#incAttach0');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }""")
    if not added:
        err = "دکمه «افزودن پیوست» (incAttach0) یافت نشد"
        logging.error(f"[CHECK][منضمات] {err}")
        try:
            await bot.send_message(ADMIN_ID, f"❌ [CHECK] {err} — کاربر {user_id} | کد: {bill_no}")
        except Exception:
            pass
        return False
    await asyncio.sleep(1)

    # ۵) «ثبت و ویرایش پیوست» با ریترای و اعمال خطاها/نکات منضمات
    save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix="CHECK")
    if not save_ok:
        error_text = await _uh_error_popup_text(page)
        logging.error(f"[CHECK][منضمات] ذخیره سند ازدواج ناموفق: {error_text!r}")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"❌ [CHECK] ذخیره سند ازدواج ناموفق — کاربر {user_id} | کد: {bill_no} | "
                f"خطا: {(error_text or 'نامشخص')[:200]}")
        except Exception:
            pass
        return False
    await resilient_sleep(page, 5, bot, user_id)

    # ۶) آپلود تصاویر عین سایر منضمات
    if group_paths:
        upload_result = await _upload_check_files(
            page, "سند ازدواج", group_paths, bot, user_id, bill_no)
        if not upload_result.get("success"):
            logging.error(
                f"[CHECK][منضمات] آپلود تصاویر سند ازدواج ناموفق: {upload_result.get('error')}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CHECK] آپلود تصاویر سند ازدواج ناموفق — کاربر {user_id} | کد: {bill_no} | "
                    f"خطا: {(upload_result.get('error') or 'نامشخص')[:200]}")
            except Exception:
                pass
            return False
    logging.info("[CHECK][منضمات] سند ازدواج ثبت و تصاویر آپلود شد")
    return True


async def _register_dadnameh_attachment(page, group, group_paths, bot, user_id, bill_no) -> bool:
    """⭐ ثبت «تصويردادنامه غيرمكانيزه» (دادنامه/اجرائیه) طبق مسیر کارفرما:

    انتخاب «تصويردادنامه غيرمكانيزه» در attachmentType →
      - #txtNo ← شماره دادنامه (عددی)
      - #txtIssueDate ← تاریخ دادنامه (فرمت ۱۴۰۳/۰۶/۱۵)
      - #txtUnit ← نام دادگاه
      - #txtCourt ← شماره شعبه
    → تعداد برگ پیوست (#txt001 = تعداد تصاویر) → «افزودن پیوست» (incAttach0)
    → «ثبت و ویرایش پیوست» (btnSaveDoc) با مدیریت خطا → آپلود تصاویر عین سایر منضمات.
    """
    dadnameh_no = str(group.get("dadnameh_no", "") or "").strip()
    dadnameh_date = str(group.get("dadnameh_date", "") or "").strip()
    dadnameh_court = str(group.get("dadnameh_court", "") or "").strip()
    dadnameh_branch = str(group.get("dadnameh_branch", "") or "").strip()
    logging.info(
        f"[CHECK][منضمات] ثبت دادنامه غیرمکنه — شماره:{dadnameh_no} تاریخ:{dadnameh_date} "
        f"دادگاه:{dadnameh_court} شعبه:{dadnameh_branch} تصویر:{len(group_paths)}")

    # ۱) «پیوست جدید»
    clicked = await page.evaluate("""() => {
        const btn = document.querySelector('#newAttachmentType');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }""")
    if clicked:
        await asyncio.sleep(3)
        await wait_for_angular_idle(page)
        await asyncio.sleep(1)

    # ۲) انتخاب «تصويردادنامه غيرمكانيزه» در فهرست نوع سند
    if not await _select_attachment_type(page, "تصويردادنامه غيرمكانيزه"):
        err = "گزینه «تصويردادنامه غيرمكانيزه» در فهرست نوع سند یافت نشد"
        logging.error(f"[CHECK][منضمات] {err}")
        try:
            await bot.send_message(ADMIN_ID, f"❌ [CHECK] {err} — کاربر {user_id} | کد: {bill_no}")
        except Exception:
            pass
        return False
    await asyncio.sleep(1)

    # ۳) تکمیل فیلدهای سند — شماره دادنامه / تاریخ / نام دادگاه / شماره شعبه
    #    ⭐ دور ۳: با setter امن + سینک AngularJS (_fill_doc_field_angular) —
    #    رفع خطای «Page.evaluate: TypeError: Illegal invocation» که در همین
    #    فرمول setter بومی (HTMLInputElement.prototype.value.set) هنگام ورود
    #    اطلاعات دادنامه رخ می‌داد و کل منضمات را قطع می‌کرد.
    filled_no = await _fill_doc_field_angular(page, "txtNo", dadnameh_no)
    if not filled_no:
        logging.warning("[CHECK][منضمات] فیلد #txtNo (شماره دادنامه) پیدا نشد")
    else:
        await asyncio.sleep(0.5)

    filled_date = await _fill_doc_field_angular(page, "txtIssueDate", dadnameh_date)
    if filled_date:
        await asyncio.sleep(0.5)
        # بستن dropdown تقویم فارسی که ممکن است روی فرزندها باز شود
        try:
            await page.evaluate(
                "() => { document.querySelectorAll('.dropdown-menu, ul.dropdown-menu')"
                ".forEach(m => m.remove()); }")
        except Exception:
            pass
    else:
        logging.warning("[CHECK][منضمات] فیلد #txtIssueDate (تاریخ دادنامه) پیدا نشد")

    if dadnameh_court:
        filled_unit = await _fill_doc_field_angular(page, "txtUnit", dadnameh_court)
        if not filled_unit:
            logging.warning("[CHECK][منضمات] فیلد #txtUnit (نام دادگاه) پیدا نشد")

    if dadnameh_branch:
        filled_court = await _fill_doc_field_angular(page, "txtCourt", dadnameh_branch)
        if not filled_court:
            logging.warning("[CHECK][منضمات] فیلد #txtCourt (شماره شعبه) پیدا نشد")

    # ۴) تعداد برگ پیوست (مثل سایر پیوست‌ها)
    await _fill_doc_field_angular(page, "txt001", str(len(group_paths or [])))
    await asyncio.sleep(0.5)

    # ۵) «افزودن پیوست»
    added = await page.evaluate("""() => {
        const btn = document.querySelector('#incAttach0');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }""")
    if not added:
        err = "دکمه «افزودن پیوست» (incAttach0) برای دادنامه یافت نشد"
        logging.error(f"[CHECK][منضمات] {err}")
        try:
            await bot.send_message(ADMIN_ID, f"❌ [CHECK] {err} — کاربر {user_id} | کد: {bill_no}")
        except Exception:
            pass
        return False
    await asyncio.sleep(1)

    # ۶) «ثبت و ویرایش پیوست» با ریترای و اعمال خطاها/نکات منضمات
    save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix="CHECK")
    if not save_ok:
        error_text = await _uh_error_popup_text(page)
        logging.error(f"[CHECK][منضمات] ذخیره دادنامه غیرمکنه ناموفق: {error_text!r}")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"❌ [CHECK] ذخیره دادنامه غیرمکنه ناموفق — کاربر {user_id} | کد: {bill_no} | "
                f"خطا: {(error_text or 'نامشخص')[:200]}")
            await bot.send_message(
                user_id,
                "⚠️ ثبت پیوست دادنامه در بخش منضمات با خطا مواجه شد.\n"
                f"🔢 کد بایگانی: `{bill_no}`\n"
                f"لطفاً به شماره {SUPPORT_PHONE} در واتساپ یا بله پیام دهید.")
        except Exception:
            pass
        return False
    await resilient_sleep(page, 5, bot, user_id)

    # ۷) آپلود تصاویر عین سایر منضمات
    if group_paths:
        upload_result = await _upload_check_files(
            page, "تصويردادنامه غيرمكانيزه", group_paths, bot, user_id, bill_no)
        if not upload_result.get("success"):
            logging.error(
                f"[CHECK][منضمات] آپلود تصاویر دادنامه ناموفق: {upload_result.get('error')}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CHECK] آپلود تصاویر دادنامه ناموفق — کاربر {user_id} | کد: {bill_no} | "
                    f"خطا: {(upload_result.get('error') or 'نامشخص')[:200]}")
            except Exception:
                pass
            return False
    logging.info("[CHECK][منضمات] دادنامه غیرمکنه ثبت و تصاویر آپلود شد")
    return True


async def _process_check_attachments(
    page,
    request_title: str,
    cheque_items: list,
    attachment_groups: list,
    bot: Bot,
    user_id: int,
    bill_no: str,
    plaintiffs: list = None,
    defendants: list = None):
    """اجرای کامل مرحلهٔ «منضمات» دادخواست — طبق مشخصات کارفرما.

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
      ۲.۵. ⭐ وکالت‌نامه الکترونیک — اگر وکیل داریم (شماره قرارداد + تمبر
           خودکار) — الگوی اظهارنامه/lایحه
      ۳. پیوست‌های اضافی کاربر (check_attachment_groups) با «سایر ضمائم»
         (و «تصوير مدرک نمايندگي» برای مدرک نمایندگی) — الگوی اظهارنامه

    خروجی: (status, contract_fix_lawyer)
      - status: True = ادامهٔ فرآیند | False = قطع (پیام‌ها ارسال شده‌اند) | "contract_fix" = شماره قرارداد نامعتبر (پنجرهٔ ۴۵ دقیقه‌ای باز می‌شود)
      - contract_fix_lawyer: {"contract_number", "stamp_amount_value"} وکیلِ قراردادش نامعتبر بود
    """
    is_ejra = (request_title == "صدور اجرائیه چک")
    attachment_label = ("تصوير چك و گواهينامه عدم پرداخت" if is_ejra else "تصوير چك")

    # ۱) ورود به منضمات
    if not await _enter_attachments_section(page, bot, user_id, bill_no):
        return False, {}

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
                return False, {}
            if inquiry_status == "failed":
                # پیام «سامانه قطع» برای کاربر ارسال شده — توقف کل فرآیند
                return False, {}
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

    # ۲.۵) ⭐ وکالت‌نامه الکترونیک — برای هر وکیل (خواهان یا خوانده) که شماره
    # قرارداد وکالت و تمبر دارد؛ قبلاً فقط وکیل خواهان (و فقط اولین مورد)
    # پردازش می‌شد — حالا روی همهٔ وکلای خواهان و خوانده حلقه می‌زند تا
    # وکالت‌نامهٔ وکیل خوانده هم در سامانه ثبت شود.
    # ⭐ اصلاحیه: قبلاً «defendants» در این تابع تعریف نشده بود و خطای
    # NameError کل مرحلهٔ منضمات را قطع می‌کرد (هیچ تصویری پیوست نمی‌شد و
    # پرونده با ATTACHMENTS_UNEXPECTED_ERROR متوقف می‌شد) — حالا به‌عنوان
    # پارامتر دریافت می‌شود تا وکیل خوانده هم در وکالت‌نامه الکترونیک ثبت شود.
    contract_fix_pending = False
    contract_fix_lawyer = {}
    lawyers = [p for p in (list(plaintiffs or []) + list(defendants or []))
               if p.get("person_type") == "وکیل"]
    for lawyer in lawyers:
        contract_no = lawyer.get("contract_number", "")
        stamp_val = int(lawyer.get("stamp_amount_value", 0) or 0)
        if not (contract_no or stamp_val):
            continue
        # «پیوست جدید» برای فرم وکالت‌نامه الکترونیک
        await asyncio.sleep(2)
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#newAttachmentType');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if clicked:
            logging.info("[CHECK][منضمات] کلیک «پیوست جدید» برای وکالت‌نامه الکترونیک")
            await asyncio.sleep(3)
            await wait_for_angular_idle(page)
            await asyncio.sleep(1)
        vakalaht_status = await _upload_electronic_vakalaht_check(
            page, contract_no, stamp_val, bot, user_id, bill_no)
        if vakalaht_status == "invalid_contract":
            # ⭐ اصلاحیه ۱۴۰۵/۰۶ — دستور کارفرما: این مرحله اسکیپ می‌شود؛
            # ابتدا سایر پیوست‌های کاربر انجام و سپس اعلام ۴۵ دقیقه‌ای
            # ارسال کد قرارداد جدید می‌شود. آماده‌سازی/هزینه/چاپ تا پس از
            # ثبت قرارداد جدید به تعویق می‌افتد.
            contract_fix_pending = True
            contract_fix_lawyer = {"contract_number": contract_no, "stamp_amount_value": stamp_val}
            logging.error(
                f"[CHECK][منضمات] شماره قرارداد وکالت «{contract_no}» معتبر نمی باشد — "
                f"اسکیپ مرحله و ادامه با سایر پیوست‌ها (کاربر {user_id})")
            await log_event(
                "خطای سامانه", "دادخواست", str(user_id), user_id,
                tracking_code=bill_no, doc_name=request_title,
                note=f"شماره قرارداد وکالت «{contract_no}» معتبر نمی باشد (کد بایگانی: {bill_no})")
        elif vakalaht_status != "success":
            # شکست وکالت‌نامه فرآیند کلی را قطع نمی‌کند — مدیر مطلع می‌شود
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ [CHECK] وکالت‌نامه الکترونیک (قرارداد {contract_no}) برای کاربر "
                f"{user_id} ثبت نشد — لطفاً در سامانه به‌صورت دستی بررسی کنید. "
                f"کد: {bill_no}")

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

        # ⭐ استشهادیه محلی — فقط وقتی کاربر درخواست اعسار داده است یا عنوان
        # اعسار است؛ طبق دستور کارفرما: نوع پیوست «استشهاديه محلي» + تمام فیلدها = ۱
        # ⭐ سند ازدواج — مسیر اختصاصی طبق دستور کارفرما (سپس مابقی عین منضمات)
        # ⭐ دادنامه غیرمکنه — عناوین اعسار (تصويردادنامه غيرمكانيزه + ۴ فیلد سند)
        # ⭐ لیست اموال — عناوین اعسار (ساير ضمائم)
        if group.get("is_marriage_cert"):
            mc_ok = await _register_marriage_certificate(
                page, group, group_paths, bot, user_id, bill_no)
            if not mc_ok:
                logging.error("[CHECK][منضمات] ثبت سند ازدواج ناموفق بود")
        elif bool(group.get("is_dadnameh")):
            dn_ok = await _register_dadnameh_attachment(
                page, group, group_paths, bot, user_id, bill_no)
            if not dn_ok:
                logging.error("[CHECK][منضمات] ثبت دادنامه غیرمکنه ناموفق بود")
            else:
                logging.info("[CHECK][منضمات] پیوست «تصويردادنامه غيرمكانيزه» ثبت و آپلود شد")
        elif bool(group.get("is_esteshahadieh")) or ("استشهاد" in group_title):
            estesh_ok = await _upload_esteshahadieh_attachment(
                page, group_paths, bot, user_id, bill_no)
            if not estesh_ok:
                logging.error("[CHECK][استشهادیه] ثبت/آپلود استشهادیه ناموفق بود")
            else:
                logging.info("[CHECK][استشهادیه] پیوست «استشهاديه محلي» ثبت و آپلود شد")
        elif bool(group.get("is_assets_list")) or ("لیست اموال" in group_title) or ("ليست اموال" in group_title):
            # ⭐ لیست اموال — مانند سایر پیوست‌ها با «ساير ضمائم» ثبت و آپلود می‌شود
            upload_result = await resilient_upload_attachment(
                page, group_title, group_paths, bot, user_id,
                prefix="CHECK", form_fill_fn=_fill_extra_attachment_form)
            if not upload_result.get("success"):
                logging.error(
                    f"[CHECK][منضمات] آپلود لیست اموال ناموفق: "
                    f"{upload_result.get('error')}")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [CHECK] آپلود لیست اموال ناموفق — کاربر {user_id} | "
                    f"کد: {bill_no} | خطا: {(upload_result.get('error') or 'نامشخص')[:200]}")
            else:
                logging.info("[CHECK][منضمات] پیوست «لیست اموال» (ساير ضمائم) آپلود شد")
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

    # ⭐ اصلاحیه ۱۴۰۵/۰۶ — اگر شماره قرارداد وکالت نامعتبر بود، وضعیت
    # "contract_fix" برگردانده می‌شود تا فراخواننده (process_check_task)
    # پنجرهٔ ۴۵ دقیقه‌ای کد قرارداد جدید را باز کند و مراحل آماده‌سازی/
    # هزینه/چاپ را تا پس از ثبت قرارداد جدید به تعویق بیندازد.
    if contract_fix_pending:
        return "contract_fix", contract_fix_lawyer

    return True, {}


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
    from lavayeh_scenario import _is_valid_pdf_file
    pdf_path = f"check_{bill_no or user_id}_{int(time.time())}.pdf"

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

    # ⭐ تا ۲ تلاش: اگر حین چاپ نشست منقضی شود، check_and_handle_expiry لاگین
    # مجدد را انجام می‌دهد؛ چون print_page ممکن است به Offices/Index
    # ریدایرکت شده باشد (نه سند واقعی)، تلاش دوم صفحه‌ی چاپ را از نو باز
    # می‌کند تا PDF واقعی گرفته شود.
    last_err = None
    for attempt in range(1, 3):
        print_page = None
        try:
            async with browser_context.expect_page(timeout=25000) as new_page_info:
                await click_print()

            print_page = await new_page_info.value
            await print_page.wait_for_load_state("load", timeout=30000)
            await asyncio.sleep(8)
            session_expired = False
            try:
                session_expired = await check_and_handle_expiry(print_page, bot, user_id, check_body_text=False)
            except Exception:
                pass
            if session_expired:
                try:
                    await print_page.close()
                except Exception:
                    pass
                print_page = None
                if attempt < 2:
                    continue
            else:
                await print_page.pdf(path=pdf_path, format="A4")
                logging.info(f"[CHECK] PDF چاپ اولیه ذخیره شد: {pdf_path}")
                try:
                    await print_page.close()
                except Exception:
                    pass
                print_page = None
                if _is_valid_pdf_file(pdf_path):
                    return pdf_path
                logging.warning(f"[CHECK] PDF چاپ نامعتبر بود (تلاش {attempt}/2)")
        except Exception as e:
            last_err = e
            logging.error(f"[CHECK] خطا در چاپ PDF (تلاش {attempt}/2): {e}")
        finally:
            if print_page is not None:
                try:
                    await print_page.close()
                except Exception:
                    pass

    if last_err is not None:
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="check_print", error=last_err,
                             user_id=user_id, page=page)
        except Exception:
            pass
    return pdf_path if _is_valid_pdf_file(pdf_path) else ""
