"""تست‌های اصلاحات ۱۴۰۵/۰۸ (دستور کارفرما):

۱) بازهٔ معتبر کد رهگیری استعلام: ۱۶ رقم و پیشوند ۱۳۹۵۲۲۰ تا ۱۴۰۵۲۲۰
   (۱۳۹۵۲۲۰ و ۱۳۹۶۲۲۰ و ... تا ۱۴۰۵۲۲۰) — در handlers و اکسل دسته‌جمعی.
۲) گیت وضعیت چاپ نهایی روزانهٔ ۱۷:۰۰ بر اساس جدول «خلاصهٔ» پرونده:
   • لایحه: ردیف «ارسال شده به» پر → تایید؛ نبود/خالی بودن (مثل «احراز هويت شده») → عدم ارسال.
   • اظهارنامه/دادخواست: «آخرین وضعیت» = «ارسال شده به مرجع قضايي» → تایید؛ وگرنه عدم ارسال.
   در عدم تایید: PDF نگه داشته می‌شود، به کاربر نمی‌رود، مدیر اطلاع می‌یابد و
   با دکمهٔ «📤 ارسال به کاربر» هر زمان خواست ارسال می‌کند.

اجرای تست‌ها:
    BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_final_print_status_gate.py
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import final_print
import handlers
import bulk_inquiry_excel
import scenarios

TC = "1395220018338769"  # ۱۶ رقم با پیشوند ۱۳۹۵۲۲۰


# ══════════════════════════════════════════════════════════════════════
# ۱) بازهٔ کد رهگیری — ۱۳۹۵۲۲۰ تا ۱۴۰۵۲۲۰، ۱۶ رقمی
# ══════════════════════════════════════════════════════════════════════

def test_tracking_code_valid_bounds():
    """پیشوندهای ۱۳۹۵۲۲۰ و ۱۳۹۶۲۲۰ و ... تا ۱۴۰۵۲۲۰ مجاز؛ بیرون بازه نامعتبر."""
    # مجاز — ابتدا و انتهای بازه
    assert handlers._is_valid_tracking_code("1395220018338769")
    assert handlers._is_valid_tracking_code("1405220018338769")
    # مجاز — سال‌های میانی
    for prefix in (1395220, 1396220, 1397220, 1398220, 1399220,
                   1400220, 1401220, 1402220, 1403220, 1404220):
        assert handlers._is_valid_tracking_code(f"{prefix}018338769"), prefix
    # نامعتبر — بیرون بازه
    assert not handlers._is_valid_tracking_code("1394220018338769")   # ۱۳۹۴ — قبل از بازه
    assert not handlers._is_valid_tracking_code("1394199018338769")
    assert not handlers._is_valid_tracking_code("1406220018338769")   # ۱۴۰۶ — بعد از بازه
    assert not handlers._is_valid_tracking_code("1415220018338769")
    # نامعتبر — تعداد رقم
    assert not handlers._is_valid_tracking_code("140522001833876")    # ۱۵ رقم
    assert not handlers._is_valid_tracking_code("14052200183387699")  # ۱۷ رقم
    assert not handlers._is_valid_tracking_code("")
    assert not handlers._is_valid_tracking_code("14052200183387a9")


def test_tracking_code_valid_bounds_bulk_excel():
    """همان قاعده در اعتبارسنجی اکسل استعلام دسته‌جمعی."""
    assert bulk_inquiry_excel._is_valid_tracking_code("1395220018338769")
    assert bulk_inquiry_excel._is_valid_tracking_code("1405220018338769")
    assert not bulk_inquiry_excel._is_valid_tracking_code("1394220018338769")
    assert not bulk_inquiry_excel._is_valid_tracking_code("1406220018338769")
    assert not bulk_inquiry_excel._is_valid_tracking_code("140522001833876")
    assert not bulk_inquiry_excel._is_valid_tracking_code("14052200183387699")


def test_invalid_tracking_message_tells_user_examples():
    """پیام خطا باید بگوید کد اشتباه است و مثالِ شروع درست (1405220 یا 1404220 و ...) بدهد."""
    import inspect
    src = inspect.getsource(handlers.process_tracking_code)
    assert "اشتباه" in src                     # «کد رهگیری اشتباه است»
    assert "۱۶ رقم" in src
    assert "۱۳۹۵۲۲۰" in src and "۱۴۰۵۲۲۰" in src  # بازهٔ کامل
    assert "1405220" in src and "1404220" in src  # مثال‌های خواسته‌شدهٔ کارفرما
    # همان پیام در فرصت اصلاح رایگان
    src2 = inspect.getsource(handlers.process_corrected_tracking_code)
    assert "اشتباه" in src2 and "1405220" in src2


def test_constants_expose_range():
    assert (handlers.TRACKING_CODE_PREFIX_MIN, handlers.TRACKING_CODE_PREFIX_MAX) == (1395220, 1405220)
    assert handlers.TRACKING_CODE_LENGTH == 16
    assert (bulk_inquiry_excel.TRACKING_CODE_PREFIX_MIN,
            bulk_inquiry_excel.TRACKING_CODE_PREFIX_MAX) == (1395220, 1405220)


# ══════════════════════════════════════════════════════════════════════
# ۲) قواعد تایید چاپ نهایی — check_portal_status
# ══════════════════════════════════════════════════════════════════════

def test_bill_rule_approved_with_sent_to():
    """نمونهٔ ۱ فایل پیوست (لایحه): «ارسال شده به: دادگاههاي تجديدنظر استان تهران» → تایید."""
    v = final_print.check_portal_status(
        "لایحه",
        {"last_status": "ثبت در دفتر انديکارتور شعبه",
         "sent_to": "دادگاههاي تجديدنظر استان تهران"})
    assert v["approved"] is True


def test_bill_rule_not_approved_without_sent_to():
    """نمونهٔ ۲ فایل پیوست (لایحه): «احراز هويت شده» بدون ردیف «ارسال شده به» → ارسال نشود."""
    v = final_print.check_portal_status("لایحه", {"last_status": "احراز هويت شده", "sent_to": None})
    assert v["approved"] is False
    assert v["last_status"] == "احراز هویت شده"  # نرمال‌شدهٔ «احراز هويت شده"
    v = final_print.check_portal_status("لایحه", {"last_status": "احراز هويت شده", "sent_to": ""})
    assert v["approved"] is False


def test_petition_rule_approved_when_sent_to_judicial():
    """نمونهٔ اظهارنامه/دادخواست فایل پیوست: «آخرین وضعیت: ارسال شده به مرجع قضايي» → تایید."""
    for cat in ("اظهارنامه", "دادخواست بدوی", "دعاوی اعتراضی", "دعاوی دادگاههای صلح"):
        v = final_print.check_portal_status(
            cat, {"last_status": "ارسال شده به مرجع قضايي", "sent_to": ""})
        assert v["approved"] is True, cat
    # دادخواست با «ارسال شده به» پر هم فقط با وضعیت تایید می‌شود
    v = final_print.check_portal_status(
        "دادخواست بدوی",
        {"last_status": "ارسال شده به مرجع قضايي",
         "sent_to": "مجتمع دادگاههاي عمومي و انقلاب شهرستان آمل"})
    assert v["approved"] is True


def test_petition_rule_not_approved_other_status():
    """وضعیت غیر «ارسال شده به مرجع قضايي» → عدم تایید (ارسال به کاربر نباید بشود)."""
    for cat in ("اظهارنامه", "دادخواست بدوی"):
        v = final_print.check_portal_status(cat, {"last_status": "احراز هويت شده", "sent_to": ""})
        assert v["approved"] is False, cat
        v = final_print.check_portal_status(cat, {"last_status": "ثبت در دفتر انديکارتور شعبه", "sent_to": ""})
        assert v["approved"] is False, cat


def test_extraction_missing_approves_by_default():
    """اگر جدول خلاصه خوانده نشد → تایید (رفتار قبلی حفظ می‌شود)."""
    assert final_print.check_portal_status("لایحه", None)["approved"] is True
    assert final_print.check_portal_status("اظهارنامه", None)["approved"] is True
    assert final_print.check_portal_status("دادخواست بدوی", {})["approved"] is True


def test_norm_fa_handles_arabic_chars_and_zwnj():
    assert final_print._norm_fa("ارسال\u200cشده به مرجع قضايي ") == "ارسال شده به مرجع قضایی"
    assert final_print._norm_fa(None) == ""
    assert final_print._norm_fa("احراز\u00a0هويت شده") == "احراز هویت شده"


# ══════════════════════════════════════════════════════════════════════
# ۳) جریان نگهداری + دکمهٔ مدیر
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def fp_store(tmp_path, monkeypatch):
    """ذخیرهٔ چاپ نهایی و PDFهای نگه‌داشته و pending_cases به پوشهٔ موقت."""
    monkeypatch.setattr(final_print, "STORE_FILE", str(tmp_path / "final_print_queue.json"))
    monkeypatch.setattr(final_print, "HELD_DIR", str(tmp_path / "held_final_prints"))
    try:
        import pending_cases
        monkeypatch.setattr(pending_cases, "STORE_FILE", str(tmp_path / "pending_cases.json"))
    except Exception:
        pass
    yield tmp_path


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _callback(data: str, user_id: int = 1):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.photo = None
    cb.message.document = None
    cb.message.edit_text = AsyncMock()
    return cb


def test_held_items_are_not_due_for_daily_run():
    """موارد held دیگر در اجرای روزانه تلاش نمی‌شوند (فقط دکمهٔ مدیر)."""
    data = {"items": [{
        "user_id": 42, "tracking_code": TC, "status": "held",
        "sign_required": True, "signed": True,
        "signed_date": "2020-01-01", "registered_date": "2020-01-01",
        "last_attempt_date": "",
    }], "last_run_date": "", "on_demand": []}
    assert final_print._due_items(data, "2026-11-10") == []
    data["items"][0]["status"] = "pending"
    assert len(final_print._due_items(data, "2026-11-10")) == 1


async def test_hold_for_admin_keeps_pdf_and_notifies_admin(fp_store):
    """عدم تایید: PDF به held منتقل می‌شود، مورد held می‌شود و مدیر دکمهٔ ارسال می‌گیرد."""
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    pdf = fp_store / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake-final-print")

    bot = _bot()
    ok = await final_print.hold_for_admin(
        bot, 42, TC, "لایحه", "پرونده هنوز به مرجع ارسال نشده است",
        "احراز هويت شده", str(pdf))
    assert ok is True

    # PDF از مسیر موقت به پوشهٔ نگه‌داشته‌شده‌ها منتقل شد
    assert not pdf.exists()
    held = final_print.held_pdf_path(42, TC)
    assert os.path.exists(held) and Path(held).parent.name == "held_final_prints"

    # مورد در صف held شد (نه sent/failed — یعنی فردا تلاش نمی‌شود)
    with final_print._lock:
        items = final_print._load()["items"]
    assert items[0]["status"] == "held"
    assert items[0]["held_last_status"] == "احراز هويت شده"

    # اطلاع به مدیر + دکمهٔ ارسال
    assert bot.send_message.await_count == 1
    args = bot.send_message.await_args.args
    kwargs = bot.send_message.await_args.kwargs
    assert args[0] == 1  # ADMIN_ID=1
    kb = kwargs["reply_markup"]
    cb_data = kb.inline_keyboard[0][0].callback_data
    assert cb_data == f"fpsend:42:{TC}"
    assert kb.inline_keyboard[0][0].text == "📤 ارسال به کاربر"
    assert "ارسال نشد" in str(args[1])


async def test_admin_button_sends_held_pdf_to_user(fp_store, monkeypatch):
    """دکمهٔ مدیر: هر زمان که بزند، همان پرونده برای کاربر ارسال می‌شود."""
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    pdf = fp_store / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake-final-print")
    bot = _bot()
    await final_print.hold_for_admin(bot, 42, TC, "لایحه", "علت تست", "احراز هويت شده", str(pdf))

    sent = {}

    async def fake_send(chat_id, file_path, filename=None, caption=None, reply_markup=None):
        sent.update(chat_id=chat_id, path=file_path, filename=filename, caption=caption)
        return {"message_id": 77}

    monkeypatch.setattr(final_print, "send_document_direct", fake_send)

    callback = _callback(f"fpsend:42:{TC}")
    await final_print.cb_send_held_final_print(callback, bot)

    # برای کاربر (نه مدیر) با کپشن چاپ نهایی ارسال شد
    assert sent["chat_id"] == 42
    assert "چاپ نهایی" in sent["caption"] and TC in sent["caption"]
    assert os.path.basename(sent["path"]).startswith("42_" + TC)

    # مورد sent شد و فایل نگه‌داشته‌شده پاک شد
    with final_print._lock:
        items = final_print._load()["items"]
    assert items[0]["status"] == "sent"
    assert not os.path.exists(final_print.held_pdf_path(42, TC))
    callback.answer.assert_awaited()
    callback.message.edit_text.assert_awaited()


async def test_admin_button_is_idempotent(fp_store, monkeypatch):
    """کلیک دوم روی دکمه بعد از ارسال → «قبلاً ارسال شده» و بدون ارسال مجدد."""
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    pdf = fp_store / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    bot = _bot()
    await final_print.hold_for_admin(bot, 42, TC, "لایحه", "علت", "", str(pdf))

    sent = []

    async def fake_send(chat_id, file_path, filename=None, caption=None, reply_markup=None):
        sent.append(chat_id)
        return {"message_id": 1}

    monkeypatch.setattr(final_print, "send_document_direct", fake_send)
    callback = _callback(f"fpsend:42:{TC}")
    await final_print.cb_send_held_final_print(callback, bot)
    await final_print.cb_send_held_final_print(callback, bot)  # کلیک دوم
    assert sent == [42]  # فقط یک‌بار


async def test_admin_button_rejects_non_admin(fp_store):
    """کلیک غیرمدیر روی دکمه → فقط هشدار؛ هیچ فایلی ارسال نمی‌شود."""
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    pdf = fp_store / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    bot = _bot()
    await final_print.hold_for_admin(bot, 42, TC, "لایحه", "علت", "", str(pdf))

    callback = _callback(f"fpsend:42:{TC}", user_id=999)
    await final_print.cb_send_held_final_print(callback, bot)
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert")
    # مورد همچنان held است
    with final_print._lock:
        items = final_print._load()["items"]
    assert items[0]["status"] == "held"


async def test_admin_button_missing_pdf_requeues_for_tomorrow(fp_store):
    """اگر فایل نگه‌داشته‌شده موجود نبود → مورد برای اجرای فردا ساعت ۱۷:۰۰ به صف برمی‌گردد."""
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    pdf = fp_store / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    bot = _bot()
    await final_print.hold_for_admin(bot, 42, TC, "لایحه", "علت", "", str(pdf))
    os.remove(final_print.held_pdf_path(42, TC))

    callback = _callback(f"fpsend:42:{TC}")
    await final_print.cb_send_held_final_print(callback, bot)
    with final_print._lock:
        items = final_print._load()["items"]
    assert items[0]["status"] == "pending"
    callback.answer.assert_awaited()


async def test_hold_for_admin_falls_back_to_report_failure(fp_store, monkeypatch):
    """اگر خودِ نگه‌داشتن PDF ناموفق بود → همان رفتار ناموفق معمول (گزارش مدیر + تلاش فردا)."""
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    monkeypatch.setattr(final_print.shutil, "move", lambda *a, **k: (_ for _ in ()).throw(IOError("disk")))
    reported = []
    async def fake_report(bot, uid, tc, doc, reason):
        reported.append((uid, tc, reason))
    monkeypatch.setattr(final_print, "report_failure", fake_report)
    ok = await final_print.hold_for_admin(_bot(), 42, TC, "لایحه", "علت", "", "/nonexistent.pdf")
    assert ok is False
    assert reported and reported[0][0] == 42


# ══════════════════════════════════════════════════════════════════════
# ۴) پرچم status_gate — فقط اجرای روزانهٔ ۱۷:۰۰، نه چاپ درخواستی کاربر
# ══════════════════════════════════════════════════════════════════════

class _FakeQueue:
    def __init__(self):
        self.items = []

    async def put(self, item):
        self.items.append(item)

    def qsize(self):
        return len(self.items)


async def test_daily_batch_sets_status_gate(fp_store, monkeypatch):
    """تسک‌های اجرای روزانهٔ ۱۷:۰۰ باید پرچم گیت وضعیت را داشته باشند."""
    q = _FakeQueue()
    monkeypatch.setattr(final_print.runtime_state, "job_queue", q)
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    with final_print._lock:
        data = final_print._load()
        data["items"][0]["signed"] = True
        data["items"][0]["signed_date"] = "2020-01-01"
        data["items"][0]["registered_date"] = "2020-01-01"
        final_print._save(data)

    n = await final_print.run_daily_batch(_bot())
    assert n == 1 and len(q.items) == 1
    job = q.items[0]
    assert job["final_print"] is True
    assert job.get("status_gate") is True


async def test_on_demand_print_has_no_status_gate(fp_store, monkeypatch):
    """چاپ درخواستی کاربر (request_print) از گیت وضعیت مستثنی است."""
    q = _FakeQueue()
    monkeypatch.setattr(final_print.runtime_state, "job_queue", q)
    ok = await final_print.request_print(42, TC, "لایحه")
    assert ok is True and len(q.items) == 1
    job = q.items[0]
    assert job["final_print"] is True
    assert "status_gate" not in job


async def test_old_held_items_are_pruned_with_pdf(fp_store, monkeypatch):
    """موارد held قدیمی (بیش از KEEP_HELD_DAYS) با PDFشان پاک می‌شوند."""
    q = _FakeQueue()
    monkeypatch.setattr(final_print.runtime_state, "job_queue", q)
    final_print.record_registration(42, TC, service_type="LAVAYEH")
    final_print.mark_signed(42, TC)
    pdf = fp_store / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    bot = _bot()
    await final_print.hold_for_admin(bot, 42, TC, "لایحه", "علت", "", str(pdf))
    held = final_print.held_pdf_path(42, TC)
    assert os.path.exists(held)

    with final_print._lock:
        data = final_print._load()
        data["items"][0]["held_date"] = "2020-01-01"  # خیلی قدیمی
        final_print._save(data)

    await final_print.run_daily_batch(bot)
    with final_print._lock:
        items = final_print._load()["items"]
    assert items == []
    assert not os.path.exists(held)


# ══════════════════════════════════════════════════════════════════════
# ۵) استخراج واقعی جدول خلاصه از DOM (نمونه‌های فایل پیوست کارفرما)
# ══════════════════════════════════════════════════════════════════════

async def _summary_of(fixture: str):
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    try:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(Path(fixture).resolve().as_uri())
        summary = await scenarios._extract_portal_summary_status(page)
        await browser.close()
        return summary
    finally:
        await p.stop()


_N = final_print._norm_fa  # متن سامانه (ي/ی عربی) در استخراج نرمال می‌شود


async def test_extract_bill_approved_sample():
    """نمونهٔ ۱ پیوست: لایحه با «ارسال شده به: دادگاههاي تجديدنظر استان تهران»."""
    summary = await _summary_of("test_fixtures/fp_bill_sent.html")
    assert summary is not None
    assert summary["last_status"] == _N("ثبت در دفتر انديکارتور شعبه")
    assert summary["sent_to"] == _N("دادگاههاي تجديدنظر استان تهران")
    assert final_print.check_portal_status("لایحه", summary)["approved"] is True


async def test_extract_bill_not_approved_sample():
    """نمونهٔ ۲ پیوست: لایحه «احراز هويت شده» بدون ردیف «ارسال شده به»."""
    summary = await _summary_of("test_fixtures/fp_bill_not_sent.html")
    assert summary is not None
    assert summary["last_status"] == _N("احراز هويت شده")
    assert summary["sent_to"] is None
    v = final_print.check_portal_status("لایحه", summary)
    assert v["approved"] is False


async def test_extract_ezhharnameh_approved_sample():
    """نمونهٔ اظهارنامه: «آخرین وضعیت: ارسال شده به مرجع قضايي» (با «ارسال شده به» خالی)."""
    summary = await _summary_of("test_fixtures/fp_ezhharnameh_sent.html")
    assert summary is not None
    assert summary["last_status"] == _N("ارسال شده به مرجع قضايي")
    assert summary["sent_to"] == ""  # ردیف هست ولی مقدارش خالی است
    assert final_print.check_portal_status("اظهارنامه", summary)["approved"] is True


async def test_extract_dadkhast_approved_sample():
    """نمونهٔ دادخواست بدوی: وضعیت «ارسال شده به مرجع قضايي» → تایید."""
    summary = await _summary_of("test_fixtures/fp_dadkhast_sent.html")
    assert summary is not None
    assert summary["last_status"] == _N("ارسال شده به مرجع قضايي")
    assert summary["sent_to"] == _N("مجتمع دادگاههاي عمومي و انقلاب شهرستان آمل")
    assert final_print.check_portal_status("دادخواست بدوی", summary)["approved"] is True


async def test_extract_returns_none_without_summary():
    """صفحهٔ بدون جدول خلاصه → None → چاپ مثل قبل ارسال می‌شود."""
    html = "<html><body><table><tbody><tr><td>هزینه</td><td>1000</td></tr></tbody></table></body></html>"
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    try:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)
        summary = await scenarios._extract_portal_summary_status(page)
        await browser.close()
        assert summary is None
        assert final_print.check_portal_status("لایحه", summary)["approved"] is True
    finally:
        await p.stop()


# ══════════════════════════════════════════════════════════════════════
# ۶) یکپارچگی سناریو — گیت در مسیر چاپ نهایی
# ══════════════════════════════════════════════════════════════════════

def test_scenarios_applies_gate_before_final_print_send():
    """مسیر چاپ نهایی باید قبل از ارسال به کاربر، گیت وضعیت را بگذراند."""
    import inspect
    src = inspect.getsource(scenarios.process_task)
    # گیت فقط برای چاپ نهاییِ روزانه (status_gate) فعال است
    assert 'is_final_print and data.get("status_gate")' in src
    assert "_fp_check_portal_status" in src
    # عدم تایید → hold برای مدیر و return (قبل از send_document_direct)
    assert '_fp_hold_for_admin(' in src
    assert 'fp_verdict is not None and not fp_verdict.get("approved")' in src


def test_router_registered_in_bot():
    """روتر دکمهٔ مدیر باید در bot.py ثبت شده باشد."""
    src = Path("bot.py").read_text(encoding="utf-8")
    assert "final_print_router" in src
