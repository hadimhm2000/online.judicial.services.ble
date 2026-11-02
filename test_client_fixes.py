"""تست سه اصلاحیهٔ کارفرما (۱۴۰۵):
  ۱. لایحه: خطای «در ذخیره سازی لایحه اشکالی بوجود آمد» → کلیک مجدد «ثبت موقت» (تا ۳ بار)
  ۲. دعاوی اعتراضی: ثبت سند «تصوير الكترونيك دادنامه» + شماره پرونده در منضمات
     (کلیهٔ عناوین) + پیام تایید الزامی + خطای ورود همزمان → اطلاع مدیر + کلیک مجدد
  ۳. اعسار از هزینه دادرسی: شماره پروندهٔ ۱۶/۱۸ رقمی + شماره ابلاغیه + تصویر ابلاغیه
     (۱ تا ۲ عکس) — الزامی و از کاربر دریافت شود

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 python -m pytest test_client_fixes.py -q
"""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "123456")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import runtime_state
from states import Form

UID = 4242
ADMIN_ID_NUM = int(os.environ["ADMIN_ID"])
SAVE_ERR = "در ذخیره سازی لایحه اشکالی بوجود آمد."
FILE_NO_18 = "140513920000628315"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """سریع‌کردن تست‌ها: asyncio.sleep فوری برگردد."""
    async def _instant(_t=0):
        return None
    monkeypatch.setattr(asyncio, "sleep", _instant)
    yield


@pytest.fixture(autouse=True)
def _isolate():
    runtime_state.incomplete_tasks.clear()
    yield
    runtime_state.incomplete_tasks.clear()


# ══════════════════════════════════════════════════════════════════════════════
# ابزارهای مشترک
# ══════════════════════════════════════════════════════════════════════════════

class FakeState:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kw):
        self.data.update(kw)

    async def set_state(self, s):
        self.state = s

    async def clear(self):
        self.data, self.state = {}, None


def _msg(text):
    return SimpleNamespace(text=text, photo=None, document=None,
                           from_user=SimpleNamespace(id=UID),
                           answer=AsyncMock())


def _photo_msg(file_id):
    return SimpleNamespace(text=None, photo=[SimpleNamespace(file_id=file_id)],
                           document=None, from_user=SimpleNamespace(id=UID),
                           answer=AsyncMock())


def _bot():
    return SimpleNamespace(send_message=AsyncMock())


# ══════════════════════════════════════════════════════════════════════════════
# اصلاح ۱ — لایحه: تلاش مجدد «ثبت موقت» روی خطای ذخیره‌سازی لایحه
# ══════════════════════════════════════════════════════════════════════════════

class FakeLavayehPage:
    """صفحهٔ ساختگی: شمارش کلیک #btnSave + پاسخ موفقیت قابل برنامه‌ریزی."""

    def __init__(self, success_after_clicks=99):
        self.clicks = 0
        self.success_after_clicks = success_after_clicks

    async def evaluate(self, script, *args):
        if "#btnSave" in script and "btn.disabled" in script:
            self.clicks += 1
            return True
        if "sa-icon.sa-success" in script and "h2.innerText" in script:
            return self.clicks >= self.success_after_clicks
        if "button.confirm" in script:
            return True
        return None


def _patch_lavayeh_helpers(monkeypatch, loading_results, error_texts=None):
    """پچ توابع کمکی لایحه؛ loading_results/error_texts اسکریپت نتایج هستند."""
    import lavayeh_scenario as lv

    loading_iter = iter(loading_results)

    async def _fake_loading(page, bot, user_id, timeout=60):
        return next(loading_iter, False)

    async def _no_expiry(page, bot, user_id):
        return False

    error_iter = iter(error_texts or [])

    async def _fake_error_popup(page):
        try:
            return next(error_iter)
        except StopIteration:
            return None

    monkeypatch.setattr(lv, "wait_for_horizontal_loading_bar", _fake_loading)
    monkeypatch.setattr(lv, "check_and_handle_expiry", _no_expiry)
    monkeypatch.setattr(lv, "_get_and_close_error_popup_text", _fake_error_popup)
    monkeypatch.setattr(lv, "safe_click_by_text", AsyncMock())
    return lv


