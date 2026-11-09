# -*- coding: utf-8 -*-
"""تست ۱۴۰۵/۰۸ — دستور کارفرما (اصلاح انتخاب عنوان‌های لایحه در سامانه):

برای «اعتراض به نظریه کارشناسی» و «اعتراض به قرار رد دفتر» باید در فیلد
جستجوی عنوان (ui-select) کلمهٔ «اعتراض» نوشته شود و سپس عنوان درست از
فهرست انتخاب شود؛ برای «درخواست کپی از مدارک پرونده» و «درخواست مطالعه
پرونده» باید «پرونده» نوشته شود و سپس گزینهٔ درست انتخاب شود. مابقی
عناوین — طبق اعلام کارفرما — درست‌اند و نباید تغییر کنند.

اصلاح تکمیلی (دستور «اصلاح شو»): کلید «درخواست منعیت از خروج کشور»
با متن واقعی دکمهٔ کیبورد/قالب اکسل («ممنوعیت») یکسان نشده بود و همیشه
به فال‌بک «دفا» می‌افتید — کلید یکسان‌سازی شد.

فهرست‌های ETRAZ_LIST و PARVANDEH_LIST عیناً از HTML فهرست کشویی سامانه
(ui-select / theJSSBillTypeListForLookup) به نقل از کارفرما آورده شده‌اند.
اجرای:
BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_lavayeh_bill_titles.py
"""
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import lavayeh_scenario as ls

# فهرست واقعی سامانه برای جستجوی «اعتراض» (به‌ترتیب نمایش)
ETRAZ_LIST = [
    "استرداد اعتراض به نظریه کارشناسی",
    "اعتراض به بهای خواسته",
    "اعتراض به عملیات اجرایی",
    "اعتراض به قرار تأمین خواسته",
    "اعتراض به قرار رد دفتر",
    "اعتراض به نظریه کارشناسی",
    "اعتراض راجع به ترتیب تقسیم وجه حاصل از فروش اموال توقیفی",
    "اعتراض مربوط به تنظیم صورتجلسه اموال توقیفی",
]

# فهرست واقعی سامانه برای جستجوی «پرونده» (به‌ترتیب نمایش)
PARVANDEH_LIST = [
    "اعلام پرونده مرتبط",
    "درخواست تجمیع پرونده",
    "درخواست تصویر اوراق پرونده",
    "درخواست مطالبه پرونده استنادی",
    "درخواست مطالعه پرونده",
    "درخواست کپی از مدارک پرونده",
]

# حالت‌های محتمل عنوان سامانه برای ممنوعیت از خروج (املای دقیق قطعی نیست)
KHORUJ_VARIANTS = [
    ["درخواست ممنوعیت از خروج از کشور"],
    ["درخواست ممنوعیت از خروج کشور"],
    ["درخواست منعیت از خروج کشور"],
    ["درخواست ممنوعیت از خروج از کشور", "درخواست تجدید نظر در قرار ممنوعیت از خروج"],
]


def _norm(s: str) -> str:
    """همان یکسان‌سازیِ JS داخل _select_bill_type: ي/ك، نیم‌فاصله و فاصله‌ها."""
    for ch in ("\u200c", "\u200f", "\u200e"):
        s = s.replace(ch, "")
    s = s.replace("ي", "ی").replace("ك", "ک")
    return " ".join(s.split())


def _simulate_select(search_kw: str, target_text: str, items: list, fallback_idx: int = -1):
    """بازسازی منطق انتخاب _select_bill_type در Python:

    ۱) فهرست با کلیدواژهٔ جستجو فیلتر می‌شود (filter:{Title:$select.search})
    ۲) اولویت با «تطابق کامل» است و بعد «شامل بودن» — دقیقاً مثل JS.
    ۳) اگر متن هدف پیدا نشد، ردیف fallback_idx کلیک می‌شود (رفتار JS).
    خروجی: (عنوان انتخاب‌شده، اندیس آن در فهرست فیلترشده)
    """
    filtered = [it for it in items if search_kw in _norm(it)]
    t = _norm(target_text)
    exact = [it for it in filtered if _norm(it) == t]
    if exact:
        return exact[0], filtered.index(exact[0])
    contains = [it for it in filtered if t in _norm(it)]
    if contains:
        return contains[0], filtered.index(contains[0])
    if fallback_idx >= 0 and len(filtered) > fallback_idx:
        return filtered[fallback_idx], fallback_idx
    return None, -1


