# -*- coding: utf-8 -*-
"""بخش ۱ — هدر، ایمپورت‌ها، ثابت‌ها و توابع متنی سناریوی دعاوی اعتراضی."""

# ══════════════════════════════════════════════════════════════════════════════
# سناریوی ثبت دعاوی اعتراضی در سامانه قضایی ثنا — بازنویسی کامل طبق سند راهنما.
#
# ۷ نوع دعوی:
#   تجدیدنظرخواهی، واخواهی، فرجام‌خواهی،
#   اعاده دادرسی مدنی، اعاده دادرسی کیفری،
#   اعتراض ثالث، اعتراض به قرار دادسرا
#
# جریان کلی (عیناً هم‌تراز با اظهارنامه — ezhharnameh_scenario.py):
#   ۱. منوی «دعاوی اعتراضی» → نوع دعوی → باکس مرحله ثبت (مخصوص همان نوع —
#      REGISTER_BOX_MAP؛ مثلاً تجدیدنظرخواهی «ثبت و اصلاح دادخواست»، اعاده
#      دادرسی کیفری «ثبت و اصلاح اعاده دادرسي»، دادسرا «ثبت و اصلاح درخواست»)
#   ۲. مرحله «شروع» — انتخاب نوع ارائه (حقیقی/وکیل/نماینده) مانند اظهارنامه
#   ۳. مرحله «اطلاعات دادنامه/قرار»:
#      - شماره دادنامه (#txtJudgeNo) + شماره پرونده (#txtReferingCaseNo)
#      - تاریخ تنظیم دادنامه (persian-datepicker)
#      - استان (خادم مرتبط — مانند لایحه)
#      - «بازیابی» (#btnGetHst) → پاپ‌آپ «بلی» → انتظار لودینگ
#        · خطای ورود همزمان → لاگین مجدد + اطلاع مدیر (عین کدهای قبلی)
#        · خطای دیگر → بستن پاپ‌آپ + استعلام مجدد
#      - پس از بازیابی: تاریخ (NoticeDateTime مقاوم)، در صورت «قرار»:
#        #rdbJudDictum سپس #rdbModifiedByUserOk، مبلغ
#        (ModifyByUserPenaltyAmount — مبلغ کاربر یا ۱)، اعسار (#rdbIsMoserByPetition)
#      - جدول «پرونده‌های مرتبط» → «حذف همه» + #chkSelectAll (در صورت نمایش)
#   ۴. مرحله «تجدیدنظرخواه» — پاک‌سازی کامل nav-list + افزودن اشخاص
#      (مانند اظهارکننده اظهارنامه) — یا حالت استعلام (حذف انتخاب‌نشده‌ها)
#   ۵. مرحله «تجدیدنظرخوانده» — همانند بالا + وکیل/نماینده مانند اظهارنامه
#   ۶. مراحل «وكيل» (در صورت وجود وکیل) و «نماينده» (در صورت وجود حقوقی)
#   ۷. مرحله «مطلع/گواه» یا «سایر اشخاص» (کیفری) — شهود
#   ۸. مرحله «شرح» — متن مانند اظهارنامه
#   ۹. مرحله «دلايل» — سایر دلایل (#chk1 + #ReasonAttach1) یا اسکیپ
#   ۱۰. مرحله «جهات» (فقط اعاده دادرسی) — چک‌باکس جهات انتخابی
#   ۱۱. «ثبت موقت» (#btnSave) → هشدارها/خطاها + کد رهگیری (مانند اظهارنامه)
#   ۱۲. «منضمات» — عیناً مانند اظهارنامه (مدرک نمایندگی/وکالت‌نامه/سایر)
#   ۱۳. «آماده‌سازی» — تایید اطلاعات → پاپ‌آپ → «بستن» → بازگشت به فهرست
#   ۱۴. «هزینه» — جدول هزینه + فرمول (جمع ۵ ردیف + ۵۰ ریال + جمع کل، رند بالا)
#   ۱۵. «چاپ اولیه» → PDF → ارسال نتیجه (پرداخت/امضا طبق روال مستقل)
# ══════════════════════════════════════════════════════════════════════════════

import asyncio
import html as html_lib
import logging
import os
import time

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry,
    goto_url_with_retry, human_delay, safe_click_by_text,
    wait_for_angular_idle, handle_session_expired,
    wait_for_horizontal_loading_bar, detect_concurrent_login_popup,
    NavigationResetError)


class TajdidFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


class TajdidSanaQueryError(Exception):
    """خطای استعلام ثنا — شناسه ملی ثبت نشده یا تاریخ تولد اشتباه."""
    def __init__(self, message: str, national_id: str = "", person_role: str = "", person_index: int = 0):
        super().__init__(message)
        self.national_id = national_id
        self.person_role = person_role
        self.person_index = person_index


# ══════════════════════════════════════════════════════════════════════════════
# ثابت‌ها
# ══════════════════════════════════════════════════════════════════════════════

# نگاشت نوع دعوی به نام منوی سامانه
CASE_TYPE_MENU_MAP = {
    "تجدیدنظرخواهی": "تجدیدنظرخواهی",
    "واخواهی": "واخواهی",
    "فرجام خواهی": "فرجام خواهی",
    "اعاده دادرسی مدنی": "اعاده دادرسی مدنی",
    "اعاده دادرسی کیفری": "اعاده دادرسی کیفری",
    "اعتراض ثالث": "اعتراض ثالث",
    "اعتراض به قرار دادسرا": "اعتراض به قرار دادسرا",
}

# ⭐ نگاشت نوع دعوی به عنوان باکس مرحله ثبت (h5 در صفحه انتخاب مراحل)
# طبق HTML واقعی سامانه (گزارش کارفرما ۱۴۰۵/۰۶): هر نوع دعوی باکس مخصوص خودش را
# دارد و باکس «ثبت و اصلاح دادخواست» فقط برای تجدیدنظرخواهی است!
#   تجدیدنظرخواهی      → «ثبت و اصلاح دادخواست»
#   واخواهی            → «ثبت و اصلاح واخواهي»
#   فرجام خواهی        → «ثبت و اصلاح فرجام خواهي»
#   اعاده دادرسی مدنی  → «ثبت و اصلاح اعاده دادرسي مدني»
#   اعاده دادرسی کیفری → «ثبت و اصلاح اعاده دادرسي»
#   اعتراض ثالث        → «ثبت و اصلاح اعتراض ثالث»
#   اعتراض به قرار دادسرا → «ثبت و اصلاح درخواست»
# ⚠ عناوین عین عبارت سامانه‌اند (ي/ك عربی) — تطبیق با نرمال‌سازی انجام می‌شود.
# ⚠ «ثبت و اصلاح اعاده دادرسي» پیشوندِ «ثبت و اصلاح اعاده دادرسي مدني» است؛
#   به همین دلیل تطبیق باکس همیشه «اول دقیق، بعد شامل‌شدن» انجام می‌شود.
REGISTER_BOX_MAP = {
    "تجدیدنظرخواهی": "ثبت و اصلاح دادخواست",
    "واخواهی": "ثبت و اصلاح واخواهي",
    "فرجام خواهی": "ثبت و اصلاح فرجام خواهي",
    "اعاده دادرسی مدنی": "ثبت و اصلاح اعاده دادرسي مدني",
    "اعاده دادرسی کیفری": "ثبت و اصلاح اعاده دادرسي",
    "اعتراض ثالث": "ثبت و اصلاح اعتراض ثالث",
    "اعتراض به قرار دادسرا": "ثبت و اصلاح درخواست",
}
REGISTER_BOX_DEFAULT = "ثبت و اصلاح دادخواست"

# نگاشت نوع دعوی به نام step اشخاص اول
# ⚠ نکته: تطبیق step ها با نرمال‌سازی نیم‌فاصله/ي/ك انجام می‌شود، اما فاصله‌ی
# معمولی حذف نمی‌شود (_click_step_label) — پس مقادیر زیر باید *دقیقاً* با
# متن واقعی HTML سامانه (کلاس .step) یکی باشند. طبق گزارش کارفرما
# (۱۴۰۵/۰۶/۲۰) این مقادیر برای واخواهی/فرجام‌خواهی/اعاده دادرسی/اعتراض ثالث
# اصلاح شدند (فاصله واقعی به‌جای نیم‌فاصله، و برچسب‌های درست هر نوع دعوی).
APPELLANT_STEP_MAP = {
    "تجدیدنظرخواهی": "تجديدنظرخواه",
    "واخواهی": "واخواه",
    "فرجام خواهی": "فرجام خواه",
    "اعاده دادرسی مدنی": "متقاضي اعاده دادرسي",
    "اعاده دادرسی کیفری": "محكوم عليه",
    "اعتراض ثالث": "معترض ثالث",
    "اعتراض به قرار دادسرا": "درخواست دهنده",
}

# نگاشت نوع دعوی به نام step اشخاص دوم
APPELLEE_STEP_MAP = {
    "تجدیدنظرخواهی": "تجديدنظرخوانده",
    "واخواهی": "واخوانده",
    "فرجام خواهی": "فرجام خوانده",
    "اعاده دادرسی مدنی": "طرف اعاده دادرسي",
    "اعاده دادرسی کیفری": "طرف اعاده دادرسي",
    "اعتراض ثالث": "طرف اعتراض ثالث",
    "اعتراض به قرار دادسرا": "اعتراض‌شونده",
}

# نام step شهود/مطلع — در کیفری «سایر اشخاص» است (طبق سند راهنما)
WITNESS_STEP_MAP = {
    "اعاده دادرسی کیفری": "سايراشخاص",
}
WITNESS_STEP_DEFAULT = "مطلع/ گواه"

# مقدار value برای نوع نماینده در dropdown نماينده (مانند اظهارنامه)
AGENT_TYPE_VALUES = {
    "مدیرعامل": "0091000010000008",
    "نماینده": "0091000010000010",
}

# ══════════════════════════════════════════════════════════════════════════════
# جهات درخواست اعاده دادرسی — متن کامل و عین عبارت سامانه (chk0..chk6)
# ⚠ این متن‌ها «منبع واحد حقیقت» هستند: هندلرها همین لیست را برای نمایش
# شماره‌گذاری‌شده به کاربر می‌فرستند و همین لیست ایندکس چک‌باکس سامانه است.
# نسخه قبلی: متن‌های کوتاه‌شده هندلر با کلیدهای متفاوت سناریو mismatch بود
# و جهات هرگز در سامانه انتخاب نمی‌شدند.
# ══════════════════════════════════════════════════════════════════════════════

EADAH_MADANI_GROUNDS = [
    "موضوع حكم مورد، ادعاي خواهان نبوده است",
    "وجود تضاد در مفاد يك حكم كه ناشي از استناد به اصول يا به مواد متضاد است",
    "حكم صادره با حكم ديگري در خصوص همان دعوا و اصحاب آن، كه قبلا توسط همان دادگاه صادر شده است متضاد است، بدون انكه سبب قانوني موجب اين مغايرت باشد",
    "طرف مقابل درخواست كننده اعاده دادرسي حيله و تقلبي به كار برده كه در حكم دادگاه موثربوده است",
    "پس از صدور حكم، اسناد و مداركي به دست ايد كه دليل حقانيت درخواست كننده اعاده دادرسي باشد و ثابت شود اسناد و مدارك ياد شده در جريان دادرسي مكتوم بوده و در اختيار متقاضي نبوده است",
    "حكم به ميزان بيشتر از خواسته صادر شده است",
    "حكم دادگاه مستند به اسنادي بوده كه پس از صدور حكم جعلي بودن آنها ثابت شده است",
]

EADAH_KIFRI_GROUNDS = [
    "كسى به اتهام قتل شخصى محكوم شود و سپس زنده بودن وى محرز گردد.",
    "محكوميت چند نفر به اتهام ارتكاب جرمى كه نتوان بيش از يك مرتكب براى آن قائل شد.",
    "تعارض و تضاد مفاد دو حكم بى‌گناهى يكى از آنان احراز گردد.",
    "درباره شخصى به اتهام واحد، احكام متفاوتى صادر شود.",
    "اثبات جعليت اسناد يا خلاف واقع بودن شهادت گواهان كه مبناى حكم بوده است.",
    "حدوث واقعه جديد يا كشف ادله جديد بر بى‌گناهى محكومٌ عليه يا عدم تقصير وى",
    "عمل ارتكابى جرم نباشد و يا مجازات مورد حكم بيش از مجازات مقرر قانونى باشد.",
]


def get_grounds_list(case_type: str) -> list:
    """لیست جهات کامل بر اساس نوع دعوی (اعاده دادرسی مدنی/کیفری)."""
    if case_type == "اعاده دادرسی مدنی":
        return list(EADAH_MADANI_GROUNDS)
    if case_type == "اعاده دادرسی کیفری":
        return list(EADAH_KIFRI_GROUNDS)
    return []


def _normalize_fa(text: str) -> str:
    """نرمال‌سازی متن فارسی برای تطبیق (ي→ی، ك→ک، حذف نیم‌فاصله و فاصله‌ها)."""
    return (
        (text or "")
        .replace("\u064A", "\u06CC")   # ي → ی
        .replace("\u0643", "\u06A9")   # ك → ک
        .replace("\u200c", "")         # حذف نیم‌فاصله
        .replace("\u200f", "")
        .replace("إ", "ا")
        .replace("أ", "ا")
        .replace("٫", ".")
    ).strip()


def resolve_ground_indices(reasons, case_type: str) -> list:
    """تبدیل جهات انتخابی به ایندکس چک‌باکس سامانه (chk{idx}).

    ورودی می‌تواند:
      - لیستی از dict: [{"index": int, "text": str}, ...]  (فرمت جدید هندلرها)
      - لیستی از str (سازگاری با داده‌های قدیمی) — با نرمال‌سازی متن تطبیق می‌شود

    خروجی: لیست مرتب ایندکس‌های یکتا.
    """
    grounds = get_grounds_list(case_type)
    indices = []
    for r in (reasons or []):
        if isinstance(r, dict):
            idx = r.get("index")
            text = r.get("text", "")
        else:
            idx = None
            text = str(r)
        if isinstance(idx, int) and 0 <= idx < len(grounds):
            indices.append(idx)
            continue
        # تطبیق متنی با نرمال‌سازی
        norm_text = _normalize_fa(text)
        if norm_text:
            for i, g in enumerate(grounds):
                if _normalize_fa(g) == norm_text:
                    indices.append(i)
                    break
    return sorted(set(indices))


# ══════════════════════════════════════════════════════════════════════════════
# فرمول محاسبه هزینه دعاوی اعتراضی (طبق سند راهنما):
#   ۱. عدد «جمع کل هزینه» جدول یادداشت می‌شود (مثال: ۴,۵۹۲,۱۹۹)
#   ۲. این ۵ ردیف با هم جمع می‌شوند:
#      بهاي اوراق دادخواست + افزودن پيوست + ثبت اطلاعات اشخاص
#      + تنظيم دادخواست/شكواييه + خدمات الكترونيك قضايي
#   ۳. در آخر ۵۰ ریال اضافه می‌شود
#   ۴. با عدد اصلی (جمع کل) جمع و «رند به بالا» می‌شود
# ══════════════════════════════════════════════════════════════════════════════

TN_COST_FORMULA_LABELS = [
    "اوراق دادخواست",       # بهاي اوراق دادخواست
    "افزودن پيوست",         # افزودن پيوست در خدمات قضايي
    "ثبت اطلاعات اشخاص",    # هزينه ثبت اطلاعات اشخاص در خدمات قضايي
    "تنظيم دادخواست",       # هزينه تنظيم دادخواست/شكواييه در خدمات قضايي
    "الكترونيك قضايي",      # هزينه خدمات الكترونيك قضايي
]
TN_COST_SMS_SURCHARGE = 50  # ریال — «و در اخر به اضافه 50 میکنی»