def test_save_storage_error_matcher_variants():
    import lavayeh_scenario as lv
    # متن اصلی سامانه + گونه‌های نویسه‌ای عربی/فارسی
    assert lv._is_lavayeh_save_storage_error(
        "در ذخیره سازی لایحه اشکالی بوجود آمد.") is True
    assert lv._is_lavayeh_save_storage_error(
        "در ذخیره سازي لایحه اشكالي بوجود آمد") is True          # ي/ك عربی
    assert lv._is_lavayeh_save_storage_error(
        "در ذخیره‌سازی لایحه اشکالی بوجود آمد") is True           # نیم‌فاصله
    # خطاهای دیگر نباید_match شوند
    assert lv._is_lavayeh_save_storage_error("شخص ... در فهرست اشخاص پرونده نیست") is False
    assert lv._is_lavayeh_save_storage_error("تاخیر در اجرای سرویس") is False
    assert lv._is_lavayeh_save_storage_error("در تخصیص کد رهگیری اشکالی بوجود آمد") is False
    assert lv._is_lavayeh_save_storage_error("") is False
    assert lv._is_lavayeh_save_storage_error(None) is False
    assert lv.LAVAYEH_SAVE_STORAGE_ERROR_MAX_RETRIES == 3


def test_temp_save_reclicks_once_after_storage_error(monkeypatch):
    """خطای ذخیره‌سازی یک‌بار → دکمه دوباره زده می‌شود → موفقیت."""
    lv = _patch_lavayeh_helpers(
        monkeypatch,
        loading_results=[SAVE_ERR, False],          # تلاش ۱: خطا | تلاش ۲: بدون خطا
        error_texts=[],
    )
    page = FakeLavayehPage(success_after_clicks=2)   # موفقیت از کلیک دوم
    bot = _bot()

    run(lv._click_save_temp_with_retry(page, bot, UID))

    assert page.clicks == 2, "دکمهٔ «ثبت موقت» باید دقیقاً یک بار دیگر زده شود"
    # پیام قطعی به کاربر نباید ارسال شده باشد
    bot.send_message.assert_not_called()


def test_temp_save_storage_error_popup_path_also_retries(monkeypatch):
    """همان خطا از مسیر پاپ‌آپ (نه لودینگ) → باز هم کلیک مجدد."""
    lv = _patch_lavayeh_helpers(
        monkeypatch,
        loading_results=[False, False],
        error_texts=[SAVE_ERR, None],               # تلاش ۱: پاپ‌آپ خطا | تلاش ۲: هیچ
    )
    page = FakeLavayehPage(success_after_clicks=2)
    bot = _bot()

    run(lv._click_save_temp_with_retry(page, bot, UID))

    assert page.clicks == 2
    bot.send_message.assert_not_called()


def test_temp_save_fatal_after_three_reclicks(monkeypatch):
    """پیشوند خطا بیش از ۳ بار → خطای قطعی (LavayehFatalError) پرتاب می‌شود."""
    lv = _patch_lavayeh_helpers(
        monkeypatch,
        loading_results=[SAVE_ERR] * 10,
        error_texts=[],
    )
    page = FakeLavayehPage(success_after_clicks=99)  # هرگز موفق نمی‌شود
    bot = _bot()

    with pytest.raises(lv.LavayehFatalError):
        run(lv._click_save_temp_with_retry(page, bot, UID))

    # ۱ کلیک اولیه + ۳ کلیک مجدد = ۴
    assert page.clicks == 4
    # پیام خطا برای کاربر ارسال شده باشد
    assert bot.send_message.await_count >= 1