def test_etezag_titles_search_keyword_is_etezag():
    """«اعتراض به نظریه کارشناسی» و «اعتراض به قرار رد دفتر»: جستجو با «اعتراض»."""
    assert ls.TITLE_SEARCH_MAP["اعتراض به نظر کارشناس"][0] == "اعتراض"
    assert ls.TITLE_SEARCH_MAP["اعتراض به قرار رد دفتر"][0] == "اعتراض"


def test_parvandeh_titles_search_keyword_is_parvandeh():
    """«کپی از مدارک پرونده» و «مطالعه پرونده»: جستجو با «پرونده»."""
    assert ls.TITLE_SEARCH_MAP["درخواست کپی از مدارک پرونده"][0] == "پرونده"
    assert ls.TITLE_SEARCH_MAP["درخواست مطالعه پرونده"][0] == "پرونده"


def test_target_texts_are_real_system_titles():
    """متن هدف باید دقیقاً نام درستِ موجود در فهرست سامانه باشد."""
    assert ls.TITLE_TARGET_TEXT_MAP["اعتراض به نظر کارشناس"] == "اعتراض به نظریه کارشناسی"
    assert ls.TITLE_TARGET_TEXT_MAP["اعتراض به قرار رد دفتر"] == "اعتراض به قرار رد دفتر"
    assert ls.TITLE_TARGET_TEXT_MAP["درخواست کپی از مدارک پرونده"] == "درخواست کپی از مدارک پرونده"
    assert ls.TITLE_TARGET_TEXT_MAP["درخواست مطالعه پرونده"] == "درخواست مطالعه پرونده"


def test_select_nazariye_karshenasi_not_esterdad():
    """تطابق کامل مقدم است: «استرداد اعتراض به نظریه کارشناسی» (که متن هدف را
    «شامل» است) نباید به‌جای «اعتراض به نظریه کارشناسی» انتخاب شود."""
    title, idx = _simulate_select(
        "اعتراض", ls.TITLE_TARGET_TEXT_MAP["اعتراض به نظر کارشناس"], ETRAZ_LIST)
    assert title == "اعتراض به نظریه کارشناسی"
    assert idx == 5


def test_select_etezag_be_gharar_radd_daftar():
    """«اعتراض به قرار رد دفتر» از فهرست ۸تاییِ «اعتراض» انتخاب شود (ردیف ۴)."""
    title, idx = _simulate_select(
        "اعتراض", ls.TITLE_TARGET_TEXT_MAP["اعتراض به قرار رد دفتر"], ETRAZ_LIST)
    assert title == "اعتراض به قرار رد دفتر"
    assert idx == 4


def test_select_copy_az_madarek_parvandeh():
    """«درخواست کپی از مدارک پرونده» از فهرست ۶تاییِ «پرونده» انتخاب شود (ردیف ۵)."""
    title, idx = _simulate_select(
        "پرونده", ls.TITLE_TARGET_TEXT_MAP["درخواست کپی از مدارک پرونده"], PARVANDEH_LIST)
    assert title == "درخواست کپی از مدارک پرونده"
    assert idx == 5


def test_select_motale_parvandeh():
    """«درخواست مطالعه پرونده» از فهرست ۶تاییِ «پرونده» انتخاب شود (ردیف ۴)."""
    title, idx = _simulate_select(
        "پرونده", ls.TITLE_TARGET_TEXT_MAP["درخواست مطالعه پرونده"], PARVANDEH_LIST)
    assert title == "درخواست مطالعه پرونده"
    assert idx == 4