def round_up_to_ten_thousand(amount: int) -> int:
    """رند به بالا به نزدیک‌ترین ۱۰,۰۰۰ ریال (همان الگوی اظهارنامه)."""
    if amount <= 0:
        return 0
    return ((amount + 9999) // 10000) * 10000


def _text_to_editor_html(text: str) -> str:
    """متن کاربر را با حفظ فاصله‌ها/اینترها به HTML امن برای ادیتور تبدیل می‌کند."""
    if not text:
        return "<p><br></p>"
    lines = text.split("\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")
        parts.append(f"<p>{escaped}</p>" if escaped else "<p><br></p>")
    return "".join(parts)
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی ناوبری (منو / باکس مرحله / step / دکمه افزودن / بازگشت به فهرست)
# ══════════════════════════════════════════════════════════════════════════════

async def _click_menu_item(page, menu_text: str, bot: Bot, user_id: int):
    """کلیک روی آیتم منوی سامانه — با نرمال‌سازی متن.

    دو نوع عنصر پشتیبانی می‌شود (طبق HTML سند راهنما):
      - هدر منوی اصلی (مثل «دعاوی اعتراضی»): تگ <a class="list-group-item">
        با data-toggle="collapse" که زیرمنو را باز می‌کند.
      - آیتم زیرمنو (مثل «تجدیدنظرخواهی»): تگ <li class="list-group-item">
        با ng-click="actions.loadForm(subMenu)".

    ⭐ اصلاحیه: قبلاً فقط li جستجو می‌شد؛ هدرِ <a> پیدا نمی‌شد و کد به
    safe_click_by_text می‌افتاد که ماشین‌آلات جانبی‌اش (go_back روی کلاس
    .error، کلیک button.confirm فرضی و ...) ریسک پرت‌شدن صفحه دارد.
    الگوی اثبات‌شده check_scenario: کلیک JS مستقیم روی a.list-group-item.
    """
    clicked = await page.evaluate('''(menuText) => {
        const norm = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC').replace(/\\u0643/g, '\\u06A9')
            .replace(/[\\u200c\\u200f]/g, '')
            .replace(/\\s+/g, ' ').trim();
        const t = norm(menuText);
        // ۱) هدر منوی اصلی (<a>) — تطبیق دقیق سپس شامل‌شدن
        // ۲) آیتم زیرمنو (<li>) — تطبیق دقیق سپس شامل‌شدن
        for (const sel of ['a.list-group-item', 'li.list-group-item']) {
            const items = Array.from(document.querySelectorAll(sel));
            const el = items.find(x => norm(x.innerText) === t)
                    || items.find(x => norm(x.innerText).includes(t));
            if (el) { el.click(); return true; }
        }
        return false;
    }''', menu_text)
    if not clicked:
        await safe_click_by_text(page, menu_text, bot, user_id)


async def _click_step_box(page, step_name: str, bot: Bot, user_id: int) -> bool:
    """کلیک روی box مرحله (مثل «ثبت و اصلاح دادخواست» / «منضمات» / «آماده سازي...»)."""
    clicked = await page.evaluate('''(stepName) => {
        const heads = Array.from(document.querySelectorAll('.box h5'));
        const t = heads.find(el => el.innerText && el.innerText.trim().includes(stepName));
        if (t) {
            const box = t.closest('.box');
            if (box) { box.click(); return true; }
        }
        return false;
    }''', step_name)
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)
        return False

    # مسیر کلیک مستقیم — چک انقضا صریح (الگوی اظهارنامه)
    await asyncio.sleep(1.5)
    had_expiry = await check_and_handle_expiry(page, bot, user_id)
    if had_expiry:
        logging.info(f"[TN] session renewed after clicking box '{step_name}' — retrying click.")
        await page.evaluate('''(stepName) => {
            const heads = Array.from(document.querySelectorAll('.box h5'));
            const t = heads.find(el => el.innerText && el.innerText.trim().includes(stepName));
            if (t) {
                const box = t.closest('.box');
                if (box) box.click();
            }
        }''', step_name)
        await asyncio.sleep(1.5)
    return True


async def _click_step_label(page, step_name: str, bot: Bot, user_id: int) -> bool:
    """کلیک روی .step مرحله — با نرمال‌سازی نیم‌فاصله/ي/ك و اولویت تطبیق دقیق.

    ⚠ «تجديدنظرخواه» پیشوندِ «تجديدنظرخوانده» است — تطبیق دقیق اول انجام
    می‌شود تا step اشتباه کلیک نشود (باگ نسخه قبلی).
    """
    clicked = await page.evaluate('''(stepName) => {
        const norm = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC').replace(/\\u0643/g, '\\u06A9')
            .replace(/\\u200c/g, '').replace(/\\u200f/g, '')
            .replace(/\\s+/g, ' ').replace(/\\s*\\/\\s*/g, '/').trim();
        const steps = Array.from(document.querySelectorAll('.step'));
        // ۱) تطبیق دقیق پس از نرمال‌سازی
        let t = steps.find(el => norm(el.innerText) === norm(stepName));
        // ۲) تطبیق شامل‌شدن (فال‌بک)
        if (!t) t = steps.find(el => norm(el.innerText).includes(norm(stepName)));
        if (t) { t.click(); return true; }
        return false;
    }''', step_name)
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)
        return False
    return True


async def _step_exists(page, step_name: str) -> bool:
    """آیا step با این نام در صفحه وجود دارد؟ (بدون کلیک)"""
    return await page.evaluate('''(stepName) => {
        const norm = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC').replace(/\\u0643/g, '\\u06A9')
            .replace(/\\u200c/g, '').replace(/\\u200f/g, '')
            .replace(/\\s+/g, ' ').replace(/\\s*\\/\\s*/g, '/').trim();
        const steps = Array.from(document.querySelectorAll('.step'));
        return steps.some(el => norm(el.innerText) === norm(stepName))
            || steps.some(el => norm(el.innerText).includes(norm(stepName)));
    }''', step_name)


async def _click_step_label_soft(page, step_name: str) -> bool:
    """کلیک نرم روی .step — بدون فال‌بک safe_click_by_text.

    برای step های اختیاری (وكيل/نماينده) که ممکن است در همه انواع دعوی
    وجود نداشته باشند؛ فال‌بک متنی باعث NavigationResetError و ری‌استارت
    کل ثبت می‌شد.
    """
    return await page.evaluate('''(stepName) => {
        const norm = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC').replace(/\\u0643/g, '\\u06A9')
            .replace(/\\u200c/g, '').replace(/\\u200f/g, '')
            .replace(/\\s+/g, ' ').replace(/\\s*\\/\\s*/g, '/').trim();
        const steps = Array.from(document.querySelectorAll('.step'));
        let t = steps.find(el => norm(el.innerText) === norm(stepName));
        if (!t) t = steps.find(el => norm(el.innerText).includes(norm(stepName)));
        if (t) { t.click(); return true; }
        return false;
    }''', step_name)


async def _click_add_section_btn(page, bot: Bot, user_id: int):
    """کلیک دکمه «افزودن» (#btnAddSection) — الگوی اظهارنامه/چک."""
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        const btns = Array.from(document.querySelectorAll('button'));
        const t = btns.find(el => el.innerText && el.innerText.trim().includes("افزودن") && !el.disabled);
        if (t) { t.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)
    await asyncio.sleep(2)


async def _click_goto_main(page, bot: Bot, user_id: int):
    """کلیک «بازگشت به فهرست» (#gotoMainPage / #btnGotoMainPage)."""
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#gotoMainPage, #btnGotoMainPage');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        from browser_helpers import soft_click_if_exists
        await soft_click_if_exists(page, "بازگشت به فهرست")


# ══════════════════════════════════════════════════════════════════════════════
# پاپ‌آپ‌ها
# ══════════════════════════════════════════════════════════════════════════════

async def _close_popup(page) -> bool:
    """بستن پاپ‌آپ sweet-alert (دکمه confirm)."""
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _close_success_popup(page) -> bool:
    """بستن پاپ‌آپ موفقیت («بستن»)."""
    return await _close_popup(page)


async def _get_error_text(page, click_confirm: bool = True):
    """دریافت متن خطای sweet-alert (بدون آیکون موفقیت)."""
    text = await page.evaluate('''(doClick) => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return null;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim();
        if (doClick) {
            const btn = popup.querySelector('button.confirm');
            if (btn) btn.click();
        }
        return msg || null;
    }''', click_confirm)
    if text:
        await asyncio.sleep(1)
    return text


def _is_session_error_text(text) -> bool:
    """آیا متن خطا نشانه ورود همزمان/انقضای نشست است؟ (مقاوم در برابر ورودی غیرمتنی)"""
    if not text or not isinstance(text, str):
        return False
    return any(k in text for k in (
        "منقضی", "منقضي",
        "رایانه ای دیگر", "رایانه اي ديگر", "رایانهٔ دیگر",
        "اعتبار ورود", "ورود قبلی", "صفحه یا رایانه",
    ))


# ══════════════════════════════════════════════════════════════════════════════
# پر کردن اشخاص (عیناً الگوی اظهارنامه/چک)
# ══════════════════════════════════════════════════════════════════════════════

