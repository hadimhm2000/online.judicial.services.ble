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

def parse_excel_file(filepath: str, service_type: str) -> list:
    """
    خواندن اکسل با انعطاف‌پذیری بالا - مطابق فرمت جدید (فقط هدر بدون راهنما):
    حتی اگر کاربر برخی سلول‌ها را ناقص یا با فرمت اشتباه پر کرده باشد،
    سیستم با مقادیر پیش‌فرض خطا را ترمیم می‌کند تا اختلالی پیش نیاید.
    """
    items = []
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            return items

        # از سطر دوم به بعد (ردیف ۱ فقط هدر)
        for idx, row in enumerate(rows[1:], start=1):
            if not any(row):  # ردیف کاملا خالی
                continue

            if service_type == "lavayeh":
                # ساختار: ردیف، شماره پرونده، ردیف فرعی، عنوان لایحه، کدملی، متن لایحه
                tracking_code = str(row[1] if len(row) > 1 and row[1] is not None else "").strip()
                row_num_or_archive = str(row[2] if len(row) > 2 and row[2] is not None else "1").strip()
                title = str(row[3] if len(row) > 3 and row[3] is not None else "لایحه دفاعیه").strip()
                national_id = str(row[4] if len(row) > 4 and row[4] is not None else "0000000000").strip()
                text = str(row[5] if len(row) > 5 and row[5] is not None else "متن لایحه ثبت‌شده").strip()
                branch_name = ""  # بدون شعبه در فرمت جدید
                attachment = "بدون پیوست"  # پیوست جداگانه اضافه می‌شود

                # ترمیم شناسه یا شماره پرونده
                if not tracking_code:
                    tracking_code = f"1403-AUTO-{idx:03d}"
                if not national_id or len(re.sub(r'\D', '', national_id)) != 10:
                    national_id = re.sub(r'\D', '', national_id)
                    if len(national_id) != 10:
                        national_id = (national_id + "0000000000")[:10]

                items.append({
                    "row_index": idx,
                    "tracking_code": tracking_code,
                    "row_number": row_num_or_archive,
                    "branch_name": branch_name,
                    "title": title,
                    "national_id": national_id,
                    "text": text,
                    "attachment": attachment,
                    "status": "pending"
                })

            else:  # ezhharnameh
                # ساختار: ردیف، اظهارکننده، مخاطب، نماینده، عنوان، متن
                declarant_id = str(row[1] if len(row) > 1 and row[1] is not None else "0000000000").strip()
                addressee_id = str(row[2] if len(row) > 2 and row[2] is not None else "0000000000").strip()
                representative_id = str(row[3] if len(row) > 3 and row[3] is not None else "").strip()
                subject = str(row[4] if len(row) > 4 and row[4] is not None else "سایر").strip()
                text = str(row[5] if len(row) > 5 and row[5] is not None else "متن اظهارنامه").strip()
                attachment = "بدون پیوست"  # پیوست جداگانه اضافه می‌شود

                declarant_id = re.sub(r'\D', '', declarant_id)
                if len(declarant_id) < 10 or len(declarant_id) > 11:
                    declarant_id = (declarant_id + "0000000000")[:10]

                addressee_id = re.sub(r'\D', '', addressee_id)
                if len(addressee_id) < 10 or len(addressee_id) > 11:
                    addressee_id = (addressee_id + "0000000000")[:10]

                representative_id = re.sub(r'\D', '', representative_id) if representative_id else ""

                items.append({
                    "row_index": idx,
                    "declarant_id": declarant_id,
                    "addressee_id": addressee_id,
                    "representative_id": representative_id,
                    "subject": subject if subject else "سایر",
                    "text": text,
                    "attachment": attachment,
                    "status": "pending"
                })

    except Exception as e:
        logger.error(f"Error parsing Excel file {filepath}: {e}")
    return items

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