def test_fallback_row_idx_points_to_correct_rows():
    """فال‌بک اندیس ردیف هم (اگر متن هدف پیدا نشد) به ردیف درست اشاره کند."""
    assert _norm(ETRAZ_LIST[ls.TITLE_SEARCH_MAP["اعتراض به نظر کارشناس"][1]]) == \
        _norm("اعتراض به نظریه کارشناسی")
    assert _norm(ETRAZ_LIST[ls.TITLE_SEARCH_MAP["اعتراض به قرار رد دفتر"][1]]) == \
        _norm("اعتراض به قرار رد دفتر")
    assert _norm(PARVANDEH_LIST[ls.TITLE_SEARCH_MAP["درخواست کپی از مدارک پرونده"][1]]) == \
        _norm("درخواست کپی از مدارک پرونده")
    assert _norm(PARVANDEH_LIST[ls.TITLE_SEARCH_MAP["درخواست مطالعه پرونده"][1]]) == \
        _norm("درخواست مطالعه پرونده")


def test_remaining_titles_unchanged():
    """مابقی عناوین — طبق اعلام کارفرما — باید دست‌نخورده مانده باشند."""
    assert ls.TITLE_SEARCH_MAP["لایحه دفاعیه"] == ("دفا", 0)
    assert ls.TITLE_SEARCH_MAP["صدور اجرائیه"] == ("اجرا", 0)
    assert ls.TITLE_SEARCH_MAP["اعلام وکالت"] == ("اعلام وکالت", 0)
    assert ls.TITLE_SEARCH_MAP["درخواست مطالبه پرونده"] == ("مطالبه", 0)
    assert ls.TITLE_SEARCH_MAP["سایر عناوین"] == ("سایر", 0)
    assert ls.TITLE_TARGET_TEXT_MAP["صدور اجرائیه"] == "تقاضای صدور اجرائیه"


def test_momenoiat_key_matches_keyboard_title():
    """کلید نگاشت باید دقیقاً متن دکمهٔ کیبورد/قالب اکسل باشد («ممنوعیت»)
    تا انتخاب کاربر به فال‌بک «دفا» (لایحه دفاعیه) نیفتد."""
    assert "درخواست ممنوعیت از خروج کشور" in ls.TITLE_SEARCH_MAP
    assert "درخواست منعیت از خروج کشور" not in ls.TITLE_SEARCH_MAP
    assert ls.TITLE_SEARCH_MAP["درخواست ممنوعیت از خروج کشور"][0] == "خروج"


def test_momenoiat_selects_correct_row_in_all_variants():
    """جستجوی «خروج» + متن هدف «ممنوعیت از خروج» باید در همهٔ حالت‌های
    محتمل املای سامانه، ردیف ممنوعیت از خروج را انتخاب کند (در بدترین
    حالت با فال‌بک ردیف اولِ فهرستِ فیلترشده با «خروج»)."""
    kw, row_idx = ls.TITLE_SEARCH_MAP["درخواست ممنوعیت از خروج کشور"]
    target = ls.TITLE_TARGET_TEXT_MAP["درخواست ممنوعیت از خروج کشور"]
    for items in KHORUJ_VARIANTS:
        title, _ = _simulate_select(kw, target, items, fallback_idx=row_idx)
        assert title is not None, f"برای فهرست {items} چیزی انتخاب نشد"
        assert "خروج" in title, f"عنوان انتخابی «{title}» کلمهٔ خروج ندارد"
        assert "ممنوع" in _norm(title) or "منع" in _norm(title), \
            f"عنوان انتخابی «{title}» مربوط به ممنوعیت از خروج نیست"


def test_every_keyboard_title_has_search_map_entry():
    """رگرسیون: هر عنوانی که کیبورد ربات (یا قالب اکسل دسته‌جمعی) ارسال
    می‌کند باید در TITLE_SEARCH_MAP کلید داشته باشد — وگرنه بی‌سروصدا به
    فال‌بک «دفا» می‌افتد (همان باگ ممنوعیت/منعیت)."""
    import keyboards
    import bulk_excel_v2
    for title in keyboards.LAVAYEH_TITLES:
        assert title in ls.TITLE_SEARCH_MAP, \
            f"عنوان کیبورد «{title}» در TITLE_SEARCH_MAP کلید ندارد"
    for title in bulk_excel_v2.LAVAYEH_TITLES:
        assert title in ls.TITLE_SEARCH_MAP, \
            f"عنوان اکسل «{title}» در TITLE_SEARCH_MAP کلید ندارد"