async def _fill_real_person(page, national_id: str, bot: Bot, user_id: int,
                            person_role: str = "", person_index: int = 0):
    """پر کردن کدملی شخص حقیقی و استعلام ثنا (مانند اظهارکننده اظهارنامه)."""
    for sel in ["#txtRealIrNationalityCode1", "#txtRealIrNationalityCode"]:
        elem_count = await page.locator(sel).count()
        if elem_count > 0:
            # ⚠ page.evaluate فقط یک آرگومان (غیر از تابع JS) می‌پذیرد —
            # چند مقدار باید در یک دیکشنری بسته‌بندی شوند.
            await page.evaluate('''({sel, val}) => {
                const inp = document.querySelector(sel);
                if (inp && inp.offsetParent !== null) {
                    inp.value = val;
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', {"sel": sel, "val": national_id})
            await asyncio.sleep(1)
            break

    # استعلام ثنا
    await _query_sana(page, "actions.callNationalityCode", bot, user_id,
                      current_national_id=national_id, person_role=person_role,
                      person_index=person_index)


async def _set_legal_record_no_zero(page):
    """شماره ثبت شخص حقوقی (#txtLegalIrShSabt) را روی «0» می‌گذارد."""
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
            } catch (e) {}
            return true;
        }''')
        if done:
            await asyncio.sleep(1)
            return True
        await asyncio.sleep(0.5)
    logging.warning("[TN] فیلد شماره ثبت (#txtLegalIrShSabt) یافت نشد — رد شد")
    return False


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int,
                             person_role: str = "", person_index: int = 0):
    """پر کردن اطلاعات شخص حقوقی + استعلام شرکت و نماینده.

    عیناً الگوی اثبات‌شده اظهارنامه/چک:
      ۱. رادیو «شخص حقوقی» (#rdb3 / value=3)
      ۲. رادیو «غیردولتی/خصوصی» (#rdbPrivate / value=4)
      ۳. شناسه ملی شرکت + استعلام (callLegalNationalityCode)
      ۴. شماره ثبت = 0
      ۵. نوع نماینده (dropdown AgentTypeId) — بعد از استعلام
      ۶. کدملی نماینده + استعلام
    """
    company_id = person.get("company_id", "")
    national_id = person.get("national_id", "")
    rep_type = person.get("representative_type", "نماینده")

    # ۱. رادیو «شخص حقوقی»
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdb3, input[value="3"][name="personType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # ۲. رادیو «غیردولتی / خصوصی»
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdbPrivate, input[value="4"][name="LegalPersonType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # ۳. شناسه ملی شرکت (چند سلکتور برای اطمینان)
    await page.evaluate('''(val) => {
        const inp = document.querySelector('#txtLegalNationalityCode, #txtLegalIrNationalityCode, #txtLegalNationalityCode1');
        if (inp && inp.offsetParent !== null) {
            inp.value = val;
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }''', company_id)
    await asyncio.sleep(1)

    # استعلام شرکت
    await _query_sana(page, "actions.callLegalNationalityCode", bot, user_id,
                      current_national_id=company_id, person_role=person_role,
                      person_index=person_index)

    # ۴. شماره ثبت — همیشه صفر
    await _set_legal_record_no_zero(page)

    if not national_id:
        logging.info(f"[TN] شخص حقوقی ({person_role}) بدون کدملی نماینده — فقط شناسه ملی شرکت ثبت شد")
        return

    await asyncio.sleep(3)

    # ۵. نوع نماینده — بعد از استعلام موفق شرکت رندر می‌شود
    agent_value = AGENT_TYPE_VALUES.get(rep_type, AGENT_TYPE_VALUES["نماینده"])
    logging.info(f"[TN] انتخاب نوع نماینده: {rep_type} -> {agent_value}")
    await page.evaluate('''(val) => {
        const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
        if (sel && !sel.disabled) {
            sel.focus();
            sel.value = val;
            sel.dispatchEvent(new Event("input", { bubbles: true }));
            sel.dispatchEvent(new Event("change", { bubbles: true }));
            return true;
        }
        return false;
    }''', agent_value)
    await asyncio.sleep(2)

    # ۶. کدملی نماینده — با چند تلاش (ممکن است دیر رندر شود)
    for _try in range(5):
        set_ok = await page.evaluate('''(val) => {
            const inp = document.querySelector('#txtRealIrNationalityCode, #txtRealIrNationalityCode1');
            if (inp && !inp.disabled && inp.offsetParent !== null) {
                inp.value = val;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
            return false;
        }''', national_id)
        if set_ok:
            break
        await asyncio.sleep(3)

    # استعلام نماینده
    await _query_sana(page, "actions.callNationalityCode", bot, user_id,
                      current_national_id=national_id, person_role=person_role,
                      person_index=person_index)


async def _fill_lawyer_person(page, national_id: str, bot: Bot, user_id: int,
                              person_role: str = "", person_index: int = 0):
    """پر کردن کدملی وکیل در step وكيل + استعلام (الگوی اظهارنامه)."""
    await page.evaluate('''(val) => {
        const inp = document.querySelector('#txtNationalityCode');
        if (inp) {
            inp.value = val;
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }''', national_id)
    await asyncio.sleep(1)

    await _query_sana(page, "actions.getLawyerDataWithSana", bot, user_id,
                      current_national_id=national_id, person_role=person_role,
                      person_index=person_index)


async def _query_sana(page, ng_click: str, bot: Bot, user_id: int,
                      current_national_id: str = "", person_role: str = "",
                      person_index: int = 0, max_retries: int = 5):
    """استعلام از ثنا — الگوی اظهارنامه (کلیک، انتظار لودینگ، بررسی پاپ‌آپ).

    - انقضای نشست → تمدید (handle_session_expired) و تلاش مجدد
    - خطای «ثبت نشده/تاریخ تولد اشتباه» → TajdidSanaQueryError
    - موفقیت → فیلد کدملی disabled می‌شود (ExtractedFromSana)
    """
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[TN] session renewed before query attempt {attempt + 1}")
            continue

        # کلیک دکمه استعلام (ng-click + فال‌بک tooltip)
        clicked = await page.evaluate('''(ngClick) => {
            const btns = Array.from(document.querySelectorAll('button[ng-click*="' + ngClick + '"]'));
            const btn = btns.find(b => !b.disabled);
            if (btn) { btn.click(); return true; }
            const warns = Array.from(document.querySelectorAll('button.btn-warning'));
            const w = warns.find(b => !b.disabled && (
                (b.getAttribute("tooltip") || "").includes("استعلام") ||
                (b.getAttribute("title") || "").includes("استعلام")
            ));
            if (w) { w.click(); return true; }
            return false;
        }''', ng_click)

        if not clicked:
            logging.warning(f"[TN] دکمه استعلام ({ng_click}) پیدا نشد — تلاش {attempt + 1}")

        # صبر اولیه + لودینگ افقی
        await asyncio.sleep(5)
        loading_result = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if loading_result == "SESSION_EXPIRED":
            logging.warning(f"[TN] session expiry during query loading — retry")
            continue
        if loading_result:
            logging.warning(f"[TN] خطا بعد از لودینگ استعلام: {loading_result} — تلاش مجدد")
            await asyncio.sleep(5)
            continue

        # بررسی session expiry بعد از استعلام
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[TN] session renewed after query attempt {attempt + 1}")
            continue

        # بررسی پاپ‌آپ خطای ثنا
        popup_error = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' ').trim();
            return msg || null;
        }''')

        if popup_error and isinstance(popup_error, str):
            if _is_session_error_text(popup_error):
                logging.warning(f"[TN] session expiry detected in popup after query")
                await _close_popup(page)
                await handle_session_expired(bot, user_id, page=page)
                continue

            is_not_registered = ("ثبت نشده" in popup_error and "شناسه" in popup_error) or \
                                ("اطلاعاتی با این شناسه ملی ثبت نشده است" in popup_error)
            is_birthdate_error = "تاریخ تولد" in popup_error and "اشتباه" in popup_error

            if is_not_registered or is_birthdate_error:
                await _close_popup(page)
                logging.warning(f"[TN] خطای ثنا برای شناسه {current_national_id}: {popup_error}")
                raise TajdidSanaQueryError(
                    popup_error,
                    national_id=current_national_id,
                    person_role=person_role,
                    person_index=person_index)

        # بستن هر پاپ‌آپ خطای دیگر
        await _close_popup(page)
        await asyncio.sleep(2)

        # بررسی موفقیت: فیلد کدملی غیرفعال شده است
        success = await page.evaluate('''() => {
            const disabled = document.querySelector(
                'input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"]');
            if (disabled) return true;
            const inp = document.querySelector('#txtRealIrNationalityCode, #txtRealIrNationalityCode1, #txtNationalityCode');
            return inp ? inp.disabled : false;
        }''')
        if success:
            logging.info(f"[TN] استعلام موفق ({ng_click})")
            return

        await asyncio.sleep(5)

    logging.warning(f"[TN] استعلام ({ng_click}) پس از {max_retries} تلاش نتیجه نداد")
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
# مرحله «اطلاعات دادنامه/قرار» — پرکردن، بازیابی (بلی) و فرم پس از بازیابی
# ══════════════════════════════════════════════════════════════════════════════

async def _select_province(page, province: str, bot: Bot, user_id: int, max_retries: int = 4) -> bool:
    """انتخاب استان از دراپ‌داون ui-select «خادم مرتبط» — مانند لایحه.

    آیتم‌های لیست به شکل «واحدهاي قضايي مستقر در استان يزد» هستند؛
    تطبیق با نرمال‌سازی حروف عربی/فارسی و سه استراتژی (دقیق → بدون
    فاصله → شامل‌شدن جزئی). هرگز تایپ مستقیم نام استان در فیلد انجام
    نمی‌شود.
    """
    for attempt in range(max_retries):
        # باز کردن dropdown
        await page.evaluate('''() => {
            const btn = document.querySelector('.ui-select-toggle');
            if (btn) btn.click();
        }''')
        await asyncio.sleep(1.5 + attempt * 0.5)

        clicked = await page.evaluate(r'''(province) => {
            const normalize = (s) => (s || '')
                .replace(/\u064A/g, '\u06CC')
                .replace(/\u0643/g, '\u06A9')
                .replace(/\u200c/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();

            const normProvince = normalize(province);
            const items = Array.from(document.querySelectorAll('.ui-select-choices-row'));
            if (items.length === 0) return false;

            // ۱) تطبیق دقیق پس از نرمال‌سازی
            let target = items.find(el => normalize(el.innerText) === normProvince);
            // ۲) تطبیق شامل‌شدن دوطرفه (آیتم «واحدهاي قضايي مستقر در استان يزد» شامل «يزد»)
            if (!target) {
                target = items.find(el => {
                    const t = normalize(el.innerText);
                    return t && (t.includes(normProvince) || normProvince.includes(t));
                });
            }
            if (target) { target.click(); return true; }
            return false;
        }''', province)

        if clicked:
            await asyncio.sleep(2)
            return True

        logging.warning(
            f"[TN] انتخاب استان '{province}' در تلاش {attempt + 1} ناموفق بود؛ "
            f"دوباره تلاش می‌شود (بدون تایپ در فیلد).")
        await asyncio.sleep(1.5)

    logging.error(f"[TN] انتخاب استان '{province}' پس از {max_retries} تلاش ناموفق ماند.")
    return False


async def _fill_input_value(page, selector: str, value: str, prefix: str = "TN"):
    """پرکردن مقاوم یک input با dispatch رویدادهای AngularJS.

    ⚠ page.evaluate فقط یک آرگومان (غیر از تابع JS) می‌پذیرد — selector و
    value باید در یک دیکشنری بسته‌بندی شوند، وگرنه خطای
    «Page.evaluate() takes from 2 to 3 positional arguments but 4 were given»
    رخ می‌دهد (این باعث می‌شد هیچ فیلدی در «اطلاعات دادنامه/پرونده» پر نشود).
    """
    return await page.evaluate('''({selector, value}) => {
        const inp = document.querySelector(selector);
        if (!inp) return false;
        inp.focus();
        inp.value = value;
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        inp.dispatchEvent(new Event("change", { bubbles: true }));
        try {
            if (typeof angular !== 'undefined') {
                const el = angular.element(inp);
                const ctrl = el.controller('ngModel');
                if (ctrl) { ctrl.$setViewValue(value); ctrl.$render(); }
                const scope = el.scope();
                if (scope) scope.$apply();
            }
        } catch (e) {}
        inp.blur();
        return true;
    }''', {"selector": selector, "value": value})


async def _fill_notice_date_time_robust(page, judge_date: str) -> bool:
    """پرکردن مقاوم فیلد «تاریخ تنظیم دادنامه/قرار» (name="NoticeDateTime").

    ⚠ این فیلد بعد از کلیک «بازیابی» دوباره ساخته می‌شود و persian-datepicker
    با jud-validator است — بدون digest واقعی AngularJS مقدار در مدل ثبت
    نمی‌شود و فیلد در حالت ng-invalid-required می‌ماند و مانع ادامه می‌شود.
    باید در «کلیه قسمت‌های دعاوی اعتراضی» بعد از هر بار بازیابی فراخوانی شود.
    """
    filled = await page.evaluate('''(judgeDate) => {
        let inp = document.querySelector('input[name="NoticeDateTime"]');
        if (!inp) {
            const inps = document.querySelectorAll('input[persian-datepicker-popup]');
            if (inps.length > 0) inp = inps[0];
        }
        if (!inp) return false;

        inp.value = judgeDate;
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        inp.dispatchEvent(new Event("change", { bubbles: true }));

        try {
            if (typeof angular !== "undefined") {
                const scope = angular.element(inp).scope();
                const ctrl = angular.element(inp).controller("ngModel");
                if (ctrl) {
                    ctrl.$setViewValue(judgeDate);
                    ctrl.$render();
                }
                if (scope) {
                    scope.$apply(() => {
                        const key = inp.getAttribute("ng-model");
                        if (key) {
                            const parts = key.split(".");
                            let obj = scope;
                            for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
                            obj[parts[parts.length - 1]] = judgeDate;
                        }
                    });
                }
            }
        } catch (e) {}

        inp.blur();
        return true;
    }''', judge_date)
    if not filled:
        logging.warning("[TN] فیلد تاریخ دادنامه (NoticeDateTime) پس از استعلام پیدا نشد")
    return bool(filled)


async def _click_get_hst(page) -> bool:
    """کلیک دکمه «بازیابی» (#btnGetHst)."""
    return await page.evaluate('''() => {
        const btn = document.querySelector('#btnGetHst');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')


async def _confirm_retrieve_popup(page, wait_sec: float = 1.0, tries: int = 12) -> bool:
    """تایید پاپ‌آپ «بلی» بعد از کلیک بازیابی.

    ⭐ رفع باگ اصلی: نسخه قبلی دکمه «خیر» (cancel) را می‌زد و بازیابی
    داده‌های دادنامه لغو می‌شد! طبق سند راهنما باید «بلی» زده شود:
      «این پاپ اپ نمایش داده می شود و سپس گزینه زیر را بزن — [بلی]»
    """
    for _ in range(tries):
        await asyncio.sleep(wait_sec)
        confirmed = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            // فقط پاپ‌آپ تایید (دارای دکمه confirm) — نه پاپ‌آپ خطا
            const btn = popup.querySelector('button.confirm');
            if (btn && window.getComputedStyle(btn).display !== 'none') { btn.click(); return true; }
            return false;
        }''')
        if confirmed:
            await asyncio.sleep(1)
            return True
    # پاپ‌آپ ظاهر نشد — شاید بازیابی مستقیم شروع شده است
    logging.info("[TN] پاپ‌آپ تایید بازیابی ظاهر نشد — ادامه با فرض شروع مستقیم")
    return False


async def _wait_retrieve_loading(page, bot: Bot, user_id: int, timeout: int = 90):
    """انتظار برای پایان لودینگ بازیابی (progress-bar stripes + نوار افقی).

    «این مرحله بعضی مواقع سریع است و بعضی مواقع ممکن است طول بکشد، باید
    منتظر لودینگ باشی و هرموقع لودینگ محو شد به معنای این است که میتوانی
    ادامه مراحل را بروی»
    """
    # ۱. انتظار کوتاه برای «شروع» لودینگ (شاید با تأخیر ظاهر شود)
    try:
        await page.wait_for_selector(
            '.progress-bar-striped, .progress-bar-animated',
            state='visible', timeout=8000)
    except PlaywrightTimeoutError:
        pass  # لودینگ سریع تمام شده یا بدون stripes
    # ۲. انتظار برای «محو شدن کامل» progress-bar
    try:
        await page.wait_for_selector(
            '.progress-bar-striped, .progress-bar-animated',
            state='detached', timeout=30000)
    except PlaywrightTimeoutError:
        pass
    # ۳. نوار لودینگ افقی بالای صفحه (helper مشترک — متن خطا یا SESSION_EXPIRED برمی‌گرداند)
    return await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=timeout)


async def _handle_post_retrieve_error(page, error_text: str, bot: Bot, user_id: int) -> bool:
    """مدیریت خطای بعد از لودینگ بازیابی.

    طبق سند راهنما:
      - خطای «ورود همزمان» → مدیر باید لاگین مجدد کند (عین کدهای قبلی)
      - خطای دیگر → بستن پاپ‌آپ و استعلام مجدد

    Returns:
        True اگر خطای نشست بود (بعد از تمدید، بازیابی باید تکرار شود)
        False اگر خطای عادی بود (پاپ‌آپ بسته شد، بازیابی تکرار شود)
    """
    logging.warning(f"[TN] خطا بعد از بازیابی: {error_text[:200]}")

    concurrent = await detect_concurrent_login_popup(page)
    if concurrent or _is_session_error_text(error_text):
        logging.error(f"[TN] ورود همزمان بعد از بازیابی! تمدید نشست...")
        await _close_popup(page)
        await handle_session_expired(bot, user_id, page=page)
        return True

    # خطای دیگر → بستن پاپ‌آپ (گزینه «بستن») — استعلام مجدد توسط فراخواننده
    await _close_popup(page)
    await asyncio.sleep(3)
    return False


async def _is_judgment_retrieved(page) -> bool:
    """آیا بازیابی موفق بوده؟ (فیلدهای دادنامه غیرفعال یا فرم جدید رندر شده)"""
    return await page.evaluate('''() => {
        // بعد از بازیابی موفق، JudgeObjectId پر می‌شود و فیلدها disabled می‌شوند
        const judgeNo = document.querySelector('#txtJudgeNo');
        if (judgeNo && judgeNo.disabled) return true;
        // فرم بعد از بازیابی شامل NoticeDateTime است
        const notice = document.querySelector('input[name="NoticeDateTime"]');
        if (notice) return true;
        // رادیوهای ProtestType (حکم/قرار) رندر شده‌اند
        const rdb = document.querySelector('#rdbJudDictum, input[name="rdbProtestType"]');
        if (rdb) return true;
        return false;
    }''')


async def _retrieve_judgment(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    """کلیک «بازیابی» + تایید «بلی» + انتظار لودینگ + مدیریت خطاها (با retry).

    طبق سند راهنما:
      ۱. #btnGetHst کلیک می‌شود
      ۲. پاپ‌آپ تایید ظاهر می‌شود → «بلی»
      ۳. منتظر لودینگ می‌مانیم تا محو شود
      ۴. خطای ورود همزمان → لاگین مجدد + اطلاع مدیر
         خطای دیگر → بستن پاپ‌آپ + مجدد استعلام
    """
    for attempt in range(1, max_retries + 1):
        # اطمینان از نبود پاپ‌آپ باز از قبل
        await _close_popup(page)
        await asyncio.sleep(1)

        # بررسی نشست قبل از تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            await asyncio.sleep(2)

        clicked = await _click_get_hst(page)
        if not clicked:
            logging.warning(f"[TN] دکمه بازیابی (#btnGetHst) پیدا نشد — تلاش {attempt}")
            await asyncio.sleep(2)
            continue

        # پاپ‌آپ تایید → «بلی» (نه «خیر»!)
        await _confirm_retrieve_popup(page)

        # انتظار لودینگ
        loading_result = await _wait_retrieve_loading(page, bot, user_id)
        if loading_result == "SESSION_EXPIRED":
            logging.warning(f"[TN] نشست حین لودینگ بازیابی منقضی شد — تلاش {attempt}")
            continue
        if loading_result:
            # خطای سامانه بعد از لودینگ
            is_session = await _handle_post_retrieve_error(page, loading_result, bot, user_id)
            if is_session:
                continue
            # خطای عادی → پاپ‌آپ بسته شد → استعلام مجدد
            continue

        # بررسی خطای پاپ‌آپ بعد از لودینگ (بدون بستن خودکار)
        popup_text = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const icon = popup.querySelector('.sa-icon.sa-success');
            if (icon && window.getComputedStyle(icon).display !== 'none') return null;
            const h2 = popup.querySelector('h2');
            const p = popup.querySelector('p');
            return [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim() || null;
        }''')
        if popup_text:
            is_session = await _handle_post_retrieve_error(page, popup_text, bot, user_id)
            if is_session:
                continue
            # خطای عادی → بسته شد → استعلام مجدد
            continue

        # بررسی موفقیت
        if await _is_judgment_retrieved(page):
            logging.info(f"[TN] بازیابی دادنامه موفق (تلاش {attempt})")
            return True

        logging.warning(f"[TN] نشانه موفقیت بازیابی یافت نشد — تلاش {attempt}")
        await asyncio.sleep(3)

    return False