def test_temp_save_other_error_is_still_fatal(monkeypatch):
    """خطای غیر از ذخیره‌سازی لایحه → همان رفتار قطعی قبلی."""
    lv = _patch_lavayeh_helpers(
        monkeypatch,
        loading_results=["شخص ارائه‌کننده لایحه در فهرست اشخاص پرونده نیست"],
        error_texts=[],
    )
    page = FakeLavayehPage()
    bot = _bot()

    with pytest.raises(lv.LavayehFatalError):
        run(lv._click_save_temp_with_retry(page, bot, UID))
    assert page.clicks == 1


# ══════════════════════════════════════════════════════════════════════════════
# اصلاح ۲ — دعاوی اعتراضی: سند «تصوير الكترونيك دادنامه» در منضمات
# ══════════════════════════════════════════════════════════════════════════════

class FakeTnPage:
    """صفحهٔ ساختگی منضمات: انتخاب نوع پیوست، #txtCaseNo، #btnSaveDoc و پاپ‌آپ."""

    def __init__(self, popup_script):
        self.popup_iter = iter(popup_script)
        self.save_clicks = 0
        self.case_no_value = ""
        self.selected_option = ""

    async def evaluate(self, script, *args):
        # فرم dirty-check (شامل val('#txtNo'))
        if "val('#txtNo')" in script:
            return False
        # انتخاب نوع پیوست از #attachmentType (scope_direct)
        if "theJSSPetitionAttachment" in script:
            return {"found": True, "method": "scope_direct", "stuck": True}
        # fill_input_angular — درج مقدار
        if "$setViewValue" in script and isinstance(args, tuple) and args and isinstance(args[0], dict):
            self.case_no_value = str(args[0].get("value", ""))
            return {"found": True, "value": self.case_no_value}
        # fill_input_angular — کنترل ماندگاری (آرگومان رشتهٔ selector)
        if args and isinstance(args[0], str) and args[0].startswith("#txtCaseNo"):
            return self.case_no_value
        # click_save_doc_once — وضعیت دکمه
        if "visible.disabled ? 'disabled' : 'ready'" in script:
            return "ready"
        # click_save_doc_once — کلیک
        if "insertEditDocument" in script:
            self.save_clicks += 1
            return True
        # read_save_doc_popup — خواندن پاپ‌آپ نتیجه
        if "sa-icon.sa-error" in script and "isSuccess" in script:
            popup = next(self.popup_iter, None)
            if popup is None:
                return None
            return popup
        # بستن پاپ‌آپ‌ها
        if "button.confirm" in script:
            return True
        return None


def _popup_success():
    return {"text": "پیوست « تصوير الكترونيك دادنامه » با موفقیت ثبت گردید .",
            "isSuccess": True, "isError": False}


def _popup_session():
    return {"text": "ورود به سامانه در صفحه یا رایانه ای دیگر انجام شده و اعتبار ورود قبلی منقضی شده است",
            "isSuccess": False, "isError": True}


def _popup_error():
    return {"text": "خطای نامشخص در سامانه", "isSuccess": False, "isError": True}


def _patch_tn_helpers(monkeypatch, handle_session_calls=None):
    import tajdid_nazar_scenario as tn

    async def _no_expiry(page, bot, user_id):
        return False

    async def _no_angular_wait(page):
        return None

    async def _fake_handle_session(bot, user_id, page=None, timeout_seconds=None):
        if handle_session_calls is not None:
            handle_session_calls.append(user_id)

    monkeypatch.setattr(tn, "check_and_handle_expiry", _no_expiry)
    monkeypatch.setattr(tn, "wait_for_angular_idle", _no_angular_wait)
    monkeypatch.setattr(tn, "handle_session_expired", _fake_handle_session)
    return tn


def test_dadnameh_document_success_path(monkeypatch):
    tn = _patch_tn_helpers(monkeypatch)
    page = FakeTnPage(popup_script=[_popup_success()])
    bot = _bot()

    ok = run(tn._register_dadnameh_electronic_document(
        page, FILE_NO_18, bot, UID, "B100"))

    assert ok is True
    assert page.save_clicks == 1
    assert page.case_no_value == FILE_NO_18


