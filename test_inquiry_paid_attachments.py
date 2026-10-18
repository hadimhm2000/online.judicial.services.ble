"""تست محاسبهٔ برگ‌های پیوست پرداخت‌شده — اجرا: python -m pytest test_inquiry_paid_attachments.py"""
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

from scenarios import _paid_attachment_pages


def test_paid_pages_from_fee():
    # فقط هزینهٔ پایه (۵۰,۰۰۰) — پیوستی پرداخت نشده (سناریوی گزارش‌شده)
    assert _paid_attachment_pages({"payment_fee": 50000}) == 0
    assert _paid_attachment_pages({"payment_fee": 50000 + 11 * 5000}) == 11


def test_explicit_total_wins():
    assert _paid_attachment_pages({"payment_fee": 50000, "total_attachments": 3}) == 3


def test_unknown_fee_is_unrestricted():
    assert _paid_attachment_pages({}) is None
    assert _paid_attachment_pages({"payment_fee": 0}) is None