async def _clear_related_cases(page, bot: Bot, user_id: int, max_deletions: int = 30):
    """حذف ردیف‌های جدول «پرونده‌های مرتبط» (در صورت نمایش).

    طبق سند راهنما: «ضمنا اگر این جدول نمایش داده شده بود، باید اقدامات
    بعدی را انجام بدی» — دکمه‌های حذف ردیف (deleteSingleRelatedCase) و
    «حذف همه» (deleteAllRelatedCase) در جدول وجود دارند.
    اول «حذف همه» زده می‌شود؛ اگر نبود، ردیف‌ها یکی‌یکی حذف می‌شوند.
    """
    # آیا جدول پرونده‌های مرتبط ردیف دارد؟
    row_count = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll('tr[ng-repeat*="theRelatedCaseList"]'));
        return rows.length;
    }''')
    if row_count == 0:
        logging.info("[TN] جدول پرونده‌های مرتبط خالی/غیرموجود — رد شد")
        return 0

    logging.info(f"[TN] جدول پرونده‌های مرتبط {row_count} ردیف دارد — حذف همه")

    # ۱. «حذف همه»
    deleted_all = await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button[ng-click*="deleteAllRelatedCase"]'));
        const btn = btns.find(b => !b.disabled);
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if deleted_all:
        await asyncio.sleep(3)
        # بستن پاپ‌آپ احتمالی تایید
        await _close_popup(page)
        await asyncio.sleep(1)

    # ۲. فال‌بک: حذف ردیف‌های باقیمانده یکی‌یکی
    deleted = 0
    for _ in range(max_deletions):
        remaining = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('tr[ng-repeat*="theRelatedCaseList"]'));
            return rows.length;
        }''')
        if remaining == 0:
            break
        clicked = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('tr[ng-repeat*="theRelatedCaseList"]'));
            if (rows.length === 0) return false;
            const btn = rows[0].querySelector('button[ng-click*="deleteSingleRelatedCase"]');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            break
        deleted += 1
        await asyncio.sleep(1.5)

    logging.info(f"[TN] پرونده‌های مرتبط حذف شدند (حذف‌همه={deleted_all}, تک‌تک={deleted})")
    return deleted


async def _click_select_all_related(page):
    """کلیک چک‌باکس «انتخاب همه» (#chkSelectAll) — فقط اگر نمایش داده شود.

    طبق سند راهنما: «باید گزینه زیر را بزنی و اگر نمایش نداد، این مرحله
    را اسکیپ میکنی»
    """
    clicked = await page.evaluate('''() => {
        const chk = document.querySelector('#chkSelectAll');
        if (chk && chk.offsetParent !== null && !chk.checked) {
            chk.click();
            return true;
        }
        return false;
    }''')
    if clicked:
        logging.info("[TN] چک‌باکس «انتخاب همه» (#chkSelectAll) کلیک شد")
        await asyncio.sleep(1)
    else:
        logging.info("[TN] چک‌باکس #chkSelectAll نمایش داده نشد — این مرحله اسکیپ شد")
    return clicked


async def _fill_judge_date_field(page, judge_date: str) -> bool:
    """پرکردن فیلد «تاریخ تنظیم دادنامه» (اولین persian-datepicker صفحه).

    idempotent است — هم قبل از انتخاب استان و هم بعد از آن (رفع خالی‌شدن
    احتمالی فیلد پس از تعامل دراپ‌داون) قابل فراخوانی است.
    """
    filled = await page.evaluate('''(judgeDate) => {
        const inps = document.querySelectorAll('input[persian-datepicker-popup]');
        if (inps.length > 0) {
            const inp = inps[0];
            inp.value = judgeDate;
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            try {
                if (typeof angular !== 'undefined') {
                    const ctrl = angular.element(inp).controller('ngModel');
                    if (ctrl) { ctrl.$setViewValue(judgeDate); ctrl.$render(); }
                }
            } catch (e) {}
            return true;
        }
        return false;
    }''', judge_date)
    if not filled:
        logging.warning("[TN] فیلد تاریخ تنظیم دادنامه (datepicker اول) پیدا نشد")
    return bool(filled)


async def _fill_judge_info_step(page, data: dict, bot: Bot, user_id: int,
                                is_prosecutor: bool = False) -> bool:
    """مرحله «اطلاعات دادنامه/قرار» — کامل طبق سند راهنما.

    ۱. شماره دادنامه (#txtJudgeNo)
    ۲. شماره پرونده (#txtReferingCaseNo)
    ۳. تاریخ تنظیم دادنامه (persian-datepicker)
    ۴. استان (خادم مرتبط — مانند لایحه)
    ۵. «بازیابی» → «بلی» → لودینگ → مدیریت خطاها
    ۶. پس از بازیابی:
       - تاریخ دادنامه مجدداً (NoticeDateTime مقاوم)
       - اگر «قرار»: #rdbJudDictum سپس #rdbModifiedByUserOk
       - مبلغ (ModifyByUserPenaltyAmount) — مبلغ کاربر یا ۱
       - اگر اعسار: #rdbIsMoserByPetition
       - جدول پرونده‌های مرتبط → حذف همه + #chkSelectAll (در صورت نمایش)
    """
    case_type = data.get("case_type", "")
    judge_no = data.get("tn_judge_no", "")
    file_no = data.get("tn_file_no", "")
    judge_date = data.get("tn_judge_date", "")
    province = data.get("tn_province", "")
    doc_type = data.get("tn_doc_type", "حکم")
    amount = data.get("tn_amount", 0) or 0
    insolvency = data.get("tn_insolvency", False)

    # ── ورود به step «اطلاعات دادنامه/قرار» ──
    # ⚠ نکته کارفرما (۱۴۰۵/۰۶/۲۰): «اعاده دادرسی کیفری» بر خلاف بقیه انواع
    # دعوی، step آن «اطلاعات پرونده» است نه «اطلاعات دادنامه».
    if is_prosecutor:
        judge_info_step = "اطلاعات قرار"
    elif case_type == "اعاده دادرسی کیفری":
        judge_info_step = "اطلاعات پرونده"
    else:
        judge_info_step = "اطلاعات دادنامه"
    await _click_step_label(page, judge_info_step, bot, user_id)
    await resilient_sleep(page, 4, bot, user_id)

    # ۱. شماره دادنامه
    await _fill_input_value(page, "#txtJudgeNo", judge_no)
    await asyncio.sleep(1)

    # ۲. شماره پرونده
    await _fill_input_value(page, "#txtReferingCaseNo", file_no)
    await asyncio.sleep(1)

    # ۳. تاریخ تنظیم دادنامه (فیلد persian-datepicker اول)
    await _fill_judge_date_field(page, judge_date)
    await asyncio.sleep(1)

    # ۴. استان — مانند بخش لایحه (خادم مرتبط)
    province_selected = await _select_province(page, province, bot, user_id)
    if not province_selected:
        await bot.send_message(
            ADMIN_ID,
            f"❌ [TN] انتخاب استان '{province}' برای کاربر {user_id} ناموفق.")
        raise TajdidFatalError(
            f"استان «{province}» در لیست سامانه پیدا نشد. لطفاً نام استان را بررسی و مجدداً اقدام نمایید.")
    await resilient_sleep(page, 3, bot, user_id)

    # ۴.ب — «بعد تاریخ تنظیم دادنامه را وارد می کنی» (سند ۱۴۰۵/۰۶):
    # پس از انتخاب استان، تاریخ تنظیم دادنامه «مجدداً» وارد می‌شود —
    # تعامل با دراپ‌داون خادم مرتبط ممکن است فیلد تاریخ را در آنگولار خالی
    # کند؛ refilling بی‌ضرر است و جلوی خطای required در بازیابی را می‌گیرد.
    await _fill_judge_date_field(page, judge_date)
    await asyncio.sleep(1)

    # ۵. «بازیابی» → «بلی» → لودینگ → مدیریت خطاها
    retrieved = await _retrieve_judgment(page, bot, user_id)
    if not retrieved:
        raise TajdidFatalError(
            "بازیابی اطلاعات دادنامه پس از چند تلاش ناموفق بود. "
            "شماره دادنامه/پرونده/تاریخ/استان را بررسی کنید.")

    # ۶. پس از بازیابی — تاریخ مجدداً (فرم جدید)
    await asyncio.sleep(2)
    await _fill_notice_date_time_robust(page, judge_date)
    await asyncio.sleep(1)

    if not is_prosecutor:
        # ── حکم/قرار ──
        # «اگر گزینه حکم، کاربر انتخاب کرده بود که نیازی به اقدام خاصی نداری
        #  اما اگر قرار را انتخاب کرده بود، حتما این گزینه را انتخاب کن»
        if doc_type == "قرار":
            await page.evaluate('''() => {
                const rdb = document.querySelector('#rdbJudDictum, input[name="rdbProtestType"][value="2"]');
                if (rdb) rdb.click();
            }''')
            await asyncio.sleep(1)

        # «بعد گزینه زیر» — رادیوی ModifiedByUser (برای فعال شدن فیلد مبلغ)
        await page.evaluate('''() => {
            const rdb = document.querySelector('#rdbModifiedByUserOk, input[name="ModifiedByUser"][value="1"]');
            if (rdb) rdb.click();
        }''')
        await asyncio.sleep(1)

        # ── مبلغ ──
        # «اگر کاربر مبلغ را وارد کرده بود، مبلغ را در فیلد زیر وارد میکنی و
        #  اگر مبلغ نزده بود و سایر گزینه را انتخاب کرده بود، عدد 1 را وارد فیلد کن»
        amount_str = str(amount) if amount > 0 else "1"
        await page.evaluate('''(val) => {
            const inp = document.querySelector('input[ng-model*="ModifyByUserPenaltyAmount"]');
            if (inp && !inp.disabled) {
                inp.focus();
                inp.value = val;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                try {
                    if (typeof angular !== 'undefined') {
                        const ctrl = angular.element(inp).controller('ngModel');
                        if (ctrl) { ctrl.$setViewValue(val); ctrl.$render(); }
                    }
                } catch (e) {}
            }
        }''', amount_str)
        await asyncio.sleep(1)

        # ── اعسار ──
        # «اگر کاربر گزینه اعسار را انتخاب کرده بود، گزینه زیر را میزنی، اگر نه اسکیپ کن»
        if insolvency:
            await page.evaluate('''() => {
                const rdb = document.querySelector('#rdbIsMoserByPetition, input[name="moser"][value="2"]');
                if (rdb && !rdb.disabled) rdb.click();
            }''')
            await asyncio.sleep(1)

    # ── جدول پرونده‌های مرتبط (در صورت نمایش) + «انتخاب همه» ──
    await _clear_related_cases(page, bot, user_id)
    await _click_select_all_related(page)

    return True


# ══════════════════════════════════════════════════════════════════════════════
# مدیریت لیست اشخاص (nav-list)
# ══════════════════════════════════════════════════════════════════════════════

_NAV_ITEMS_JS = '''
() => {
    const items = Array.from(document.querySelectorAll('div[ng-repeat*="navListCtrl.dataSource"]'));
    const visible = items.filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    });
    return visible.map((el, idx) => {
        const infoDiv = el.querySelector('.info');
        const text = infoDiv ? infoDiv.innerText.trim() : '';
        // حذف شماره ردیف از ابتدا (مثل «1- »)
        const cleanName = text.replace(/^\\d+\\s*\\-\\s*/, '').trim();
        return {index: idx, name: cleanName, raw: text};
    }).filter(n => n.name);
}
'''


async def _get_visible_nav_items(page) -> list:
    """استخراج افراد بخش فعال (nav-list مرئی) — [{'index', 'name'}, ...]"""
    try:
        return await page.evaluate(_NAV_ITEMS_JS)
    except Exception as e:
        logging.error(f"[TN] خطا در استخراج nav-list: {e}")
        return []


async def _extract_persons_from_navlist(page) -> list:
    """استخراج لیست نام‌ها از nav-list (سازگاری با کد قبلی)."""
    return await _get_visible_nav_items(page)


async def _clear_nav_list_persons(page, max_removals: int = 50) -> int:
    """حذف «تمام» افراد موجود در nav-list بخش فعال.

    طبق سند راهنما (مرحله تجدیدنظرخواه):
      «در فیلد بالا نام هایی اورده می شود که باید همه ان ها را حذف کنی با
       انتخاب گزینه زیر به ازای هر نامی که وجود دارد تا این فایل خالی شود»
    ⭐ باگ نسخه قبلی: در حالت عادی، افراد پیش‌فرض پرونده (طرفین دادنامه
    بازیابی‌شده) هرگز پاک نمی‌شدند و در کنار افراد کاربر ثبت می‌شدند.
    """
    removed = 0
    for _ in range(max_removals):
        items = await _get_visible_nav_items(page)
        if not items:
            break
        clicked = await page.evaluate('''() => {
            const items = Array.from(document.querySelectorAll('div[ng-repeat*="navListCtrl.dataSource"]'))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
            if (items.length === 0) return false;
            const del = items[0].querySelector('.btn-danger');
            if (del) { del.click(); return true; }
            return false;
        }''')
        if not clicked:
            logging.warning("[TN] دکمه حذف nav-list پیدا نشد — توقف پاک‌سازی")
            break
        removed += 1
        await asyncio.sleep(1.2)
    logging.info(f"[TN] nav-list پاک‌سازی شد ({removed} نفر حذف شد)")
    return removed


async def _remove_unselected_persons(page, selected_names: list, bot: Bot, user_id: int):
    """حذف افراد انتخاب‌نشده از لیست سامانه (حالت استعلام افراد پرونده).

    فقط نام‌هایی که کاربر در ربات انتخاب کرده در سامانه نگه داشته می‌شوند.
    """
    max_removals = 50  # جلوگیری از حلقه بی‌نهایت
    normalized_selected = [_normalize_fa(n) for n in (selected_names or [])]

    for _ in range(max_removals):
        current_names = await _get_visible_nav_items(page)
        if not current_names:
            logging.info("[TN] لیست افراد خالی شد — حذف تمام شد.")
            break

        # پیدا کردن اولین آیتمی که در لیست انتخاب‌شده نیست
        to_remove = None
        for item in current_names:
            if _normalize_fa(item["name"]) not in normalized_selected:
                to_remove = item
                break

        if to_remove is None:
            logging.info(f"[TN] همه افراد انتخاب‌شده باقی ماندند ({len(selected_names)} نفر).")
            break

        # حذف آیتم با کلیک روی دکمه btn-danger همان ردیف (با تطبیق متن)
        clicked = await page.evaluate('''(targetName) => {
            const norm = (s) => (s || '')
                .replace(/\\u064A/g, '\\u06CC').replace(/\\u0643/g, '\\u06A9')
                .replace(/\\u200c/g, '').replace(/\\s+/g, ' ').trim();
            const items = Array.from(document.querySelectorAll('div[ng-repeat*="navListCtrl.dataSource"]'))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
            for (const item of items) {
                const infoDiv = item.querySelector('.info');
                const text = infoDiv ? infoDiv.innerText.trim() : '';
                const cleanName = text.replace(/^\\d+\\s*\\-\\s*/, '').trim();
                if (norm(cleanName) === norm(targetName)) {
                    const del = item.querySelector('.btn-danger');
                    if (del) { del.click(); return true; }
                }
            }
            return false;
        }''', to_remove["name"])

        if clicked:
            logging.info(f"[TN] حذف '{to_remove['name']}' از لیست سامانه.")
            await asyncio.sleep(1.5)
        else:
            logging.warning(f"[TN] دکمه حذف برای '{to_remove['name']}' یافت نشد.")
            break


async def _add_persons_to_section(page, persons: list, role_label: str,
                                  bot: Bot, user_id: int,
                                  person_role: str = ""):
    """افزودن اشخاص یک بخش (تجدیدنظرخواه/خوانده/شهود) — مانند اظهارکننده اظهارنامه.

    اشخاص وکیل اینجا اضافه نمی‌شوند (در step جداگانه «وكيل»).
    """
    for idx, person in enumerate(persons or []):
        ptype = person.get("person_type", "شخص حقیقی")
        if ptype == "وکیل":
            continue  # وکیل در step «وكيل» اضافه می‌شود

        await _click_add_section_btn(page, bot, user_id)
        await resilient_sleep(page, 3, bot, user_id)

        if ptype == "شخص حقوقی":
            await _fill_legal_person(page, person, bot, user_id,
                                     person_role=person_role or role_label,
                                     person_index=idx)
        else:
            await _fill_real_person(page, person.get("national_id", ""), bot, user_id,
                                    person_role=person_role or role_label,
                                    person_index=idx)
        await resilient_sleep(page, 10, bot, user_id)
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
# مراحل «شرح»، «دلايل»، «جهات» و «ثبت موقت»
# ══════════════════════════════════════════════════════════════════════════════

