# -*- coding: utf-8 -*-
"""
تولید PDF گزارش استعلام ارزش منطقه‌ای با WeasyPrint.

هدر: عکس واقعی اسکرین‌شات سامانه مالیاتی
بدنه: تمام اطلاعات ساختاریافته از tax.gov.ir
پایان: استان، آدرس، متراژ + محاسبه ارزش کل برای هر ۳ کاربری
"""

import base64
import datetime
import html as html_lib
import logging
import os

from weasyprint import HTML

logger = logging.getLogger(__name__)

# ═══ مسیر هدر ═══
DEFAULT_HEADER_IMAGE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tax_header.jpg"
)

_PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


# ═══ فیلدهای بخش اطلاعات مکان (۹ فیلد اول) ═══
SYSTEM_FIELDS = [
    "اداره کل امور مالیاتی",
    "واحد مرتبط مالیاتی سنیم املاک",
    "واحد مرتبط مالیاتی سنیم حقوقی",
    "واحد مرتبط مالیاتی سنیم حقیقی",
    "واحد مرتبط مالیاتی حقوقی",
    "واحد مرتبط مالیاتی حقیقی",
    "واحد مرتبط مالیاتی ارث",
    "شماره بلوک بر اساس دفترچه ارزش معاملاتی ملک",
    "شماره ردیف بر اساس دفترچه ارزش معاملاتی ملک",
]

# ═══ فیلدهای ارزش معاملاتی (۳ فیلد) ═══
VALUE_FIELDS = [
    "ارزش معاملاتی مسکونی",
    "ارزش معاملاتی اداری",
    "ارزش معاملاتی تجاری",
]


def _to_pd(n) -> str:
    """تبدیل عدد به رقم فارسی."""
    return str(n).translate(str.maketrans("0123456789", _PERSIAN_DIGITS))