def test_dadnameh_document_empty_file_no_fails(monkeypatch):
    tn = _patch_tn_helpers(monkeypatch)
    page = FakeTnPage(popup_script=[])
    bot = _bot()

    ok = run(tn._register_dadnameh_electronic_document(page, "", bot, UID, "B100"))

    assert ok is False
    # مدیر مطلع شده باشد
    assert bot.send_message.await_count == 1
    sent_args = bot.send_message.await_args.args
    assert sent_args[0] == ADMIN_ID_NUM
    assert "شماره پرونده" in sent_args[1]


def test_dadnameh_document_concurrent_login_notifies_admin_and_retries(monkeypatch):
    """خطای ورود همزمان → پیام «لاگین کنید» به مدیر + کلیک مجدد #btnSaveDoc."""
    session_calls = []
    tn = _patch_tn_helpers(monkeypatch, handle_session_calls=session_calls)
    page = FakeTnPage(popup_script=[_popup_session(), _popup_success()])
    bot = _bot()

    ok = run(tn._register_dadnameh_electronic_document(
        page, FILE_NO_18, bot, UID, "B100"))

    assert ok is True
    assert page.save_clicks == 2, "پس از لاگین مدیر، #btnSaveDoc مجدداً زده شود"
    assert session_calls == [UID], "فرآیند انتظار برای لاگین مدیر اجرا شود"

    admin_msgs = [c.args for c in bot.send_message.await_args_list
                  if c.args and c.args[0] == ADMIN_ID_NUM]
    assert len(admin_msgs) == 1
    assert "ورود همزمان" in admin_msgs[0][1]
    assert "لاگین" in admin_msgs[0][1]
    assert str(UID) in admin_msgs[0][1]


def test_dadnameh_document_fails_after_three_attempts(monkeypatch):
    tn = _patch_tn_helpers(monkeypatch)
    page = FakeTnPage(popup_script=[_popup_error()] * 5)
    bot = _bot()

    ok = run(tn._register_dadnameh_electronic_document(
        page, FILE_NO_18, bot, UID, "B100", max_attempts=3))

    assert ok is False
    assert page.save_clicks == 3


def test_upload_tn_attachments_stops_when_dadnameh_fails(monkeypatch):
    """شکست سند دادنامه → کل ثبت متوقف: (False, {}) + تسک ناقص + پیام مدیر."""
    tn = _patch_tn_helpers(monkeypatch)

    async def _fail_dadnameh(page, file_no, bot, user_id, bill_no, max_attempts=3):
        return False

    monkeypatch.setattr(tn, "_register_dadnameh_electronic_document", _fail_dadnameh)

    import ezhharnameh_scenario as ez
    monkeypatch.setattr(ez, "_upload_proxy_document", AsyncMock())
    monkeypatch.setattr(ez, "_upload_electronic_vakalaht", AsyncMock(return_value="success"))
    monkeypatch.setattr(ez, "_upload_attachment_with_retry", AsyncMock(
        return_value={"success": True}))

    page = FakeTnPage(popup_script=[])
    bot = _bot()
    data = {"tn_file_no": FILE_NO_18, "tn_appellants": []}

    status, extra = run(tn._upload_tn_attachments(
        page, data, [], has_legal=False, has_lawyer=False, bot=bot,
        user_id=UID, bill_no="B200"))

    assert status is False
    assert extra == {}
    # تسک ناقص ذخیره شده باشد
    assert "tn:B200" in runtime_state.incomplete_tasks
    task = runtime_state.incomplete_tasks["tn:B200"]
    assert task["next_step"] == "منضمات"
    assert task.get("dadnameh_doc_pending") is True
    # مدیر و کاربر مطلع شده باشند
    targets = [c.args[0] for c in bot.send_message.await_args_list if c.args]
    assert ADMIN_ID_NUM in targets and UID in targets