async def _fill_sharh_section(page, tn_text: str, tn_text_html: str, bot: Bot, user_id: int):
    """مرحله «شرح» — پر کردن ادیتور متن مانند اظهارنامه (ta-bind + H3).

    ⭐ باگ نسخه قبلی: step به نام «متن» کلیک می‌شد که در این فرم وجود ندارد
    (نام صحیح طبق سند راهنما «شرح» است) و ادیتور با سلکتور حدسی
    (.note-editor) پر می‌شد.
    """
    await _click_step_label(page, "شرح", bot, user_id)
    await resilient_sleep(page, 4, bot, user_id)

    stored_html = tn_text_html or ""
    html_content = stored_html if stored_html else _text_to_editor_html(tn_text)

    await page.evaluate('''(html) => {
        const editor = document.querySelector('[contenteditable="true"][ta-bind]')
            || document.querySelector('[contenteditable="true"]');
        if (editor) {
            editor.focus();
            editor.innerHTML = html;
            editor.dispatchEvent(new Event("input", { bubbles: true }));
            editor.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }''', html_content)
    await resilient_sleep(page, 2, bot, user_id)

    # اعمال H3 (الگوی اظهارنامه)
    await page.evaluate('''() => {
        const editor = document.querySelector('[contenteditable="true"][ta-bind]')
            || document.querySelector('[contenteditable="true"]');
        if (editor) {
            const range = document.createRange();
            range.selectNodeContents(editor);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
            editor.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        }
    }''')
    await asyncio.sleep(0.5)
    await page.evaluate('''() => {
        const btn = document.querySelector('button[name="h3"]') ||
            Array.from(document.querySelectorAll('button')).find(b => b.title === "Heading 3");
        if (btn && !btn.disabled) btn.click();
    }''')
    await asyncio.sleep(0.5)


async def _fill_dalael_section(page, extra_text: str, bot: Bot, user_id: int):
    """مرحله «دلايل» — سایر دلایل کاربر (#chk1 + #ReasonAttach1).

    طبق سند راهنما:
      «اگر کاربر، سایر دلایل خود را در ربات وارد کرده بود، گزینه زیر را
       میزنی و در فیلد مربوطه متن را وارد میکنی و اگر نداشت، اسکیپ کن»
    ⭐ باگ نسخه قبلی: این مرحله کلاً وجود نداشت و متن «توضیحات جداگانه»
    کاربر هرگز در سامانه درج نمی‌شد.
    """
    await _click_step_label(page, "دلايل", bot, user_id)
    await resilient_sleep(page, 4, bot, user_id)

    if not extra_text:
        logging.info("[TN] دلايل: سایر دلایلی از کاربر ثبت نشده — این مرحله اسکیپ شد")
        return

    # کلیک چک‌باکس «سایر دلایل» (#chk1 / item.IsChecked)
    checked = await page.evaluate('''() => {
        const chk = document.querySelector('#chk1');
        if (chk && !chk.checked) { chk.click(); return true; }
        return chk ? true : false;
    }''')
    if not checked:
        logging.warning("[TN] چک‌باکس سایر دلایل (#chk1) پیدا نشد")
    await asyncio.sleep(1)

    # درج متن در textarea دلایل (#ReasonAttach1) — مقاوم با AngularJS
    filled = await page.evaluate('''(val) => {
        const ta = document.querySelector('#ReasonAttach1, textarea[ng-model*="ReasonAttach"]');
        if (!ta) return false;
        ta.focus();
        ta.value = val;
        ta.dispatchEvent(new Event("input", { bubbles: true }));
        ta.dispatchEvent(new Event("change", { bubbles: true }));
        try {
            if (typeof angular !== 'undefined') {
                const el = angular.element(ta);
                const ctrl = el.controller('ngModel');
                if (ctrl) { ctrl.$setViewValue(val); ctrl.$render(); }
                const scope = el.scope();
                if (scope) scope.$apply();
            }
        } catch (e) {}
        return true;
    }''', extra_text)
    if filled:
        logging.info("[TN] متن سایر دلایل در #ReasonAttach1 درج شد")
    else:
        logging.warning("[TN] فیلد متن دلایل (#ReasonAttach1) پیدا نشد")
    await asyncio.sleep(1)


async def _fill_jihat_section(page, reasons, case_type: str, bot: Bot, user_id: int):
    """مرحله «جهات» (فقط اعاده دادرسی مدنی/کیفری) — انتخاب چک‌باکس جهات.

    طبق سند راهنما:
      «در سامانه هم باید وارد بخش زیر شوی [جهات] و هر گزینه ای که انتخاب
       کرده بود مانند کدهای جدول بالا روی گزینه های زیر کلیک میکنی جهت
       انتخاب و سپس ادامه فرایند»
    ⭐ باگ نسخه قبلی: کلیدهای متن جهات در هندلر با سناریو mismatch بود
    و هیچ چک‌باکسی هرگز کلیک نمی‌شد.
    """
    ground_indices = resolve_ground_indices(reasons, case_type)
    if not ground_indices:
        logging.info("[TN] جهتی برای انتخاب ثبت نشده — این مرحله اسکیپ شد")
        return

    await _click_step_label(page, "جهات", bot, user_id)
    await resilient_sleep(page, 4, bot, user_id)

    for idx in ground_indices:
        chk_id = f"#chk{idx}"
        clicked = await page.evaluate('''(chkId) => {
            const chk = document.querySelector(chkId);
            if (chk && !chk.checked) { chk.click(); return true; }
            return chk ? true : false;
        }''', chk_id)
        if clicked:
            ground_text = get_grounds_list(case_type)[idx] if idx < len(get_grounds_list(case_type)) else ""
            logging.info(f"[TN] جهت #{idx} انتخاب شد: {ground_text[:60]}...")
        else:
            logging.warning(f"[TN] چک‌باکس جهت {chk_id} پیدا نشد")
        await asyncio.sleep(1)


# ══════════════════════════════════════════════════════════════════════════════
# «ثبت موقت» + کد رهگیری — الگوی اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════

async def _raise_fatal_tn_save_error(bot: Bot, user_id: int, error_text: str):
    """خطای «ثبت موقت» → پیام به کاربر + TajdidFatalError (الگوی اظهارنامه)."""
    await bot.send_message(
        user_id,
        f"⚠️ *خطا در ثبت موقت {('دعاوی اعتراضی')}*:\n\n«{error_text}»\n\n"
        "فرآیند متوقف شد. لطفاً به مدیریت اطلاع دهید.")
    raise TajdidFatalError(error_text)


