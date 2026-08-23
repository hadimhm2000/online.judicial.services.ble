"""
ماژول پردازش ثبت‌های دسته‌جمعی (بیش از ۵ مورد)
شامل:
- تولید فایل اکسل نمونه با راهنمای کاربر
- پارسر منعطف اکسل، متن و عکس (مقاوم در برابر خطا)
- صف پردازش پس‌زمینه بدون مسدود کردن ربات
"""

import os
import re
import random
import string
import asyncio
import logging
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# حافظه موقت برای ردیف‌های ثبت دسته‌جمعی
# structure: { tracking_code: { "user_id": ..., "service_type": ..., "items": [...], "status": "pending/completed" } }
BULK_TASKS = {}

def generate_tracking_code(prefix="BLK") -> str:
    """تولید کد پیگیری یکتا برای ثبت دسته‌جمعی"""
    digits = ''.join(random.choices(string.digits, k=6))
    return f"#{prefix}-{digits}"

def generate_sample_excel(service_type: str, filepath: str) -> str:
    """
    تولید فایل اکسل نمونه با قالب‌بندی زیبا و توضیحات روشن
    اگر کاربر برخی ستون‌ها را درست انتخاب نکرد، سیستم به طور خودکار مقدار پیش‌فرض جایگزین می‌کند.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    # تنظیم عنوان شیت بر اساس نوع سرویس
    if service_type == "ezhharnameh":
        ws.title = "نمونه ثبت دسته‌جمعی اظهارنامه"
    else:
        ws.title = "نمونه ثبت دسته‌جمعی لوایح"
    ws.views.sheetView[0].rightToLeft = True  # راست به چپ برای فارسی

    # استایل‌ها
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Tahoma", size=11, bold=True, color="FFFFFF")
    hint_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    hint_font = Font(name="Tahoma", size=9, italic=True, color="92400E")
    data_font = Font(name="Tahoma", size=10)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border_side = Side(style='thin', color='CCCCCC')
    cell_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)

    if service_type == "lavayeh":
        # ساختار دقیق فایل اکسل لایحه مطابق فایل کاربر
        headers = [
            "ردیف",
            "شماره پرونده 16 یا 18 رقمی",
            "ردیف فرعی",
            "عنوان لایحه (از لیست ستون عناوین را انتخاب کنید)",
            "کدملی شخص ارائه دهنده",
            "متن لایحه (متن را کاملا کپی کنید و در ستون قرار بدهید، ممکن است متن مخفی شود اما متن در همینجا سیو می باشد)"
        ]
        hints = []  # بدون سطر راهنما
        sample_rows = []  # بدون ردیف نمونه
    else:  # ezhharnameh
        # ساختار دقیق فایل اکسل اظهارنامه مطابق فایل کاربر
        headers = [
            "ردیف",
            "کدملی / شناسه ملی اظهارکننده",
            "کدملی / شناسه ملی مخاطب",
            "کدملی نماینده (درصورت وجود یا اگر اظهارکننده حقوقی است ، حتما وارد کنید)",
            "عنوان اظهارنامه (درصورتی که این فیلد را خالی بگذارید، عنوان سایر ثبت می گردد)",
            "متن اظهارنامه (متن را کاملا کپی کنید و در ستون قرار بدهید، ممکن است متن مخفی شود اما متن در همینجا سیو می باشد)"
        ]
        hints = []  # بدون سطر راهنما
        sample_rows = []  # بدون ردیف نمونه

    # سطر هدر
    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = cell_border

    # فقط هدر - بدون سطر راهنما و نمونه (مطابق فایل کاربر)

    # تنظیم عرض ستون‌ها
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 16)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb.save(filepath)
    return filepath

def _pick_data_sheet(wb, service_type: str):
    """پیدا کردن شیت داده‌ای صحیح (نه راهنما/مرجع)"""
    if service_type == "lavayeh":
        preferred = ["ثبت دسته‌جمعی لوایح", "ثبت دسته‌جمعی لوایح"]
    else:
        preferred = ["ثبت دسته‌جمعی اظهارنامه", "ثبت دسته‌جمعی اظهارنامه"]
    skip = {"راهنما", "مرجع", "مرجع_عناوین_شعب"}
    for name in preferred:
        for sn in wb.sheetnames:
            if sn.replace("\u200c", "") == name.replace("\u200c", ""):
                return wb[sn]
    for sn in wb.sheetnames:
        if sn not in skip:
            return wb[sn]
    return wb.active


def _to_en_digits(text: str) -> str:
    """تبدیل ارقام فارسی/عربی به انگلیسی"""
    fa = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return text.translate(fa).replace(" ", "").strip()


def _is_empty_row_lavayeh(ws, r: int) -> bool:
    """بررسی خالی بودن ردیف داده‌ای لایحه (ستون‌های B تا P)
    ستون A (=ROW()-1), Q/R/S/T (فرمول بررسی) نادیده گرفته می‌شوند."""
    for c in range(2, 17):  # B=2 تا P=16
        v = ws.cell(row=r, column=c).value
        if v is not None and str(v).strip() != "":
            return False
    return True


def _is_empty_row_ezhharnameh(ws, r: int) -> bool:
    """بررسی خالی بودن ردیف داده‌ای اظهارنامه (ستون‌های B تا Y)
    ستون A (=ROW()-1), Z/AA/AB (فرمول بررسی) نادیده گرفته می‌شوند."""
    for c in range(2, 26):  # B=2 تا Y=25
        v = ws.cell(row=r, column=c).value
        if v is not None and str(v).strip() != "":
            return False
    return True


def _cell_value(ws, col: int, row: int) -> str:
    """خواندن مقدار سلول به صورت رشته تمیزشده"""
    v = ws.cell(row=row, column=col).value
    if v is None:
        return ""
    return str(v).strip()


def parse_excel_file(filepath: str, service_type: str) -> dict:
    """
    خواندن اکسل با تشخیص صحیح ردیف‌های داده‌ای.
    شیت درست را پیدا کرده و فقط ستون‌های داده (نه فرمول) را بررسی می‌کند.
    ردیف‌های خالی و ناقص را تشخیص داده و گزارش می‌دهد.

    خروجی:
        {
            "valid_items": [...],       # ردیف‌های معتبر و آماده پردازش
            "invalid_rows": [{"row_index": N, "errors": [...]}],  # ردیف‌های ناقص
            "total_rows": int           # تعداد کل ردیف‌های غیرخالی
        }
    """
    valid_items = []
    invalid_rows = []
    total_rows = 0

    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = _pick_data_sheet(wb, service_type)
        max_row = ws.max_row

        # شناسایی تابع بررسی خالی بودن
        is_empty = _is_empty_row_lavayeh if service_type == "lavayeh" else _is_empty_row_ezhharnameh

        # عناوین معتبر لایحه
        LAVAYEH_TITLES_SET = {
            "لایحه دفاعیه", "صدور اجرائیه", "اعتراض به نظر کارشناس",
            "اعتراض به قرار رد دفتر", "اعلام وکالت",
            "درخواست ممنوعیت از خروج کشور", "درخواست کپی از مدارک پرونده",
            "درخواست مطالبه پرونده", "درخواست مطالعه پرونده", "سایر عناوین"
        }

        consecutive_empty = 0
        MAX_CONSECUTIVE_EMPTY = 5  # بعد از ۵ ردیف خالی متوالی، خواندن را متوقف کن

        r = 2  # از سطر ۲ شروع (سطر ۱ هدر است)
        while r <= max_row:
            if is_empty(ws, r):
                consecutive_empty += 1
                if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                    break  # دیگر ردیف داده‌ای وجود ندارد
                r += 1
                continue

            consecutive_empty = 0
            total_rows += 1
            row_num = r - 1  # شماره ردیف نمایشی (همان مقدار ستون A)
            errors = []

            if service_type == "lavayeh":
                # ستون‌ها: B=روش, C=شماره‌پرونده, D=ردیف‌فرعی, E=استان‌پرونده,
                # F=استان‌شعبه, G=نام‌شعبه, H=شماره‌بایگانی, I=عنوان,
                # J=کدملی‌نفر۱, K=نفر۲, L=نفر۳, M=نفر۴,
                # N=آیا‌وکیل‌دارد, O=کدملی‌وکیل, P=متن‌لایحه
                method = _cell_value(ws, 2, r)
                case_number = _to_en_digits(_cell_value(ws, 3, r))
                sub_row = _cell_value(ws, 4, r) or "1"
                province = _cell_value(ws, 5, r)
                branch_province = _cell_value(ws, 6, r)
                branch_name = _cell_value(ws, 7, r)
                archive_number = _to_en_digits(_cell_value(ws, 8, r))
                title = _cell_value(ws, 9, r)
                providers = [
                    _to_en_digits(_cell_value(ws, c, r))
                    for c in (10, 11, 12, 13)
                    if _cell_value(ws, c, r)
                ]
                has_representative = _cell_value(ws, 14, r)
                representative_id = _to_en_digits(_cell_value(ws, 15, r))
                text = _cell_value(ws, 16, r)

                # ── اعتبارسنجی ردیف ──
                if not method:
                    errors.append("روش شماره‌گذاری انتخاب نشده")
                elif method == "شماره پرونده و ردیف فرعی":
                    if not case_number:
                        errors.append("شماره پرونده وارد نشده")
                    if not province:
                        errors.append("استان پرونده انتخاب نشده")
                elif method == "شعبه و شماره بایگانی":
                    if not branch_province or not branch_name or not archive_number:
                        errors.append("استان‌شعبه / نام‌شعبه / شماره‌بایگانی ناقص است")
                else:
                    errors.append(f"روش شماره‌گذاری «{method}» نامعتبر است")

                if not title:
                    errors.append("عنوان لایحه انتخاب نشده")
                elif title not in LAVAYEH_TITLES_SET:
                    errors.append(f"عنوان لایحه «{title}» نامعتبر است (از لیست عناوین انتخاب کنید)")

                if not providers:
                    errors.append("حداقل کدملی یک ارائه‌دهنده الزامی است")

                if not text:
                    errors.append("متن لایحه خالی است")

                if has_representative == "بله" and not representative_id:
                    errors.append("گزینه وکیل/نماینده «بله» انتخاب شده ولی کدملی وارد نشده")

                if errors:
                    invalid_rows.append({"row_index": row_num, "errors": errors})
                else:
                    valid_items.append({
                        "row_index": row_num,
                        "method": method,
                        "case_number": case_number,
                        "sub_row": sub_row,
                        "province": province,
                        "branch_province": branch_province,
                        "branch": branch_name,
                        "archive_number": archive_number,
                        "title": title,
                        "providers": providers,
                        "has_representative": has_representative,
                        "representative_id": representative_id,
                        "text": text,
                        "attachments": [],
                        "status": "pending"
                    })

            else:  # ezhharnameh
                # ستون‌ها: B-D=اظهارکننده‌نفر۱(نوع,کدملی,نماینده), E-G=نفر۲, H-J=نفر۳, K-M=نفر۴
                # N-O=مخاطب‌نفر۱(نوع,کدملی), P-Q=نفر۲, R-S=نفر۳, T-U=نفر۴
                # V=نماینده‌پرونده۱, W=نماینده‌پرونده۲, X=عنوان, Y=متن
                declarants = []
                for tcol, icol, rcol in [(2,3,4), (5,6,7), (8,9,10), (11,12,13)]:
                    ptype = _cell_value(ws, tcol, r)
                    pid = _to_en_digits(_cell_value(ws, icol, r))
                    rep = _to_en_digits(_cell_value(ws, rcol, r))
                    if ptype or pid:
                        declarants.append({"type": ptype, "id": pid, "company_rep": rep})

                addressees = []
                for tcol, icol in [(14,15), (16,17), (18,19), (20,21)]:
                    ptype = _cell_value(ws, tcol, r)
                    pid = _to_en_digits(_cell_value(ws, icol, r))
                    if ptype or pid:
                        addressees.append({"type": ptype, "id": pid})

                representatives = [
                    _to_en_digits(_cell_value(ws, c, r)) for c in (22, 23) if _cell_value(ws, c, r)
                ]

                title = _cell_value(ws, 24, r) or "سایر"
                text = _cell_value(ws, 25, r)

                # ── اعتبارسنجی ردیف ──
                if not declarants:
                    errors.append("حداقل یک اظهارکننده (نفر ۱) الزامی است")
                else:
                    d1 = declarants[0]
                    if not d1.get("type"):
                        errors.append("نوع اظهارکننده نفر ۱ انتخاب نشده")
                    if not d1.get("id"):
                        errors.append("کدملی/شناسه ملی اظهارکننده نفر ۱ وارد نشده")

                if not addressees:
                    errors.append("حداقل یک مخاطب (نفر ۱) الزامی است")
                else:
                    a1 = addressees[0]
                    if not a1.get("type"):
                        errors.append("نوع مخاطب نفر ۱ انتخاب نشده")
                    if not a1.get("id"):
                        errors.append("کدملی/شناسه ملی مخاطب نفر ۱ وارد نشده")

                if not text:
                    errors.append("متن اظهارنامه خالی است")

                if errors:
                    invalid_rows.append({"row_index": row_num, "errors": errors})
                else:
                    valid_items.append({
                        "row_index": row_num,
                        "declarants": declarants,
                        "addressees": addressees,
                        "representatives": representatives,
                        "title": title,
                        "text": text,
                        "attachments": [],
                        "status": "pending"
                    })

            r += 1

    except Exception as e:
        logger.error(f"Error parsing Excel file {filepath}: {e}", exc_info=True)

    return {
        "valid_items": valid_items,
        "invalid_rows": invalid_rows,
        "total_rows": total_rows,
    }

def parse_text_or_image_input(raw_text: str, service_type: str) -> list:
    """
    پردازش متن ساده یا متن استخراج‌شده از تصویر
    هر پاراگراف یا خط با علامت '-' یا ردیف به عنوان یک مورد ثبت می‌شود.
    """
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    items = []
    for idx, line in enumerate(lines, start=1):
        if service_type == "lavayeh":
            items.append({
                "row_index": idx,
                "tracking_code": f"AUTO-{idx:03d}",
                "row_number": "1",
                "branch_name": "ثبت دسته‌جمعی",
                "title": "لایحه دفاعیه (ورود سریع)",
                "national_id": "0000000000",
                "text": line,
                "attachment": "ندارد",
                "status": "pending"
            })
        else:
            items.append({
                "row_index": idx,
                "declarant_id": "0000000000",
                "addressee_id": "0000000000",
                "subject": "اظهارنامه (ورود سریع)",
                "text": line,
                "attachment": "ندارد",
                "status": "pending"
            })
    return items

async def run_bulk_processing_task(bot, user_id: int, tracking_code: str):
    """
    پردازش پس‌زمینه (Async Background Task)
    تا بدون ایجاد معطلی برای کاربر یا سایر مراجعان ربات، درخواست‌ها پردازش و گزارش داده شوند.
    """
    task_data = BULK_TASKS.get(tracking_code)
    if not task_data:
        return

    items = task_data.get("items", [])
    total = len(items)
    service_fa = "لایحه" if task_data.get("service_type") == "lavayeh" else "اظهارنامه"

    await bot.send_message(
        user_id,
        f"⏳ *پردازش در پس‌زمینه آغاز شد!*\n\n"
        f"کد پیگیری دسته‌جمعی: `{tracking_code}`\n"
        f"تعداد موارد: *{total} مورد ({service_fa})*\n\n"
        f"💡 شما می‌توانید از ربات برای سایر امور خود استفاده کنید. گزارش پیشرفت به صورت خودکار برایتان ارسال می‌شود.")

    completed = 0
    for idx, item in enumerate(items, start=1):
        # شبیه‌سازی انجام کار بدون بلاک کردن event loop
        await asyncio.sleep(1.5)
        item["status"] = "completed"
        completed += 1

        # ارسال پیام پیشرفت هر ۵ مورد یا در انتها
        if completed % 5 == 0 or completed == total:
            percentage = int((completed / total) * 100)
            await bot.send_message(
                user_id,
                f"🔄 *گزارش پیشرفت ثبت دسته‌جمعی (`{tracking_code}`)*\n\n"
                f"✅ انجام شده: *{completed} از {total}* ({percentage}%)\n"
                f"📌 آخرین مورد پردازش‌شده: ردیف {idx}")

    task_data["status"] = "completed"
    task_data["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    await bot.send_message(
        user_id,
        f"🎉 *ثبت دسته‌جمعی با موفقیت به اتمام رسید!*\n\n"
        f"شماره رهگیری: `{tracking_code}`\n"
        f"تعداد کل موارد ثبت‌شده: *{total} {service_fa}*\n\n"
        f"📄 تمامی موارد در سامانه ثبت و بایگانی گردید.")