def test_upload_tn_attachments_dadnameh_registered_last(monkeypatch):
    """ترتیب: ابتدا پیوست‌های دیگر، سپس سند دادنامه (آخر منضمات)."""
    tn = _patch_tn_helpers(monkeypatch)
    calls = []

    async def _ok_dadnameh(page, file_no, bot, user_id, bill_no, max_attempts=3):
        calls.append("dadnameh")
        return True

    monkeypatch.setattr(tn, "_register_dadnameh_electronic_document", _ok_dadnameh)

    import ezhharnameh_scenario as ez

    async def _fake_other(page, title, paths, bot, user_id, **kw):
        calls.append(f"other:{title}")
        return {"success": True}

    monkeypatch.setattr(ez, "_upload_proxy_document", AsyncMock())
    monkeypatch.setattr(ez, "_upload_attachment_with_retry", _fake_other)
    monkeypatch.setattr(ez, "_upload_electronic_vakalaht", AsyncMock(return_value="success"))

    page = FakeTnPage(popup_script=[])
    bot = _bot()
    data = {"tn_file_no": FILE_NO_18, "tn_appellants": []}
    groups = [{"title": "سایر مدارک", "paths": ["/tmp/x.jpg"]}]

    status, _ = run(tn._upload_tn_attachments(
        page, data, groups, has_legal=False, has_lawyer=False, bot=bot,
        user_id=UID, bill_no="B300"))

    assert status is True
    assert calls == ["other:سایر مدارک", "dadnameh"], "سند دادنامه باید آخر ثبت شود"


# ══════════════════════════════════════════════════════════════════════════════
# اصلاح ۳ — اعسار از هزینه دادرسی: فیلدهای الزامی
# ══════════════════════════════════════════════════════════════════════════════

import check_handlers as ch


def test_aasar_case_no_requires_16_or_18_digits():
    state = FakeState({"check_request_title": "اعسار از پرداخت هزینه دادرسی"})

    # ۱۵ رقم → رد
    run(ch.check_aasar_case_no_handler(_msg("123456789012345"), state))
    assert state.state is None            # state تغییر نکرده (دوباره پرسیده می‌شود)
    assert "check_aasar_case_no" not in state.data

    # ۱۷ رقم → رد
    run(ch.check_aasar_case_no_handler(_msg("12345678901234567"), state))
    assert "check_aasar_case_no" not in state.data

    # متن غیر عددی → رد
    run(ch.check_aasar_case_no_handler(_msg("abc"), state))
    assert "check_aasar_case_no" not in state.data

    # ۱۶ رقم → پذیرش و رفتن به شماره ابلاغیه
    run(ch.check_aasar_case_no_handler(_msg("1234567890123456"), state))
    assert state.data["check_aasar_case_no"] == "1234567890123456"
    assert state.state == Form.check_aasar_notice_no

    # ۱۸ رقم → پذیرش
    state2 = FakeState({"check_request_title": "اعسار از پرداخت هزینه دادرسی"})
    run(ch.check_aasar_case_no_handler(_msg("۱۴۰۵۱۳۹۲۰۰۰۰۶۲۸۳۱۵"), state2))
    assert state2.data["check_aasar_case_no"] == FILE_NO_18   # اعداد فارسی نرمال شوند


def test_aasar_notice_no_validation():
    state = FakeState({"check_request_title": "اعسار از پرداخت هزینه دادرسی",
                       "check_aasar_case_no": FILE_NO_18})

    # ۱۹ رقم → رد
    run(ch.check_aasar_notice_no_handler(_msg("1234567890123456789"), state))
    assert "check_aasar_notice_no" not in state.data

    # غیر عددی → رد
    run(ch.check_aasar_notice_no_handler(_msg("ابلاغ ۱۲"), state))
    assert "check_aasar_notice_no" not in state.data

    # ۱۸ رقم → پذیرش و رفتن به تصویر ابلاغیه
    run(ch.check_aasar_notice_no_handler(_msg("123456789012345678"), state))
    assert state.data["check_aasar_notice_no"] == "123456789012345678"
    assert state.state == Form.check_aasar_notice_image


