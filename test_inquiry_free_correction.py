"""تست فرصت اصلاح رایگان استعلام کدرهگیری و جدول تصمیم مرکزی خطا —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_inquiry_free_correction.py"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import error_catalog
import runtime_state

WRONG_FORM_POPUP = "این کد رهگیری مربوط به  «تجديدنظرخواهي» می باشد و قابل بازیابی در این فرم نیست ."


def run(coro):
    return asyncio.run(coro)


# ── error_catalog ──────────────────────────────────────────────────────

def test_popups_classified_and_decided():
    assert error_catalog.decide("کد رهگیری نامعتبر است")["action"] == error_catalog.ACTION_FREE_CORRECTION
    d = error_catalog.decide(WRONG_FORM_POPUP)
    assert d["category"] == error_catalog.WRONG_FORM_TRACKING_CODE
    assert d["action"] == error_catalog.ACTION_SWITCH_CATEGORY
    assert error_catalog.decide("متن کاملاً ناشناخته")["action"] == error_catalog.ACTION_STOP_NOTIFY_ADMIN


def test_every_category_has_policy():
    cats = {c for c, _ in error_catalog.CATALOG} | {error_catalog.UNKNOWN}
    assert cats <= set(error_catalog.ERROR_POLICY)


@pytest.mark.parametrize("name,expected", [
    ("تجديدنظرخواهي", ("دعاوی اعتراضی", "تجدیدنظرخواهی")),
    ("دادخواست بدوي", ("دادخواست بدوی", None)),
    ("اظهارنامه", ("اظهارنامه", None)),
    ("لايحه", ("لایحه", None)),
    ("شکوائيه", ("شکواییه", None)),
    ("واخواهي", ("دعاوی اعتراضی", "واخواهی")),
    ("فرجام خواهي", ("دعاوی اعتراضی", "فرجام خواهی")),
    ("اعاده دادرسي كيفري", ("دعاوی اعتراضی", "اعاده دادرسی کیفری")),
    ("تجديدنظرخواهي شوراي حل اختلاف", ("شورای حل اختلاف", "تجدیدنظرخواهی شورا")),
    ("تجدیدنظرخواهی دیوان عدالت اداری", ("دیوان عدالت اداری", "تجدیدنظرخواهی دیوان عدالت اداری")),
    ("دعوای جلب ثالث", ("دعاوی طاری", "دعوای جلب ثالث")),
    ("چیز ناشناخته", None),
])
def test_resolve_wrong_form_target(name, expected):
    assert error_catalog.resolve_wrong_form_target(f"این کد رهگیری مربوط به «{name}» می باشد") == expected


def test_resolved_subcategories_exist_in_menu():
    from keyboards import SUB_MENUS, doc_category_kb
    cats = {b.text for row in doc_category_kb.keyboard for b in row}
    for _, cat, sub in error_catalog.WRONG_FORM_TARGETS:
        assert cat in cats
        if sub is not None:
            assert sub in SUB_MENUS[cat]


def test_generic_words_do_not_resolve():
    assert error_catalog.resolve_wrong_form_target("کد رهگیری نامعتبر است") is None


# ── scenarios: فرصت رایگان فقط یک‌بار ─────────────────────────────────

def _fake_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def test_second_failure_after_free_retry_ends_with_nothing_found(monkeypatch):
    import scenarios
    monkeypatch.setattr(scenarios, "register_failed_inquiry_to_panel", AsyncMock())
    runtime_state.invalid_tracking_retry.clear()
    bot = _fake_bot()
    data = {"user_id": 5, "query_type": "کد رهگیری", "doc_category": "لایحه", "free_retry_used": True}
    run(scenarios._handle_invalid_tracking_code(bot, 5, data, "1404000000000001", "لایحه"))
    user_msgs = [c.args[1] for c in bot.send_message.call_args_list if c.args[0] == 5]
    assert any("موردی استعلام نشد" in m for m in user_msgs)
    assert 5 not in runtime_state.invalid_tracking_retry


def test_first_failure_opens_one_free_correction(monkeypatch):
    import scenarios
    runtime_state.invalid_tracking_retry.clear()
    runtime_state.bulk_inquiry_progress.clear()
    fsm_ctx = MagicMock()
    fsm_ctx.set_state = AsyncMock()
    dp = MagicMock()
    dp.fsm.resolve_context.return_value = fsm_ctx
    monkeypatch.setattr(runtime_state, "dp", dp, raising=False)
    bot = _fake_bot()
    data = {"user_id": 6, "query_type": "کد رهگیری", "doc_category": "لایحه"}
    run(scenarios._handle_invalid_tracking_code(bot, 6, data, "1404000000000001", "لایحه"))
    assert 6 in runtime_state.invalid_tracking_retry
    assert "یک‌بار دیگر" in bot.send_message.call_args_list[0].args[1]


# ── handlers: اصلاح کد + دسته ───────────────────────────────────────

class _State:
    def __init__(self):
        self.state = None
        self.set_state = AsyncMock(side_effect=self._set)
        self.clear = AsyncMock()

    async def _set(self, s):
        self.state = s


def _msg(text, uid=7):
    m = MagicMock()
    m.text = text
    m.from_user.id = uid
    m.answer = AsyncMock()
    return m


def test_correction_lets_user_change_category_and_marks_used():
    import handlers
    from states import Form
    while not runtime_state.job_queue.empty():
        runtime_state.job_queue.get_nowait()
    runtime_state.invalid_tracking_retry[7] = {
        "expires_at": datetime.datetime.now() + datetime.timedelta(minutes=10),
        "remaining": 1,
        "template_job": {"user_id": 7, "query_type": "کد رهگیری", "doc_category": "لایحه",
                         "doc_subcategory": None, "tracking_code": "1404000000000001"},
    }
    st = _State()
    run(handlers.process_corrected_tracking_code(_msg("1404220000000002"), st))
    assert st.state == Form.waiting_for_corrected_doc_category
    run(handlers.process_corrected_doc_category(_msg("دعاوی اعتراضی"), st))
    assert st.state == Form.waiting_for_corrected_doc_subcategory
    run(handlers.process_corrected_doc_subcategory(_msg("تجدیدنظرخواهی"), st))
    job = runtime_state.job_queue.get_nowait()
    assert job["tracking_code"] == "1404220000000002"
    assert (job["doc_category"], job["doc_subcategory"]) == ("دعاوی اعتراضی", "تجدیدنظرخواهی")
    assert job["free_retry_used"] is True
    assert 7 not in runtime_state.invalid_tracking_retry


def test_correction_same_category():
    import handlers
    while not runtime_state.job_queue.empty():
        runtime_state.job_queue.get_nowait()
    runtime_state.invalid_tracking_retry[8] = {
        "expires_at": datetime.datetime.now() + datetime.timedelta(minutes=10),
        "remaining": 1,
        "template_job": {"user_id": 8, "query_type": "کد رهگیری", "doc_category": "اظهارنامه"},
    }
    st = _State()
    run(handlers.process_corrected_tracking_code(_msg("1404220000000003", uid=8), st))
    from keyboards import CORRECTED_SAME_CATEGORY_TEXT
    run(handlers.process_corrected_doc_category(_msg(CORRECTED_SAME_CATEGORY_TEXT, uid=8), st))
    job = runtime_state.job_queue.get_nowait()
    assert job["doc_category"] == "اظهارنامه" and job["free_retry_used"] is True


# ── اطلاع خطاهای منضمات/آماده‌سازی به مدیر ─────────────────────────

def test_step_error_notifies_admin_with_context_and_dedupe(monkeypatch):
    import bug_reporter
    sent = []

    async def fake_send(bot, text):
        sent.append(text)

    monkeypatch.setattr(bug_reporter, "_send_admin_text", fake_send)
    monkeypatch.setattr(bug_reporter, "ADMIN_ID", 1)
    bug_reporter._last_step_alert_at.clear()

    async def scenario():
        bug_reporter.set_job_context(MagicMock(), {"user_id": 42, "task_type": "LAVAYEH_SUBMIT", "tracking_code": "123"})
        await bug_reporter.notify_admin_step_error("منضمات", "حجم فایل بیش از حد مجاز است")
        await bug_reporter.notify_admin_step_error("منضمات", "حجم فایل بیش از حد مجاز است")  # تکراری
        await bug_reporter.notify_admin_step_error("آماده‌سازی", "متن کاملاً ناشناخته")

    run(scenario())
    assert len(sent) == 2
    assert "شناخته‌شده" in sent[0] and "/send 42" in sent[0] and "LAVAYEH_SUBMIT" in sent[0]
    assert "ناشناخته" in sent[1]


def test_upload_error_popup_reader_notifies_admin(monkeypatch):
    import bug_reporter
    import upload_helpers
    calls = []

    async def fake_notify(step, text, **kw):
        calls.append((step, text))

    monkeypatch.setattr(bug_reporter, "notify_admin_step_error", fake_notify)
    monkeypatch.setattr(upload_helpers.asyncio, "sleep", AsyncMock())
    page = MagicMock()
    page.evaluate = AsyncMock(return_value="نوع فایل مجاز نیست")
    assert run(upload_helpers.get_and_close_error_popup_text(page)) == "نوع فایل مجاز نیست"
    assert calls == [("منضمات", "نوع فایل مجاز نیست")]
