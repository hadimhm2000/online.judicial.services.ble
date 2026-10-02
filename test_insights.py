"""تست قیف تبدیل، نظرسنجی و گزارش شبانه — اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_insights.py"""
import os
import time

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import bot_settings
import daily_report
import feedback
import funnel


def test_flow_of():
    assert funnel.flow_of("lavayeh_title") == "LAVAYEH"
    assert funnel.flow_of("waiting_for_tn_prepay") == "TAJDID_NAZAR"
    assert funnel.flow_of("waiting_for_tracking_code") == "INQUIRY"
    assert funnel.flow_of("bulk_inquiry_confirm") == "INQUIRY"
    assert funnel.flow_of("bulk_confirm") == "BULK"
    assert funnel.flow_of("waiting_for_flow_type") is None


def test_funnel_dedupes_per_day():
    funnel._buffer.clear()
    funnel._seen.clear()
    funnel._record(5, "LAVAYEH", "lavayeh_title")
    funnel._record(5, "LAVAYEH", "lavayeh_title")
    funnel._record(5, "LAVAYEH", "PAID")
    assert [e["step"] for e in funnel._buffer] == ["lavayeh_title", "PAID"]


def test_feedback_schedule_respects_gap_and_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "STATE_FILE", str(tmp_path / "fb.json"))
    feedback._state = {"pending": {}, "last_asked": {"9": time.time()}}
    feedback.schedule(9, "a.pdf")
    assert "9" not in feedback._state["pending"]          # کمتر از ۲۴ ساعت از سؤال قبلی
    feedback.schedule(10, "b.pdf")
    assert feedback._state["pending"]["10"]["context"] == "b.pdf"
    bot_settings._values["rating.enabled"] = "false"
    try:
        feedback.schedule(11, "c.pdf")
        assert "11" not in feedback._state["pending"]
    finally:
        bot_settings._values.clear()


def test_settings_override_fees():
    import config
    bot_settings._values.update({"fee.inquiry.phone": "70000"})
    try:
        bot_settings._apply_fee_overrides()
        assert config.FEES["شماره تماس"] == 70000
        bot_settings._values.clear()
        bot_settings._apply_fee_overrides()
        assert config.FEES["شماره تماس"] == 65000
    finally:
        bot_settings._values.clear()
        bot_settings._apply_fee_overrides()


def test_prepay_reads_settings():
    import prepay_registration as pr
    bot_settings._values.update({"prepay.other_toman": "5000"})
    try:
        assert pr.get_prepay_amount_toman("check") == 5000
    finally:
        bot_settings._values.clear()


def test_format_report():
    text = daily_report.format_report({
        "date": "2026-10-02", "totalCases": 3, "byService": {"LAVAYEH": 2, "INQUIRY": 1},
        "completed": 2, "failed": 1, "stuck": [], "revenueToman": 150000,
        "feedback": {"count": 2, "average": 4.5, "low": 0},
    })
    assert "لایحه: 2" in text and "150,000" in text and "4.5" in text