def _gregorian_to_jalali(gy, gm, gd):
    """تبدیل تاریخ میلادی به شمسی."""
    try:
        import jdatetime
        j = jdatetime.date.fromgregorian(year=gy, month=gm, day=gd)
        return j.year, j.month, j.day
    except ImportError:
        g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        gy2, gm2, gd2 = gy - 1600, gm - 1, gd - 1
        g_days_no = (365 * gy2 + (gy2 + 3) // 4
                    - (gy2 + 99) // 100 + (gy2 + 399) // 400)
        for i in range(gm2):
            g_days_no += g_d_m[i + 1]
        g_days_no += gd2
        j_days_no = g_days_no - 79
        j_np = j_days_no // 12053
        j_days_no %= 12053
        jy = 979 + 33 * j_np + 4 * (j_days_no // 1461)
        j_days_no %= 1461
        if j_days_no >= 366:
            jy += (j_days_no - 1) // 365
            j_days_no = (j_days_no - 1) % 365
        jm, jd = 1, 1
        for i in range(11):
            if i < 6:
                if j_days_no < 31 * (i + 1):
                    jm = i + 1
                    jd = j_days_no - 31 * i + 1
                    break
            else:
                if j_days_no < 186 + 30 * (i - 5):
                    jm = i + 1
                    jd = j_days_no - 186 - 30 * (i - 6) + 1
                    break
        return jy, jm, jd


def _get_persian_date() -> str:
    now = datetime.datetime.now()
    try:
        jy, jm, jd = _gregorian_to_jalali(now.year, now.month, now.day)
    except Exception:
        jy, jm, jd = now.year, now.month, now.day
    return f"{_to_pd(jd)} {_PERSIAN_MONTHS[jm - 1]} {_to_pd(jy)}"


def _get_persian_time() -> str:
    now = datetime.datetime.now()
    return f"{_to_pd(now.hour):02s}:{_to_pd(now.minute):02s}"


def _fmt(n: int) -> str:
    """فرمت عدد با جداکننده هزارگان فارسی."""
    return f"{n:,}".translate(str.maketrans("0123456789", _PERSIAN_DIGITS))


def _esc(s: str) -> str:
    return html_lib.escape(s or "", quote=True)


def _header_base64(image_path: str) -> str:
    """خواندن عکس هدر و تبدیل به base64 data-uri."""
    if not os.path.exists(image_path):
        logger.warning(f"[RV-PDF] عکس هدر یافت نشد: {image_path}")
        return ""
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


def _get_field_value(tax_result: dict, field_name: str) -> str:
    """
    مقدار یک فیلد را از نتیجه ساختاریافته استخراج می‌کند.
    اول از فیلدهای_ساختاریافته می‌گرده، بعد از فیلدهای_خام.
    اگر پیدا نشد "-" برمی‌گرداند.
    """
    structured = tax_result.get("فیلدهای_ساختاریافته", {})
    val = structured.get(field_name)
    if val and str(val).strip():
        return str(val).strip()

    # فال‌بک: جستجو در فیلدهای خام
    def norm(t):
        return t.replace("ي", "ی").replace("ك", "ک").strip()

    raw = tax_result.get("همه_فیلدهای_خام_صفحه", {})
    norm_field = norm(field_name)
    for k, v in raw.items():
        norm_key = norm(k)
        if norm_field in norm_key or norm_key in norm_field:
            if v and str(v).strip():
                return str(v).strip()
    return "-"


def build_regional_value_pdf(
    tax_result: dict,
    province: str,
    address: str,
    area: float,
    land_use: str,
    total_value: int,
    output_path: str,
    header_image_path: str = None,
    all_land_use_values: dict = None,
) -> bool:
    """
    ساخت PDF گزارش ارزش منطقه‌ای.

    Args:
        tax_result: دیکشنری ساختاریافته خروجی build_full_result()
            {"سال": "1405", "فیلدهای_ساختاریافته": {...}, ...}
        province: نام استان
        address: آدرس کامل
        area: متراژ عرصه (متر مربع)
        land_use: کاربری زمین (مسکونی/تجاری/اداری)
        total_value: مبلغ کل (ریال)
        output_path: مسیر خروجی PDF
        header_image_path: مسیر عکس هدر (اختیاری)
        all_land_use_values: دیکشنری هر ۳ ارزش (مسکونی/تجاری/اداری → عدد ریال)

    Returns:
        True در صورت موفقیت
    """
    date_str = _get_persian_date()
    time_str = _get_persian_time()
    tax_year = tax_result.get("سال", "1405")

    # عکس هدر
    img_path = header_image_path or DEFAULT_HEADER_IMAGE
    header_b64 = _header_base64(img_path)

    # ═══ ساخت ردیف‌های اطلاعات مکان انتخابی ═══
    system_rows = ""
    for field in SYSTEM_FIELDS:
        val = _get_field_value(tax_result, field)
        system_rows += f"""
                <tr>
                    <td class="field-label">{_esc(field)}</td>
                    <td class="field-value">{_esc(val)}</td>
                </tr>"""

    # ═══ ساخت ردیف‌های ارزش معاملاتی ═══
    value_rows = ""
    for field in VALUE_FIELDS:
        val = _get_field_value(tax_result, field)
        value_rows += f"""
                <tr>
                    <td class="field-label">{_esc(field)}</td>
                    <td class="field-value">{_esc(val)}</td>
                </tr>"""

    # مقدار واحد کاربری انتخاب‌شده
    unit_value = int(total_value // area) if area > 0 else 0

    # هر ۳ ارزش کل
    all_totals_html = ""
    all_values = all_land_use_values or {}
    for lu_name, lu_val in all_values.items():
        if lu_val is not None:
            lu_total = int(lu_val * area)
            is_selected = (lu_name == land_use)
            row_class = "selected-row" if is_selected else ""
            star = " ★" if is_selected else ""
            all_totals_html += f"""
                    <tr class="{row_class}">
                        <td class="field-label">ارزش کل {lu_name}{star}</td>
                        <td class="field-value">{_fmt(lu_total)} ریال</td>
                    </tr>"""

    # هدر
    if header_b64:
        header_html = f"""    <div class="header-img-wrap">
        <img src="{header_b64}" class="header-img" alt="هدر سامانه مالیاتی">
    </div>"""
    else:
        header_html = f"""    <div class="header-fallback">
        <div class="header-fallback-right">
            <div class="org-main">وزارت امور اقتصادی و دارایی</div>
            <div class="org-sub">سازمان امور مالیاتی کشور</div>
        </div>
    </div>"""

    html_content = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 0;
    }}
    * {{
        box-sizing: border-box;
    }}
    body {{
        margin: 0;
        padding: 0;
        font-family: 'Noto Sans SC', 'Vazirmatn', Tahoma, 'B Nazanin', Arial, sans-serif;
        direction: rtl;
        color: #000;
        background: #fff;
    }}

    /* ═══ هدر عکس واقعی ═══ */
    .header-img-wrap {{
        width: 100%;
        overflow: hidden;
        line-height: 0;
    }}
    .header-img {{
        width: 100%;
        height: auto;
        display: block;
    }}

    /* ═══ هدر متنی (فال‌بک) ═══ */
    .header-fallback {{
        background: #1a1a2e;
        color: #fff;
        padding: 18px 30px 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        min-height: 90px;
        border-bottom: 3px solid #4a90d9;
    }}
    .org-main {{ font-size: 15px; font-weight: 700; margin-bottom: 4px; }}
    .org-sub {{ font-size: 18px; font-weight: 700; color: #a8c8f0; }}

    /* ═══ نوار عنوان و تاریخ ═══ */
    .title-bar {{
        background: #2c5282;
        color: #fff;
        padding: 10px 24px;
        font-size: 15px;
        font-weight: 700;
        text-align: center;
    }}
    .date-bar {{
        background: #f0f0f0;
        color: #333;
        padding: 6px 24px;
        font-size: 12px;
        display: flex;
        justify-content: space-between;
        border-bottom: 1px solid #ddd;
    }}

    /* ═══ محتوا ═══ */
    .content {{
        padding: 14px 24px 20px;
    }}

    /* ═══ جدول اطلاعات ═══ */
    .section-header {{
        background: #d6e4f0;
        font-weight: 700;
        font-size: 13px;
        padding: 8px 12px;
        border: 1px solid #8faabe;
        border-bottom: none;
        color: #1a3a5c;
    }}
    .section-header-blue {{
        background: #c5d9ed;
        font-weight: 700;
        font-size: 13px;
        padding: 8px 12px;
        border: 1px solid #8faabe;
        border-bottom: none;
        color: #1a3a5c;
    }}
    .section-header-green {{
        background: #d4edda;
        font-weight: 700;
        font-size: 13px;
        padding: 8px 12px;
        border: 1px solid #8aaa8a;
        border-bottom: none;
        color: #155724;
    }}
    table.info-list {{
        width: 100%;
        border-collapse: collapse;
    }}
    table.info-list td {{
        border: 1px solid #8faabe;
        padding: 6px 12px;
        font-size: 12.5px;
        vertical-align: middle;
    }}
    table.info-list td.field-label {{
        width: 50%;
        font-weight: 700;
        background: #f5f9fc;
        color: #1a3a5c;
    }}
    table.info-list td.field-value {{
        width: 50%;
        color: #000;
    }}

    /* جدول سبز (مشخصات درخواست) */
    table.request-table td {{
        border-color: #8aaa8a;
    }}
    table.request-table td.field-label {{
        background: #f0f7f0;
        color: #155724;
    }}

    /* ردیف انتخاب‌شده (کاربری انتخاب‌شده) */
    tr.selected-row td {{
        background: #fff3cd !important;
        font-weight: 700;
    }}

    /* ═══ ارزش کل ═══ */
    .total-box {{
        margin-top: 16px;
        background: #1a3a5c;
        color: #fff;
        border-radius: 6px;
        padding: 14px 20px;
        text-align: center;
    }}
    .total-label {{ font-size: 13px; margin-bottom: 4px; opacity: 0.9; }}
    .total-amount {{ font-size: 20px; font-weight: 700; }}
    .total-calc {{ font-size: 11px; margin-top: 4px; opacity: 0.7; }}

    /* فوتر */
    .footer {{
        margin-top: 20px;
        text-align: center;
        font-size: 9.5px;
        color: #aaa;
        padding: 8px;
        border-top: 1px solid #e0e0e0;
    }}
</style>
</head>
<body>

{header_html}

<!-- نوار عنوان -->
<div class="title-bar">جستجوی بلوک و ردیف و اداره مالیاتی مرتبط — سال {_esc(tax_year)}</div>

<!-- نوار تاریخ -->
<div class="date-bar">
    <span>{date_str}</span>
    <span>ساعت: {time_str}</span>
</div>

<!-- محتوا -->
<div class="content">

    <!-- ═══ بخش اول: اطلاعات مکان انتخابی ═══ -->
    <div class="section-header">اطلاعات مکان انتخابی</div>
    <table class="info-list">
        <tbody>
            {system_rows}
        </tbody>
    </table>

    <!-- ═══ بخش دوم: ارزش معاملاتی ═══ -->
    <div class="section-header-blue" style="margin-top: 4px;">ارزش معاملاتی</div>
    <table class="info-list">
        <tbody>
            {value_rows}
        </tbody>
    </table>

    <!-- ═══ بخش سوم: مشخصات درخواست ═══ -->
    <div class="section-header-green" style="margin-top: 4px;">مشخصات درخواست</div>
    <table class="info-list request-table">
        <tbody>
            <tr>
                <td class="field-label">استان</td>
                <td class="field-value">{_esc(province)}</td>
            </tr>
            <tr>
                <td class="field-label">آدرس اعلام‌شده</td>
                <td class="field-value">{_esc(address)}</td>
            </tr>
            <tr>
                <td class="field-label">متراژ عرصه</td>
                <td class="field-value">{_to_pd(int(area))} متر مربع</td>
            </tr>
            <tr>
                <td class="field-label">کاربری انتخاب‌شده</td>
                <td class="field-value">{_esc(land_use)} ★</td>
            </tr>
            {all_totals_html}
        </tbody>
    </table>

    <!-- ═══ ارزش کل ═══ -->
    <div class="total-box">
        <div class="total-label">مبلغ ارزش منطقه‌ای کل ({_esc(land_use)})</div>
        <div class="total-amount">{_fmt(total_value)} ریال</div>
        <div class="total-calc">
            {_to_pd(int(area))} متر مربع × {_fmt(unit_value)} ریال = {_fmt(total_value)} ریال
        </div>
    </div>

    <div class="footer">
        این گزارش صرفاً بر اساس استعلام از سامانه سازمان امور مالیاتی کشور تولید شده و جنبه اطلاع‌رسانی دارد.
    </div>
</div>

</body>
</html>"""

    try:
        html_doc = HTML(string=html_content)
        html_doc.write_pdf(output_path)
        logger.info(f"[RV-PDF] PDF ساخته شد: {output_path}")
        return True
    except Exception as e:
        logger.error(f"[RV-PDF] خطا در ساخت PDF: {e}", exc_info=True)
        return False