async def _click_save_temp(page, bot: Bot, user_id: int, max_retries: int = 5):
    """کلیک «ثبت موقت» (#btnSave) + مدیریت هشدارها/خطاها (الگوی اظهارنامه).

    «و اخر کار ثبت موقت را میزنی و اطلاعات را سیو و برای مدیر میفرستی
     مانند اظهارنامه و بعد ادامه مراحل. بعد از گزینه ثبت همان الارم ها
     و خطا ها و اخذ کدرهگیری و همه موارد را رعایت کن»
    """
    for attempt in range(max_retries):
        # بررسی session expiry قبل از هر تلاش
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[TN] session renewed before save attempt {attempt + 1}")
            continue

        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnSave');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "ثبت موقت", bot, user_id)

        await asyncio.sleep(5)

        # منتظر ناپدید شدن لودینگ — متن خطای واقعی یا SESSION_EXPIRED
        loading_result = await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)
        if loading_result == "SESSION_EXPIRED":
            logging.info(f"[TN] session renewed after save attempt {attempt + 1} (during loading wait)")
            continue
        elif loading_result:
            await _raise_fatal_tn_save_error(bot, user_id, loading_result)

        # بررسی session expiry بعد از ثبت
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info(f"[TN] session renewed after save attempt {attempt + 1}")
            continue

        await asyncio.sleep(5)

        # بررسی پاپ‌آپ موفقیت / خطا
        result = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const h2Text = h2 ? h2.innerText : '';
            if (h2Text.includes("منقضی") || h2Text.includes("منقضي") ||
                h2Text.includes("رایانه ای دیگر") || h2Text.includes("اعتبار ورود")) {
                return "session_expired";
            }
            const icon = popup.querySelector('.sa-icon.sa-success');
            if (icon && window.getComputedStyle(icon).display !== 'none') {
                return "success";
            }
            const p = popup.querySelector('p');
            return "error:" + [h2Text, p ? p.innerText : ''].filter(Boolean).join(' - ');
        }''')

        if result == "session_expired":
            logging.warning(f"[TN] session expiry detected in popup after save")
            await _close_popup(page)
            await handle_session_expired(bot, user_id, page=page)
            continue

        if result == "success":
            await _close_success_popup(page)
            return

        if result and result.startswith("error:"):
            error_text = result[6:].strip()
            if _is_session_error_text(error_text):
                await handle_session_expired(bot, user_id, page=page)
                continue
            await _raise_fatal_tn_save_error(bot, user_id, error_text)

        await asyncio.sleep(5)

    timeout_msg = ("سامانه پس از چند تلاش، پاسخ قطعی (موفقیت یا خطا) برای "
                   "«ثبت موقت» دعاوی اعتراضی نداد.")
    await _raise_fatal_tn_save_error(bot, user_id, timeout_msg)


async def _extract_bill_no(page) -> str:
    """استخراج کد رهگیری پس از ثبت موقت (الگوی اظهارنامه + فال‌بک‌ها)."""
    try:
        val = await page.evaluate('''() => {
            // ۱. فیلدهای مستقیم
            for (const sel of ['#txtBillNo', '#txtPetitionNo', '#txtTrackingCode']) {
                const inp = document.querySelector(sel);
                if (inp && inp.value && inp.value.trim()) return inp.value.trim();
            }
            // ۲. المان‌های متنی ng-model/ng-bind
            const el = document.querySelector('[ng-model*="BillNo"], [ng-bind*="BillNo"]');
            if (el) {
                const t = (el.innerText || el.textContent || '').trim();
                if (t && /\\d{5,}/.test(t)) return t;
            }
            // ۳. متن پاپ‌آپ موفقیت (شماره رهگیری)
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) {
                const texts = Array.from(popup.querySelectorAll('h2, p'))
                    .map(el => el.innerText || '').join(' ');
                const m = texts.match(/\\d{6,}/);
                if (m) return m[0];
            }
            return "";
        }''')
        return val or ""
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# «آماده‌سازی» — تایید اطلاعات (الگوی اظهارنامه)
# ══════════════════════════════════════════════════════════════════════════════

async def _click_preparation(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    """کلیک «تایید اطلاعات» در مرحله آماده‌سازی جهت دریافت وجه.

    طبق سند راهنما:
      ۱. گزینه «تایید اطلاعات» زده می‌شود
      ۲. پاپ‌آپ ظاهر می‌شود → دکمه «تایید اطلاعات» (confirm)
      ۳. به لودینگ توجه داشته باش و صبر کن تمام شود
      ۴. اگر پیام موفقیت → «بستن»
      ۵. اگر خطای ورود همزمان → مدیر برای لاگین مجدد مطلع شود
      ۶. اگر خطای دیگر → دوباره «تایید اطلاعات»
    """
    for attempt in range(max_retries):
        await _close_popup(page)
        await asyncio.sleep(2)

        # کلیک دکمه «تایید اطلاعات» (setPetitionToReadyForPaymentState)
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnCalculateCash');
            if (btn && !btn.disabled) { btn.click(); return true; }
            const btns = Array.from(document.querySelectorAll('button[ng-click*="setPetitionToReadyForPaymentState"]'));
            if (btns.length > 0) { btns[0].click(); return true; }
            const all = Array.from(document.querySelectorAll('button'));
            const tb = all.find(b => b.innerText && b.innerText.trim().includes("تایید اطلاعات") && !b.disabled);
            if (tb) { tb.click(); return true; }
            return false;
        }''')

        if not clicked:
            logging.warning(f"[TN] دکمه تایید اطلاعات (preparation) پیدا نشد — تلاش {attempt + 1}")

        await asyncio.sleep(40 if attempt > 0 else 12)

        # پاپ‌آپ تایید — باید «تایید اطلاعات» را بزنیم
        confirm_clicked = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const h2 = popup.querySelector('h2');
            if (h2 && (h2.innerText.includes("آیا اطلاعات") || h2.innerText.includes("تایید"))) {
                const btn = popup.querySelector('button.confirm');
                if (btn) { btn.click(); return true; }
            }
            return false;
        }''')
        if confirm_clicked:
            await asyncio.sleep(5)
            # انتظار لودینگ بعد از تایید
            await wait_for_horizontal_loading_bar(page, bot, user_id, timeout=60)

        # بررسی پاپ‌آپ موفقیت — «بستن»
        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const h2 = popup.querySelector('h2');
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none' &&
                   h2 && (h2.innerText.includes("آماده سازي") || h2.innerText.includes("بررسی و تایید") ||
                          h2.innerText.includes("تاييد"));
        }''')

        if success:
            await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const btn = popup.querySelector('button.confirm');
                    if (btn) btn.click();
                }
            }''')
            await asyncio.sleep(2)
            logging.info("[TN] آماده‌سازی (تایید اطلاعات) موفق")
            return True

        # خطا؟
        error_text = await _get_error_text(page, click_confirm=False)
        if error_text:
            if _is_session_error_text(error_text):
                logging.warning("[TN] ورود همزمان در آماده‌سازی — تمدید نشست")
                await handle_session_expired(bot, user_id, page=page)
                await asyncio.sleep(3)
                continue
            logging.warning(f"[TN] خطا در آماده‌سازی (تلاش {attempt + 1}): {error_text[:150]}")
            await _close_popup(page)
            await asyncio.sleep(10)
            continue

        # بستن هر پاپ‌آپ دیگر و تلاش مجدد
        await _close_popup(page)
        await asyncio.sleep(20)
        await _close_success_popup(page)

    return False


# ══════════════════════════════════════════════════════════════════════════════
# «هزینه» — جدول هزینه + فرمول محاسبه (طبق سند راهنما)
# ══════════════════════════════════════════════════════════════════════════════

async def _calculate_cost(page, bot: Bot, user_id: int, max_retries: int = 3) -> dict:
    """محاسبه هزینه دعاوی اعتراضی — پارس جدول + فرمول سند راهنما.

    فرمول:
      ۱. عدد «جمع کل هزینه» جدول (td سبز) یادداشت می‌شود
      ۲. جمع ۵ ردیف: اوراق دادخواست + افزودن پیوست + ثبت اطلاعات اشخاص
         + تنظیم دادخواست + خدمات الکترونیک قضایی
      ۳. + ۵۰ ریال
      ۴. + جمع کل → رند به بالا (۱۰,۰۰۰ ریال)

    اگر جدول نمایش داده نشد:
      - خطای ورود همزمان → مدیر مطلع می‌شود (لاگین مجدد)
      - خطای دیگر → «محاسبه هزینه دادرسی و تعرفه خدمات» کلیک و انتظار
    """
    for attempt in range(max_retries):
        await _close_popup(page)
        await asyncio.sleep(2)

        # بررسی جدول هزینه
        table_visible = await page.evaluate('''() => {
            const tds = Array.from(document.querySelectorAll('table td.color-green, table td.color-red'));
            return tds.length > 0;
        }''')

        if not table_visible:
            # خطای ورود همزمان؟
            concurrent = await detect_concurrent_login_popup(page)
            if concurrent:
                logging.error("[TN] ورود همزمان در بخش هزینه — تمدید نشست")
                await handle_session_expired(bot, user_id, page=page)
                await asyncio.sleep(3)
                continue

            # کلیک دکمه «محاسبه هزینه دادرسی و تعرفه خدمات»
            await page.evaluate('''() => {
                const btn = document.querySelector('#btnCalculateCash');
                if (btn && !btn.disabled) { btn.click(); return true; }
                const btns = Array.from(document.querySelectorAll('button[ng-click*="paymentCost"]'));
                if (btns.length > 0) { btns[0].click(); return true; }
                const all = Array.from(document.querySelectorAll('button'));
                const tb = all.find(b => b.innerText && b.innerText.includes("محاسبه هزینه دادرسی") && !b.disabled);
                if (tb) { tb.click(); return true; }
                return false;
            }''')
            await asyncio.sleep(40)

            # بستن پاپ‌آپ خطا (اگر ظاهر شد) و کلیک مجدد
            error_popup_closed = await page.evaluate('''() => {
                const popup = document.querySelector('.sweet-alert.showSweetAlert');
                if (popup) {
                    const h2 = popup.querySelector('h2');
                    if (h2 && !h2.innerText.includes("آماده")) {
                        const closeBtn = popup.querySelector('button.confirm, button.btn-info');
                        if (closeBtn) { closeBtn.click(); return true; }
                    }
                }
                const alertEl = document.querySelector('.alert-danger');
                if (alertEl && alertEl.offsetParent !== null) {
                    const closeBtns = Array.from(document.querySelectorAll('button'));
                    const c = closeBtns.find(b => b.innerText && b.innerText.trim() === "بستن");
                    if (c) { c.click(); return true; }
                }
                return false;
            }''')
            if error_popup_closed:
                logging.info("[TN] پاپ‌آپ خطا بسته شد — کلیک مجدد دکمه محاسبه هزینه")
                await asyncio.sleep(3)
                await page.evaluate('''() => {
                    const btn = document.querySelector('#btnCalculateCash');
                    if (btn && !btn.disabled) { btn.click(); return; }
                    const btns = Array.from(document.querySelectorAll('button[ng-click*="paymentCost"]'));
                    if (btns.length > 0) { btns[0].click(); return; }
                    const all = Array.from(document.querySelectorAll('button'));
                    const tb = all.find(b => b.innerText && b.innerText.includes("محاسبه هزینه دادرسی") && !b.disabled);
                    if (tb) { tb.click(); }
                }''')
                await asyncio.sleep(40)

        await _close_popup(page)

        # استخراج داده‌های جدول هزینه
        cost_data = await page.evaluate('''() => {
            // جمع کل هزینه (td سبز)
            const greenTds = Array.from(document.querySelectorAll('table td.color-green'));
            let costSum = 0;
            for (const td of greenTds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 0) {
                    costSum = parseInt(text);
                }
            }

            // ردیف‌ها: [برچسب، مبلغ]
            const labels = [];
            const rows = Array.from(document.querySelectorAll('table tr'));
            for (const row of rows) {
                const tds = Array.from(row.querySelectorAll('td'));
                if (tds.length >= 3) {
                    const label = tds[1].innerText.trim();
                    const amount = tds[2].innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                    if (label && /^[0-9]+$/.test(amount) && parseInt(amount) > 0) {
                        labels.push({label, amount: parseInt(amount)});
                    }
                }
            }

            // جمع ردیف‌های قرمز (مبالغ اصلی)
            const redTds = Array.from(document.querySelectorAll('table td.color-red'));
            let rowSum = 0;
            for (const td of redTds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '').replace(/\\s/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 0) {
                    rowSum += parseInt(text);
                }
            }

            // مبلغ اصلی: جمع کل جدول (اگر خالی بود، جمع ردیف‌ها)
            let mainTotal = costSum > 0 ? costSum : rowSum;

            return {
                costSum: costSum,
                mainTotal: mainTotal,
                rowSum: rowSum,
                labels: labels
            };
        }''')

        if cost_data and cost_data.get("mainTotal", 0) > 0:
            main_total = cost_data["mainTotal"]
            labels = cost_data.get("labels", [])

            logging.info(f"[TN] cost data: mainTotal={main_total}, labels={labels}")

            # ── جمع ردیف‌های فرمول (با نرمال‌سازی برچسب‌ها) ──
            def _norm_label(s):
                return (_normalize_fa(s)
                        .replace(" ", ""))

            formula_sum = 0
            matched_rows = []
            for item in labels:
                label_norm = _norm_label(item.get("label", ""))
                for target in TN_COST_FORMULA_LABELS:
                    if _norm_label(target) and (
                            _norm_label(target) in label_norm or label_norm in _norm_label(target)):
                        formula_sum += item.get("amount", 0)
                        matched_rows.append(item)
                        break

            # فرمول: جمع کل + جمع ردیف‌های خاص + ۵۰ ریال → رند به بالا
            raw_total = main_total + formula_sum + TN_COST_SMS_SURCHARGE
            final_total = round_up_to_ten_thousand(raw_total)

            logging.info(
                f"[TN] محاسبه هزینه: mainTotal={main_total:,} + "
                f"formulaSum={formula_sum:,} ({len(matched_rows)} ردیف) + "
                f"{TN_COST_SMS_SURCHARGE} = {raw_total:,} → رند بالا: {final_total:,}")

            return {
                "cost_sum": cost_data.get("costSum", 0),
                "main_total": main_total,
                "formula_sum": formula_sum,
                "matched_rows": matched_rows,
                "raw_total": raw_total,
                "final_total": final_total,
                "labels": labels,
            }

        # جدول هنوز نیست — تلاش مجدد با فاصله
        if attempt < max_retries - 1:
            logging.warning(f"[TN] جدول هزینه نمایش داده نشد — تلاش مجدد")
            await asyncio.sleep(20)

    return {"cost_sum": 0, "main_total": 0, "final_total": 0, "cost_error": True}


# ══════════════════════════════════════════════════════════════════════════════
# «چاپ اولیه» — PDF (الگوی اظهارنامه)
# ══════════════════════════════════════════════════════════════════════════════

def _is_valid_pdf_file(path: str) -> bool:
    """بررسی اعتبار فایل PDF."""
    try:
        if not path or not os.path.exists(path):
            return False
        size = os.path.getsize(path)
        if size < 1024:  # کمتر از ۱KB — نامعتبر
            return False
        with open(path, "rb") as f:
            header = f.read(5)
        return header == b"%PDF-"
    except Exception:
        return False


async def _print_tn_pdf(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    """چاپ PDF دادخواست — باکس «چاپ اوليه» + صفحه جدید (الگوی اظهارنامه).

    طبق سند راهنما: «بعد گزینه چاپ را بزن ... و چاپ و مبلغ را به کاربر
    اعلام کن»
    """
    pdf_path = f"tn_{bill_no}_{int(time.time())}.pdf"

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

    last_err = None
    for attempt in range(1, 3):
        print_page = None
        try:
            # بررسی نشست پیش از چاپ
            try:
                await check_and_handle_expiry(page, bot, user_id, check_body_text=False)
            except Exception:
                pass

            async with browser_context.expect_page(timeout=20000) as new_page_info:
                await click_print()

            print_page = await new_page_info.value
            await print_page.wait_for_load_state("load", timeout=30000)
            await asyncio.sleep(8)

            session_expired = await check_and_handle_expiry(print_page, bot, user_id, check_body_text=False)
            if session_expired:
                try:
                    await print_page.close()
                except Exception:
                    pass
                print_page = None
                if attempt < 2:
                    continue
                return ""
            else:
                await print_page.pdf(path=pdf_path, format="A4", print_background=True)
                await print_page.close()
                print_page = None
                if _is_valid_pdf_file(pdf_path):
                    return pdf_path
                logging.warning(f"[TN] PDF چاپ نامعتبر بود (تلاش {attempt}/2)... (user={user_id})")
        except Exception as e:
            last_err = e
            logging.error(f"[TN] خطا در چاپ (تلاش {attempt}/2): {e}")
        finally:
            if print_page is not None:
                try:
                    await print_page.close()
                except Exception:
                    pass

    # فال‌بک آخر: چاپ همان صفحه
    if not _is_valid_pdf_file(pdf_path):
        try:
            await page.pdf(path=pdf_path, format="A4")
        except Exception:
            pass
        if last_err is not None:
            try:
                from bug_reporter import report_bug
                await report_bug(bot, where="_print_tn_pdf", error=last_err,
                                 user_id=user_id,
                                 page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass
    return pdf_path
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
# «منضمات» — عیناً مانند اظهارنامه (مدرک نمایندگی / وکالت‌نامه الکترونیک / سایر)
# ══════════════════════════════════════════════════════════════════════════════

async def _download_images(bot: Bot, file_ids: list, user_id: int) -> list:
    """دانلود تصاویر از بله — تابع مشترک استاندارد (نام یکتا + فشرده‌سازی)."""
    from upload_helpers import download_images_from_bale
    return await download_images_from_bale(bot, file_ids, user_id, prefix="TN")


async def _enter_attachments_section(page, bot: Bot, user_id: int, bill_no: str) -> bool:
    """ورود به مرحله «منضمات» با retry و بررسی پاپ‌آپ خطای سامانه (الگوی اظهارنامه).

    ⚠ از safe_click_by_text برای باکس استفاده نمی‌شود مگر فال‌بک نهایی —
    NavigationResetError باعث ری‌استارت کل ثبت (= ثبت تکراری) می‌شد.
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
            await _close_popup(page)
            logging.warning(f"[TN][منضمات] خطای سامانه در ورود به منضمات (تلاش {attempt + 1}/3)")

        # بازگشت به فهرست و تلاش مجدد
        await _click_goto_main(page, bot, user_id)
        await resilient_sleep(page, 4, bot, user_id)

    await bot.send_message(
        user_id,
        f"⚠️ *خطا در بخش منضمات*\nکد رهگیری: `{bill_no}`\n"
        f"با شماره *09306186888* در واتساپ پیام دهید.")
    await bot.send_message(
        ADMIN_ID,
        f"❌ [TN] خطا در ورود به منضمات (۳ تلاش ناموفق) کاربر {user_id} | کد: {bill_no}")
    return False


async def _upload_tn_attachments(page, data: dict, groups_with_paths: list,
                                 has_legal: bool, has_lawyer: bool,
                                 bot: Bot, user_id: int, bill_no: str):
    """آپلود منضمات دعاوی اعتراضی — عیناً الگوی اظهارنامه.

    ۱. اگر تجدیدنظرخواه حقوقی داشت: اولین گروه = «مدرک نمایندگی» (اجباری)
    ۲. اگر وکیل داشت: «تصویر الکترونیک وکالت‌نامه»
    ۳. سایر پیوست‌ها با retry محلی (بدون ری‌استارت کل ثبت)

    از توابع اثبات‌شده ezhharnameh_scenario استفاده می‌کند (همان صفحه
    منضمات مشترک سامانه است).
    """
    # ایمپورت کاهنده وابستگی (جلوگیری از import cycle)
    from ezhharnameh_scenario import (
        _upload_proxy_document as _ezh_upload_proxy,
        _upload_electronic_vakalaht as _ezh_upload_vakalat,
        _upload_attachment_with_retry as _ezh_upload_with_retry,
    )

    appellants = data.get("tn_appellants", [])

    # ۱. مدرک نمایندگی (اگر تجدیدنظرخواه حقوقی داشت)
    if has_legal:
        proxy_group = groups_with_paths[0] if groups_with_paths else {"title": "مدرک نمایندگی", "paths": []}
        await _ezh_upload_proxy(page, proxy_group["paths"], bot, user_id)
        remaining_groups = groups_with_paths[1:]
    else:
        remaining_groups = groups_with_paths

    # ۲. وکالت‌نامه الکترونیک (اگر وکیل داشت)
    if has_lawyer:
        first_lawyer = next((p for p in appellants if p.get("person_type") == "وکیل"), {})
        contract_no = first_lawyer.get("contract_number", "")
        stamp_val = first_lawyer.get("stamp_amount_value", 0)
        await _ezh_upload_vakalat(page, contract_no, stamp_val, bot, user_id)

    # ۳. سایر پیوست‌ها — با retry محلی
    for idx, group in enumerate(remaining_groups):
        if not group.get("paths"):
            continue

        # اگر اولین گروه نیست، دکمه «پیوست جدید» را بزن
        if idx > 0:
            await asyncio.sleep(2)
            clicked = await page.evaluate('''() => {
                const btn = document.querySelector('#newAttachmentType');
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if clicked:
                logging.info(f"[TN] کلیک «پیوست جدید» قبل از گروه {idx + 1}")
                await asyncio.sleep(3)
                await wait_for_angular_idle(page)
                await asyncio.sleep(1)
            else:
                logging.warning("[TN] دکمه «پیوست جدید» پیدا نشد")

        upload_result = await _ezh_upload_with_retry(
            page,
            group["title"],
            group["paths"],
            bot,
            user_id,
            bill_no=bill_no,
            max_retries=3)

        # خطای کدنویسی → توقف کامل (الگوی اظهارنامه)
        if not upload_result["success"]:
            error_type = upload_result.get("error_type")
            if error_type in ("module_missing", "code_error"):
                logging.error(
                    f"[TN] خطای کدنویسی در آپلود — توقف کل فرآیند. "
                    f"خطا: {upload_result.get('error')}")
                if bill_no:
                    runtime_state.incomplete_tasks[f"tn:{bill_no}"] = {
                        "bill_no": bill_no, "user_id": user_id, "type": "tn",
                        "last_completed_step": "ثبت موقت", "next_step": "منضمات",
                        "task_data": data, "created_at": time.time(),
                        "attachment_groups": remaining_groups[idx:],
                    }
                return False  # توقف بدون retry

            # خطای غیر کدنویسی — ادامه با گروه بعدی
            logging.warning(
                f"[TN] آپلود گروه [{group['title']}] ناموفق، ادامه با گروه بعدی")

    # پاکسازی فایل‌های موقت
    for group in groups_with_paths:
        for p in group.get("paths", []):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    return True


# ══════════════════════════════════════════════════════════════════════════════
# ناوبری به فرم دعوا (مشترک بین process و pre_query)
# ══════════════════════════════════════════════════════════════════════════════

async def _goto_case_form(page, bot: Bot, user_id: int, case_type: str) -> bool:
    """ناوبری به فرم ثبت دعوا — با تلاش مجدد (الگوی check_scenario):

    ۱. Offices/Index + بررسی انقضای نشست
    ۲. منوی «دعاوی اعتراضی» (هدر <a.list-group-item> — کلیک JS مستقیم)
    ۳. منوی نوع دعوی (مثلاً «تجدیدنظرخواهی» — <li.list-group-item>)
    ۴. باکس مرحله ثبت — عنوان باکس به‌ازای هر نوع دعوی متفاوت است
       (REGISTER_BOX_MAP — گزارش کارفرما ۱۴۰۵/۰۶):
         تجدیدنظرخواهی      → «ثبت و اصلاح دادخواست»
         واخواهی            → «ثبت و اصلاح واخواهي»
         فرجام خواهی        → «ثبت و اصلاح فرجام خواهي»
         اعاده دادرسی مدنی  → «ثبت و اصلاح اعاده دادرسي مدني»
         اعاده دادرسی کیفری → «ثبت و اصلاح اعاده دادرسي»
         اعتراض ثالث        → «ثبت و اصلاح اعتراض ثالث»
         اعتراض به قرار دادسرا → «ثبت و اصلاح درخواست»
       — با polling تا ۳۰ ثانیه (رندر آنگولار پس از loadForm ممکن است کند باشد)

    ⭐ اصلاحیه ۱۴۰۵/۰۶ (ریشه باگ استعلام افراد و شکست ثبت انواع دعوا):
    قبلاً برای همه انواع دعوا دنبال باکس «ثبت و اصلاح دادخواست» می‌گشتیم —
    این باکس فقط صفحه تجدیدنظرخواهی وجود دارد و برای مثلاً اعاده دادرسی
    کیفری باکسِ «ثبت و اصلاح اعاده دادرسي» است؛ درنتیجه باکس هرگز پیدا
    نمی‌شد و بعد از ۳ تلاش NavigationResetError رخ می‌داد.
    """
    register_box_text = REGISTER_BOX_MAP.get(case_type, REGISTER_BOX_DEFAULT)
    menu_item = CASE_TYPE_MENU_MAP.get(case_type, case_type)

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(
                page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id)
            if not ok:
                return False
            await human_delay(3.0, 5.0)

            # بررسی انقضای نشست پیش از شروع — الگوی check_scenario
            await check_and_handle_expiry(page, bot, user_id)

            # ── منوی «دعاوی اعتراضی» (هدر <a>) ──
            await _click_menu_item(page, "دعاوی اعتراضی", bot, user_id)
            await resilient_sleep(page, 5, bot, user_id)

            # ── منوی نوع دعوی (<li>) ──
            await _click_menu_item(page, menu_item, bot, user_id)
            await resilient_sleep(page, 3, bot, user_id)

            # ── باکس مرحله ثبت (عنوان مخصوص هر نوع دعوا) — polling تا ۳۰ ثانیه ──
            # loadForm آنگولار بعد از کلیک زیرمنو فرم را می‌سازد؛ روی سامانه
            # کند ممکن است بیش از چند ثانیه طول بکشد. به‌جای خطای فوری، منتظر
            # می‌مانیم تا باکس ظاهر شود و سپس کلیک می‌کنیم.
            # ⚠ تطبیق «اول دقیق، بعد شامل‌شدن» — چون عنوان کیفری («ثبت و اصلاح
            # اعاده دادرسي») پیشوند عنوان مدنی («ثبت و اصلاح اعاده دادرسي مدني»)
            # است و با includes خالی ممکن است باکس اشتباه کلیک شود.
            box_clicked = False
            for _poll in range(30):
                try:
                    box_clicked = await page.evaluate('''(boxText) => {
                        const norm = (s) => (s || '')
                            .replace(/\\u064A/g, '\\u06CC').replace(/\\u0643/g, '\\u06A9')
                            .replace(/[\\u200c\\u200f]/g, '')
                            .replace(/\\s+/g, ' ').trim();
                        const t = norm(boxText);
                        const heads = Array.from(document.querySelectorAll('.box h5'));
                        const h = heads.find(el => norm(el.innerText) === t)
                                || heads.find(el => norm(el.innerText).includes(t));
                        if (h) {
                            const box = h.closest('.box');
                            if (box) { box.click(); return true; }
                        }
                        return false;
                    }''', register_box_text)
                except Exception:
                    box_clicked = False
                if box_clicked:
                    break
                await asyncio.sleep(1)

            if not box_clicked:
                if attempt < max_attempts - 1:
                    logging.warning(
                        f"[TN] باکس «{register_box_text}» یافت نشد (تلاش {attempt + 1}/{max_attempts}) — "
                        f"ری‌استارت ناوبری از Offices/Index")
                    continue
                # آخرین تلاش — فال‌بک نهایی safe_click_by_text (خطا می‌دهد اگر نبود)
                logging.warning(
                    f"[TN] باکس «{register_box_text}» پس از polling یافت نشد — فال‌بک safe_click_by_text")
                await safe_click_by_text(page, register_box_text, bot, user_id)

            await resilient_sleep(page, 5, bot, user_id)
            return True

        except NavigationResetError as e:
            # این خطا خودش به Offices/Index ناوبری کرده — تلاش مجدد کل زنجیره
            logging.warning(
                f"[TN] ناوبری ریست شد (تلاش {attempt + 1}/{max_attempts}): {e}")
            if attempt >= max_attempts - 1:
                return False
        except Exception as e:
            logging.warning(
                f"[TN] خطا در ناوبری به فرم (تلاش {attempt + 1}/{max_attempts}): {e}")
            if attempt >= max_attempts - 1:
                return False
            try:
                await page.goto("https://sakha2.adliran.ir/Offices/Index")
                await asyncio.sleep(4)
            except Exception:
                pass
    return False


async def _select_start_radio(page, has_lawyer: bool, has_legal: bool, only_real: bool):
    """مرحله «شروع» — انتخاب نوع ارائه (مانند اظهارنامه).

    «اگر نماینده یا وکیل درج شده بود، در اینجا نیز مانند بخش اظهارنامه
     موارد انجام بده»

    ⚠ فراخواننده باید قبل از این تابع step «شروع» را کلیک کرده باشد.
    """
    if only_real and not has_lawyer and not has_legal:
        # فقط حقیقی — مستقیم وارد بخش اشخاص می‌شویم (الگوی اظهارنامه)
        logging.info("[TN] only real person — no start radio needed")
        return
    if has_lawyer:
        await page.evaluate('''() => {
            const rdb = document.querySelector('#rdbLawyerOffer');
            if (rdb) rdb.click();
        }''')
        await asyncio.sleep(2)
    elif has_legal:
        await page.evaluate('''() => {
            const rdb = document.querySelector('#rdbAgentOffer');
            if (rdb) rdb.click();
        }''')
        await asyncio.sleep(2)
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
# تابع اصلی پردازش تسک ثبت دعوی اعتراضی
# ══════════════════════════════════════════════════════════════════════════════

async def process_tajdid_nazar_task(data: dict, bot: Bot):
    """پردازش تسک ثبت دعوی اعتراضی — بازنویسی کامل طبق سند راهنما."""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]
    is_prepaid = data.get("prepaid", False)

    case_type = data.get("case_type", "")
    appellants = data.get("tn_appellants", [])
    appellees = data.get("tn_appellees", [])
    witnesses = data.get("tn_witnesses", [])
    tn_text = data.get("tn_text", "")
    tn_text_html = data.get("tn_text_html", "")
    extra_text = data.get("tn_extra_text", "")
    attachments = data.get("tn_attachments", [])
    reasons = data.get("tn_reasons", [])
    file_no = data.get("tn_file_no", "")
    judge_no = data.get("tn_judge_no", "")

    has_lawyer = any(p.get("person_type") == "وکیل" for p in appellants)
    has_legal = any(p.get("person_type") == "شخص حقوقی" for p in appellants)
    has_real = any(p.get("person_type") == "شخص حقیقی" for p in appellants)
    only_real = has_real and not has_legal and not has_lawyer

    is_prosecutor = case_type == "اعتراض به قرار دادسرا"
    needs_reasons = case_type in ("اعاده دادرسی مدنی", "اعاده دادرسی کیفری")

    # نام step های اشخاص
    appellant_step = APPELLANT_STEP_MAP.get(case_type, "تجديدنظرخواه")
    appellee_step = APPELLEE_STEP_MAP.get(case_type, "تجديدنظرخوانده")
    witness_step = WITNESS_STEP_MAP.get(case_type, WITNESS_STEP_DEFAULT)

    logging.info(
        f"[TN] user={user_id} case={case_type} judge={judge_no} file={file_no} "
        f"appellants={len(appellants)} appellees={len(appellees)} witnesses={len(witnesses)} "
        f"lawyer={has_lawyer} legal={has_legal}")

    await bot.send_message(
        user_id,
        f"⏳ *در حال ثبت {case_type}...*")
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [TN] شروع ثبت {case_type} برای کاربر {user_id}\n"
        f"دادنامه: {judge_no} | تجدیدنظرخواه: {len(appellants)} | "
        f"تجدیدنظرخوانده: {len(appellees)} | شهود: {len(witnesses)}"
    )

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            # ── ۱. ناوبری به فرم دعوا ─────────────────────────────
            ok = await _goto_case_form(sana_page, bot, user_id, case_type)
            if not ok:
                return

            # ── ۲. مرحله «شروع» — رادیوی نوع ارائه ────────────────
            await _click_step_label(sana_page, "شروع", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)
            await _select_start_radio(sana_page, has_lawyer, has_legal, only_real)

            # ── ۳. مرحله «اطلاعات دادنامه/قرار» + بازیابی ──────────
            await _fill_judge_info_step(
                sana_page, data, bot, user_id, is_prosecutor=is_prosecutor)

            # ── ۴. مرحله «تجدیدنظرخواه» ────────────────────────────
            await _click_step_label(sana_page, appellant_step, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            if data.get("tn_appellant_query_mode"):
                # حالت استعلام افراد پرونده: نگه‌داشتن انتخاب‌شده‌ها
                selected_app_names = data.get("tn_appellant_selected_names", [])
                logging.info(f"[TN] حالت استعلام {appellant_step} — نگه‌داشتن: {selected_app_names}")
                await _remove_unselected_persons(sana_page, selected_app_names, bot, user_id)
                await resilient_sleep(sana_page, 3, bot, user_id)
            else:
                # حالت عادی: پاک‌سازی کامل لیست + افزودن اشخاص کاربر
                await _clear_nav_list_persons(sana_page)
                await resilient_sleep(sana_page, 2, bot, user_id)
                await _add_persons_to_section(
                    sana_page, appellants, appellant_step, bot, user_id,
                    person_role="appellant")

            # ── ۵. مرحله «تجدیدنظرخوانده» (غیر اعتراض به قرار دادسرا) ──
            if not is_prosecutor:
                await _click_step_label(sana_page, appellee_step, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                if data.get("tn_appellee_query_mode"):
                    selected_apl_names = data.get("tn_appellee_selected_names", [])
                    logging.info(f"[TN] حالت استعلام {appellee_step} — نگه‌داشتن: {selected_apl_names}")
                    await _remove_unselected_persons(sana_page, selected_apl_names, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                else:
                    await _clear_nav_list_persons(sana_page)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await _add_persons_to_section(
                        sana_page, appellees, appellee_step, bot, user_id,
                        person_role="appellee")

            # ── ۶. مرحله «وكيل» (در صورت وجود وکیل) ────────────────
            # ⭐ باگ نسخه قبلی: اشخاص وکیل skip می‌شدند ولی step وكيل
            # هرگز وجود نداشت → وکیل هرگز در سامانه ثبت نمی‌شد.
            if has_lawyer:
                lawyer_step_exists = await _step_exists(sana_page, "وكيل")
                if lawyer_step_exists:
                    await _click_step_label_soft(sana_page, "وكيل")
                    await resilient_sleep(sana_page, 4, bot, user_id)
                    for idx, person in enumerate(appellants):
                        if person.get("person_type") != "وکیل":
                            continue
                        await _click_add_section_btn(sana_page, bot, user_id)
                        await resilient_sleep(sana_page, 3, bot, user_id)
                        await _fill_lawyer_person(
                            sana_page, person.get("national_id", ""), bot, user_id,
                            person_role="appellant", person_index=idx)
                        await resilient_sleep(sana_page, 10, bot, user_id)
                else:
                    logging.warning("[TN] step «وكيل» در این فرم یافت نشد — وکیل در همان بخش اشخاص ثبت می‌شود")
                    # فال‌بک: افزودن وکیل به‌عنوان شخص در بخش تجدیدنظرخواه
                    await _click_step_label(sana_page, appellant_step, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    for idx, person in enumerate(appellants):
                        if person.get("person_type") != "وکیل":
                            continue
                        await _click_add_section_btn(sana_page, bot, user_id)
                        await resilient_sleep(sana_page, 3, bot, user_id)
                        await _fill_real_person(
                            sana_page, person.get("national_id", ""), bot, user_id,
                            person_role="appellant", person_index=idx)
                        await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۷. مرحله «نماينده» (در صورت وجود تجدیدنظرخواه حقوقی) ──
            # مانند اظهارنامه/چک — فقط اگر step وجود داشته باشد (کلیک نرم).
            if has_legal and await _step_exists(sana_page, "نماينده"):
                await _click_step_label_soft(sana_page, "نماينده")
                await resilient_sleep(sana_page, 4, bot, user_id)

                legal_app = next(
                    (p for p in appellants if p.get("person_type") == "شخص حقوقی"), {})
                rep_type = legal_app.get("representative_type", "")
                nat_id = legal_app.get("national_id", "")

                if rep_type == "مدیرعامل":
                    agent_value = "0091000010000008"
                else:
                    agent_value = "0091000010000010"

                await _click_add_section_btn(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)
                await wait_for_angular_idle(sana_page)
                await asyncio.sleep(3)

                # انتخاب نوع نماینده از dropdown
                await sana_page.evaluate('''(val) => {
                    const sel = document.querySelector('select[ng-model*="AgentTypeId"]');
                    if (sel && !sel.disabled) {
                        sel.focus();
                        sel.value = val;
                        sel.dispatchEvent(new Event("input", { bubbles: true }));
                        sel.dispatchEvent(new Event("change", { bubbles: true }));
                        return true;
                    }
                    // فال‌بک: جستجو در همه select ها
                    const sels = Array.from(document.querySelectorAll('select'));
                    for (const s of sels) {
                        const opts = Array.from(s.options);
                        const opt = opts.find(o => o.value === val);
                        if (opt && !s.disabled) {
                            s.focus();
                            s.value = val;
                            s.dispatchEvent(new Event("input", { bubbles: true }));
                            s.dispatchEvent(new Event("change", { bubbles: true }));
                            return;
                        }
                    }
                }''', agent_value)
                await asyncio.sleep(3)

                # کدملی نماینده + استعلام
                if nat_id:
                    await wait_for_angular_idle(sana_page)
                    await asyncio.sleep(2)
                    for _nat_try in range(5):
                        nat_id_set = await sana_page.evaluate('''(val) => {
                            const inp = document.querySelector('#txtRealIrNationalityCode');
                            if (inp && !inp.disabled) {
                                inp.focus();
                                inp.value = "";
                                inp.value = val;
                                inp.dispatchEvent(new Event("input", { bubbles: true }));
                                inp.dispatchEvent(new Event("change", { bubbles: true }));
                                return true;
                            }
                            return false;
                        }''', nat_id)
                        if nat_id_set:
                            break
                        await asyncio.sleep(3)

                    if nat_id_set:
                        await _query_sana(
                            sana_page, "actions.callNationalityCode", bot, user_id,
                            current_national_id=nat_id, person_role="appellant_agent")
                        await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۸. مرحله «مطلع/گواه» یا «سایر اشخاص» (شهود) ────────
            if witnesses:
                await _click_step_label(sana_page, witness_step, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)
                await _add_persons_to_section(
                    sana_page, witnesses, witness_step, bot, user_id,
                    person_role="witness")

            # ── ۹. مرحله «شرح» — متن ────────────────────────────────
            await _fill_sharh_section(sana_page, tn_text, tn_text_html, bot, user_id)

            # ── ۱۰. مرحله «دلايل» — سایر دلایل ──────────────────────
            await _fill_dalael_section(sana_page, extra_text, bot, user_id)

            # ── ۱۱. مرحله «جهات» (اعاده دادرسی) ─────────────────────
            if needs_reasons:
                await _fill_jihat_section(sana_page, reasons, case_type, bot, user_id)

            # ── ۱۲. «ثبت موقت» + کد رهگیری ──────────────────────────
            await _click_save_temp(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            bill_no = await _extract_bill_no(sana_page)
            logging.info(f"[TN] bill_no={bill_no}")

            if not bill_no:
                err_msg = ("ثبت موقت انجام شد ولی کد رهگیری دعوا از سامانه "
                           "قابل استخراج نبود.")
                await bot.send_message(
                    user_id,
                    f"⚠️ *خطا در ثبت موقت:*\n\n«{err_msg}»\n\n"
                    "فرآیند متوقف شد. لطفاً به مدیریت اطلاع دهید.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [TN] bill_no استخراج نشد برای کاربر {user_id} — بررسی صفحه لازم است.")
                raise TajdidFatalError(err_msg)

            # ذخیره کدرهگیری در گوگل شیت + اطلاع به مدیر (الگوی اظهارنامه)
            await log_event(
                "ثبت موقت", f"دعاوی اعتراضی ({case_type})", str(user_id), user_id,
                tracking_code=bill_no,
                note=f"{case_type} ثبت موقت شد | دادنامه: {judge_no}")
            await bot.send_message(
                ADMIN_ID,
                f"📋 *ثبت موقت {case_type} موفق*\n"
                f"👤 کاربر: {user_id}\n"
                f"🔢 کد رهگیری: `{bill_no}`\n"
                f"📅 دادنامه: {judge_no}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۳. «منضمات» — عیناً مانند اظهارنامه ─────────────────
            # دانلود تصاویر از بله
            groups_with_paths = []
            for group in attachments:
                paths = await _download_images(bot, group.get("images", []), user_id)
                groups_with_paths.append({"title": group.get("title", "مستندات"), "paths": paths})

            attachments_ok = True
            if has_legal or groups_with_paths:
                entered = await _enter_attachments_section(sana_page, bot, user_id, bill_no)
                if not entered:
                    error_msg = (
                        f"⚠️ *خطا در بخش منضمات*\nکد رهگیری: `{bill_no}`\n"
                        f"با شماره *09306186888* در واتساپ پیام دهید.")
                    await bot.send_message(user_id, error_msg)
                    await bot.send_message(
                        ADMIN_ID,
                        f"❌ [TN] خطای منضمات (۳ تلاش ناموفق) کاربر {user_id} | کد: {bill_no}")
                    await log_event(
                        "خطای سامانه", f"دعاوی اعتراضی ({case_type})", str(user_id), user_id,
                        tracking_code=bill_no, note="خطا در ورود به منضمات (۳ تلاش)")
                    runtime_state.incomplete_tasks[f"tn:{bill_no}"] = {
                        "bill_no": bill_no, "user_id": user_id, "type": "tn",
                        "last_completed_step": "ثبت موقت", "next_step": "منضمات",
                        "task_data": data, "created_at": time.time(),
                    }
                    return

                attachments_ok = await _upload_tn_attachments(
                    sana_page, data, groups_with_paths, has_legal, has_lawyer,
                    bot, user_id, bill_no)
                if not attachments_ok:
                    # خطای کدنویسی — تسک incomplete ذخیره شد داخل تابع
                    return

                await _click_goto_main(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۴. «آماده‌سازی» — تایید اطلاعات ─────────────────────
            await _click_step_box(sana_page, "آماده سازي جهت دريافت وجه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            prep_ok = await _click_preparation(sana_page, bot, user_id)
            if not prep_ok:
                await bot.send_message(
                    user_id,
                    f"⚠️ مرحله آماده‌سازی با مشکل مواجه شد.\n"
                    f"کد رهگیری: `{bill_no}`\n"
                    f"با شماره *09306186888* در واتساپ پیام دهید.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [TN] آماده‌سازی ناموفق کاربر {user_id} | کد: {bill_no}")
                await log_event(
                    "خطای سامانه", f"دعاوی اعتراضی ({case_type})", str(user_id), user_id,
                    tracking_code=bill_no, note="آماده‌سازی ناموفق")
                runtime_state.incomplete_tasks[f"tn:{bill_no}"] = {
                    "bill_no": bill_no, "user_id": user_id, "type": "tn",
                    "last_completed_step": "منضمات", "next_step": "آماده‌سازی",
                    "task_data": data, "created_at": time.time(),
                }
                return

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۵. «محاسبه و دریافت هزینه» ──────────────────────────
            await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            cost_info = await _calculate_cost(sana_page, bot, user_id)
            final_total = cost_info.get("final_total", 0)
            cost_error = cost_info.get("cost_error", False)
            logging.info(f"[TN] cost_info: main={cost_info.get('main_total')}, "
                         f"final={final_total}, error={cost_error}")

            # شناسه پرداخت — ذخیره در شیت + پیام به مدیر (الگوی اظهارنامه)
            try:
                from payment_id_capture import capture_and_report_payment_ids
                await capture_and_report_payment_ids(
                    sana_page, bot, user_id,
                    service_name=f"دعاوی اعتراضی ({case_type})",
                    tracking_code=bill_no,
                    amount=cost_info.get("main_total", 0),
                    exclude_values=[bill_no],
                    log_prefix="TN")
            except Exception as pay_err:
                logging.warning(f"[TN] خطا در capture_and_report_payment_ids: {pay_err}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۶. «چاپ اولیه» ──────────────────────────────────────
            pdf_path = await _print_tn_pdf(sana_page, browser_context, bill_no, bot, user_id)

            # ── ۱۷. ارسال نتیجه (پرداخت/امضا — روال مستقل دعاوی اعتراضی) ──
            from tajdid_nazar_handlers import send_tajdid_nazar_result
            appellant_nat_ids = ", ".join([
                p.get("national_id", "") for p in appellants if p.get("national_id")
            ])

            try:
                from panel_sync import upsert_case_to_panel
                await upsert_case_to_panel(
                    bale_user_id=user_id, full_name=str(user_id),
                    service_type="TAJDID_NAZAR", status="PROCESSING",
                    tracking_code=bill_no or None,
                    document_category=case_type,
                    result_summary="دعوی اعتراضی در سامانه ثبت شد",
                )
            except Exception as panel_err:
                logging.warning(f"[TN] خطا در ثبت پرونده در پنل: {panel_err}")

            if cost_error:
                # جدول هزینه نمایش داده نشد — ارسال PDF + پیام خطا (الگوی اظهارنامه)
                await bot.send_message(
                    user_id,
                    f"⚠️ *بخش هزینه سامانه دادگاه اختلال دارد.*\n\n"
                    f"📄 {case_type} شما با کد رهگیری `{bill_no}` ثبت و چاپ شد.\n"
                    f"لطفاً برای محاسبه هزینه به مدیریت به شماره *09306186888* در واتساپ پیام دهید.")
                if pdf_path and os.path.exists(pdf_path):
                    from bale_file_sender import send_document_direct
                    await send_document_direct(user_id, pdf_path)
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [TN] جدول هزینه نمایش داده نشد. کاربر {user_id} | کد: {bill_no}")
            else:
                if pdf_path:
                    await send_tajdid_nazar_result(
                        bot, user_id, pdf_path, final_total,
                        tracking_code=bill_no,
                        national_ids=appellant_nat_ids,
                        case_type=case_type,
                        file_no=file_no,
                        tn_persons=appellants)
                    await bot.send_message(
                        ADMIN_ID,
                        f"✅ [TN] ثبت {case_type} کاربر {user_id} موفق. "
                        f"کد: {bill_no} — هزینه نهایی: {final_total:,} ریال")
                else:
                    # چاپ ناموفق — دست‌کم مبلغ را اعلام کن
                    await bot.send_message(
                        user_id,
                        f"💰 *هزینه دادرسی: {final_total:,} ریال*\n\n"
                        f"⚠️ چاپ نسخه پرونده با خطا مواجه شد؛ لطفاً با پشتیبانی تماس بگیرید.\n"
                        f"کد رهگیری: `{bill_no}`")
                    try:
                        from panel_sync import upsert_case_to_panel
                        await upsert_case_to_panel(
                            bale_user_id=user_id, full_name=str(user_id),
                            service_type="TAJDID_NAZAR", status="FAILED",
                            tracking_code=bill_no or None,
                            document_category=case_type,
                            fee=final_total // 10,
                            error_details="ثبت انجام شد اما چاپ PDF ناموفق بود",
                            error_step="print_pdf")
                    except Exception as panel_err:
                        logging.warning(f"[TN] خطا در ثبت شکست پرونده در پنل: {panel_err}")

            await log_event(
                "ثبت", f"دعاوی اعتراضی ({case_type})", str(user_id), user_id,
                tracking_code=bill_no, national_id=appellant_nat_ids,
                doc_name=case_type,
                note=f"هزینه نهایی: {final_total:,} ریال")
            return  # موفقیت

        except TajdidSanaQueryError as e:
            logging.error(f"[TN] خطای استعلام ثنا user={user_id}: {e}")
            # ذخیره اطلاعات تسک برای ادامه بعدی در صورت ویرایش شناسه ملی
            pending_task_data = dict(data)
            pending_task_data["_sana_error_national_id"] = e.national_id
            pending_task_data["_sana_error_person_role"] = e.person_role
            pending_task_data["_sana_error_person_index"] = e.person_index
            runtime_state.pending_tn_sana_fix[user_id] = {
                "task_data": pending_task_data,
                "created_at": asyncio.get_event_loop().time(),
            }

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            role_label = {
                "appellant": appellant_step,
                "appellee": appellee_step,
                "witness": witness_step,
            }.get(e.person_role, e.person_role or "شخص")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ ویرایش شناسه ملی",
                    callback_data=f"tn_fix_nid:{user_id}")],
                [InlineKeyboardButton(
                    text="🗑 حذف درخواست",
                    callback_data=f"tn_del_req:{user_id}")],
            ])
            await bot.send_message(
                user_id,
                f"⚠️ *خطای استعلام ثنا*\n\n"
                f"شناسه ملی `{e.national_id}` ({role_label}) ثبت‌نام ثنا ندارد یا اشتباه است.\n\n"
                f"لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=kb)
            return  # متوقف — منتظر اصلاح کاربر

        except TajdidFatalError as e:
            logging.error(f"[TN] خطای قطعی user={user_id} (تلاش {attempt + 1}): {e}")
            await bot.send_message(user_id, f"⚠️ *خطای قطعی:*\n\n«{str(e)[:250]}»")
            await log_event(
                "خطای سامانه", f"دعاوی اعتراضی ({case_type})", str(user_id), user_id,
                doc_name=case_type, note=f"خطای قطعی: {str(e)[:200]}")
            try:
                from panel_sync import upsert_case_to_panel
                await upsert_case_to_panel(
                    bale_user_id=user_id, full_name=str(user_id),
                    service_type="TAJDID_NAZAR", status="FAILED",
                    document_category=case_type,
                    error_details=f"خطای قطعی: {str(e)[:200]}",
                    error_step="FATAL_ERROR")
            except Exception as panel_err:
                logging.warning(f"[TN] خطا در ثبت شکست پرونده در پنل: {panel_err}")
            return

        except Exception as e:
            logging.error(f"[TN] تلاش {attempt + 1} ناموفق user={user_id}: {e}",
                          exc_info=True)
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [TN] تلاش {attempt + 1} ناموفق. ریلود...\nخطا: {str(e)[:300]}")
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    f"⚠️ ثبت {case_type} با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد.")
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [TN] کاربر {user_id} پس از {max_attempts} تلاش ناموفق ({case_type}).")
                await log_event(
                    "خطای سامانه", f"دعاوی اعتراضی ({case_type})", str(user_id), user_id,
                    doc_name=case_type,
                    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}")
                try:
                    from panel_sync import upsert_case_to_panel
                    await upsert_case_to_panel(
                        bale_user_id=user_id, full_name=str(user_id),
                        service_type="TAJDID_NAZAR", status="FAILED",
                        document_category=case_type,
                        error_details=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}",
                        error_step="MAX_RETRIES_EXCEEDED")
                except Exception as panel_err:
                    logging.warning(f"[TN] خطا در ثبت شکست پرونده در پنل: {panel_err}")
            try:
                from bug_reporter import report_bug
                await report_bug(
                    bot, where="process_tajdid_nazar_task", error=e,
                    user_id=user_id,
                    page=getattr(runtime_state, "sana_page", None))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# استعلام افراد پرونده (حالت استعلام در ربات)
# ══════════════════════════════════════════════════════════════════════════════

async def pre_query_tn_persons(data: dict, bot: Bot, step_name: str) -> list:
    """استعلام افراد موجود در پرونده از سامانه.

    ۱. ناوبری به فرم دعوا (منو → نوع دعوی → باکس ثبت مخصوص همان نوع —
       REGISTER_BOX_MAP)
    ۲. مرحله شروع (رادیوی حقیقی)
    ۳. مرحله اطلاعات دادنامه + بازیابی (کامل — مانند ثبت اصلی)
    ۴. ورود به step مورد نظر (تجدیدنظرخواه/خوانده)
    ۵. استخراج لیست نام‌ها از nav-list

    ⭐ اصلاحیه: کل استعلام با تلاش مجدد (×۲) انجام می‌شود — خطای گذرای
    سامانه (رندر کند، ریست ناوبری، ...) دیگر کل استعلام را نمی‌کشد.

    Returns: [{"index": int, "name": str}, ...]
    """
    sana_page = runtime_state.sana_page
    user_id = data["user_id"]

    if not sana_page:
        raise TajdidFatalError("صفحه مرورگر در دسترس نیست. لطفاً بعداً تلاش کنید.")

    case_type = data.get("case_type", "")
    is_prosecutor = case_type == "اعتراض به قرار دادسرا"

    last_error = None
    for attempt in range(2):
        try:
            return await _pre_query_tn_persons_once(
                sana_page, bot, user_id, case_type, is_prosecutor, step_name, data)
        except TajdidFatalError:
            raise  # خطای قطعی (بدون مرورگر و ...) — retry بی‌فایده
        except TajdidSanaQueryError:
            raise  # خطای ثبت‌نام ثنا — مربوط به کاربر، نه سامانه
        except Exception as e:
            last_error = e
            logging.warning(
                f"[TN] استعلام افراد (تلاش {attempt + 1}/2) ناموفق: {e}")
            if attempt == 0:
                try:
                    await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                    await asyncio.sleep(4)
                except Exception:
                    pass

    raise TajdidFatalError(f"خطا در استعلام پرونده: {str(last_error)[:200]}")


async def _pre_query_tn_persons_once(
        sana_page, bot: Bot, user_id, case_type, is_prosecutor,
        step_name: str, data: dict) -> list:
    """یک دور کامل استعلام افراد (بدون retry — فقط منطق)."""

    # ۱. ناوبری به فرم
    ok = await _goto_case_form(sana_page, bot, user_id, case_type)
    if not ok:
        raise TajdidFatalError("خطا در اتصال به سامانه.")

    # ۲. مرحله شروع — رادیوی «شخص حقیقی»
    await _click_step_label(sana_page, "شروع", bot, user_id)
    await resilient_sleep(sana_page, 3, bot, user_id)
    await sana_page.evaluate('''() => {
        const rdb = document.querySelector('#rdbRealOffer, input[value="1"][name*="Offer"], input[value="1"]');
        if (rdb) {
            rdb.click();
            try {
                if (typeof angular !== 'undefined') {
                    const scope = angular.element(rdb).scope();
                    if (scope) scope.$apply();
                }
            } catch (e) {}
        }
    }''')
    await asyncio.sleep(2)

    # ۳. مرحله اطلاعات دادنامه + بازیابی — کامل مانند ثبت اصلی
    await _fill_judge_info_step(
        sana_page, data, bot, user_id, is_prosecutor=is_prosecutor)

    # ۴. ورود به step مورد نظر
    await _click_step_label(sana_page, step_name, bot, user_id)
    await resilient_sleep(sana_page, 5, bot, user_id)

    # ۵. استخراج نام‌ها
    names = await _extract_persons_from_navlist(sana_page)

    logging.info(f"[TN] استعلام افراد پرونده: {len(names)} نفر یافت شد (step={step_name})")
    return names