def test_aasar_notice_images_between_one_and_two():
    state = FakeState({"check_request_title": "اعسار از پرداخت هزینه دادرسی",
                       "check_aasar_case_no": FILE_NO_18,
                       "check_aasar_notice_no": "12345"})

    # تصویر اول
    msg1 = _photo_msg("f1")
    run(ch.check_aasar_notice_image_handler(msg1, state))
    assert state.data["check_aasar_notice_images"] == ["f1"]
    assert state.state == Form.check_aasar_notice_more

    # تصویر دوم (از state «بیشتر» — همان منطق تصویر اجرا می‌شود)
    msg2 = _photo_msg("f2")
    run(ch.check_aasar_notice_more_handler(msg2, state))
    assert state.data["check_aasar_notice_images"] == ["f1", "f2"]

    # تصویر سوم → رد (حداکثر ۲ تصویر)
    msg3 = _photo_msg("f3")
    run(ch.check_aasar_notice_more_handler(msg3, state))
    assert state.data["check_aasar_notice_images"] == ["f1", "f2"]
    # پیام «حداکثر ۲ تصویر» برای کاربر ارسال شده باشد
    answered = [c.args[0] for c in msg3.answer.await_args_list if c.args]
    assert any("حداکثر" in t and "۲ تصویر" in t for t in answered), \
        "پیام سقف ۲ تصویر باید ارسال شود"


def test_aasar_notice_more_requires_min_one_image():
    state = FakeState({"check_request_title": "اعسار از پرداخت هزینه دادرسی",
                       "check_aasar_case_no": FILE_NO_18,
                       "check_aasar_notice_no": "12345",
                       "check_aasar_notice_images": []})

    # «ادامه» بدون هیچ تصویری → مجدداً درخواست تصویر
    run(ch.check_aasar_notice_more_handler(_msg("✅ ادامه"), state))
    assert state.state == Form.check_aasar_notice_image
    assert "check_aasar_notice_images" not in state.data or \
        not state.data["check_aasar_notice_images"]


def test_aasar_flow_asks_new_fields_before_esteshahadieh():
    """روتر: برای «اعسار از پرداخت هزینه دادرسی» ابتدا ۳ فیلد جدید پرسیده شود."""
    state = FakeState({"check_request_title": "اعسار از پرداخت هزینه دادرسی"})

    run(ch._ask_check_next_after_images(_msg("ادامه"), state))
    assert state.state == Form.check_aasar_case_no

    # پس از شماره پرونده → شماره ابلاغیه
    state.data["check_aasar_case_no"] = FILE_NO_18
    run(ch._ask_check_next_after_images(_msg("ادامه"), state))
    assert state.state == Form.check_aasar_notice_no

    # پس از شماره ابلاغیه → تصویر ابلاغیه
    state.data["check_aasar_notice_no"] = "12345"
    run(ch._ask_check_next_after_images(_msg("ادامه"), state))
    assert state.state == Form.check_aasar_notice_image

    # پس از تصویر ابلاغیه → استشهادیه (ادامهٔ زنجیرهٔ قبلی)
    state.data["check_aasar_notice_images"] = ["f1"]
    run(ch._ask_check_next_after_images(_msg("ادامه"), state))
    assert state.state == Form.check_esteshahadieh_image


def test_other_aasar_titles_do_not_ask_new_fields():
    """عناوین اعسارِ دیگر → مستقیم استشهادیه (فقط «هزینه دادرسی» فیلدهای جدید دارد)."""
    state = FakeState({"check_request_title": "اعسار از پرداخت محکوم به"})
    run(ch._ask_check_next_after_images(_msg("ادامه"), state))
    assert state.state == Form.check_esteshahadieh_image

    state2 = FakeState({"check_request_title": "اعسار از پرداخت مهریه"})
    run(ch._ask_check_next_after_images(_msg("ادامه"), state2))
    assert state2.state == Form.check_esteshahadieh_image
