"""
اتصال به گوگل شیت برای ثبت لاگ درخواست‌ها.

ستون‌های شیت (به ترتیب) وقتی از log_event استفاده می‌شود:
    ۱. تاریخ و ساعت
    ۲. نوع رویداد           → "ثبت" | "پرداخت" | "کنسل" | "خطای سامانه"
    ۳. نوع/عنوان درخواست
    ۴. نام کاربر
    ۵. آیدی عددی کاربر
    ۶. شماره پرونده/کد رهگیری
    ۷. توضیح سند
    ۸. وضعیت پرداخت
    ۹. توضیح/متن خطا (در صورت وجود)
"""
import asyncio
import datetime
import logging

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
gc = None
try:
    creds = Credentials.from_service_account_file("google-credentials.json", scopes=SCOPES)
    gc = gspread.authorize(creds)
    logging.info("✅ Google Sheets connected!")
except Exception as e:
    logging.warning(f"⚠️ فایل google-credentials.json پیدا نشد یا اتصال ناموفق بود: {e}")

async def append_to_sheet(row_data):
    def _append():
        if gc:
            try:
                gc.open("BotData").sheet1.append_row(row_data)
            except Exception as e:
                logging.error(f"Error appending to Google Sheet: {e}")
    try:
        await asyncio.to_thread(_append)
    except Exception as e:
        logging.error(f"Error appending to Google Sheet (thread): {e}")


async def log_event(
    event_type: str,
    query_type: str,
    full_name: str,
    user_id,
    tracking_code: str = "",
    national_id: str = "",
    doc_name: str = "",
    payment_status: str = "-",
    note: str = ""):
    """لاگ یکنواخت رویدادها در گوگل‌شیت."""
    row = [
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        event_type,
        query_type,
        full_name,
        str(user_id),
        tracking_code,
        doc_name,
        payment_status,
        note,
    ]
    await append_to_sheet(row)
