"""تست محاسبه تمبر بر اساس حق‌الوکاله، جابه‌جایی منو و تشخیص پاپ‌آپ ورود همزمان —
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_lawyer_fee_stamp.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import runtime_state
import stamp_duty as sd
from states import Form


@pytest.fixture(autouse=True)
def _clean():
    runtime_state.user_free_usage.clear()
    runtime_state.user_subscriptions.clear()


# ── فرمول (مطابق نمونهٔ کارفرما: حق‌الوکاله ۱ میلیارد ریال، حقوقی) ─────────

def test_lawyer_fee_sample():
    r = sd.calculate_stamp_from_lawyer_fee(1_000_000_000)
    assert r["total"] == {"fee": 1_000_000_000, "stamp": 50_000_000,
                          "share": 37_500_000, "total": 87_500_000}
    assert r["first"] == {"fee": 600_000_000, "stamp": 30_000_000,
                          "share": 22_500_000, "total": 52_500_000}
    assert r["appeal"] == {"fee": 400_000_000, "stamp": 20_000_000,
                           "share": 15_000_000, "total": 35_000_000}
    assert (r["tamber_kolli"], r["tamber_bedvi"], r["tamber_tajdidnazar"]) == (
        50_000_000, 30_000_000, 20_000_000)


def test_lawyer_fee_format_and_invalid():
    r = sd.calculate_stamp_from_lawyer_fee(1_000_000_000)
    text = sd.format_lawyer_fee_result_fa(1_000_000_000, r)
    for part in ("۸۷٬۵۰۰٬۰۰۰ ریال", "۵۲٬۵۰۰٬۰۰۰ ریال", "۳۵٬۰۰۰٬۰۰۰ ریال",
                 "ماده ۲۱", "ماده ۲۹", "نوع پرونده : حقوقی",
                 "مبلغ حق الوکاله : ۱٬۰۰۰٬۰۰۰٬۰۰۰ ریال"):
        assert part in text, part
    assert "_" not in text  # Markdown سالم
    with pytest.raises(ValueError):
        sd.calculate_stamp_from_lawyer_fee(0)
    assert sd.calculate_stamp_from_lawyer_fee(10)["total"]["stamp"] == 1  # 0.5 → 1


# ── منو ─────────────────────────────────────────────────────────────────

def test_main_menu_swap():
    import keyboards as kb
    rows = [[b.text for b in r] for r in kb.get_flow_type_kb(99).keyboard]
    assert [kb.COURT_FEE_MENU_TEXT, kb.DAMAGES_MENU_TEXT] in rows
    assert ["🔧 ابزار فایل"] in rows
    assert rows.index([kb.COURT_FEE_MENU_TEXT, kb.DAMAGES_MENU_TEXT]) < rows.index(["🔧 ابزار فایل"])
    assert kb.STAMP_BY_LAWYER_FEE_TEXT in [b.text for r in kb.stamp_calc_claim_type_kb.keyboard for b in r]
    assert kb.STAMP_BY_LAWYER_FEE_EALAM_TEXT in [b.text for r in kb.ealam_claim_type_kb.keyboard for b in r]


# ── هندلرها ─────────────────────────────────────────────────────────────

def _msg(text, uid=777):
    m = MagicMock()
    m.text = text
    m.from_user.id = uid
    m.answer = AsyncMock()
    return m


def _state(data=None):
    st = MagicMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    st.update_data = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {})
    return st


def test_stamp_calc_lawyer_fee_flow_counts_usage():
    import keyboards as kb
    import stamp_calc_handlers as h

    async def scenario():
        st = _state()
        await h.stamp_calc_claim_type_handler(_msg(kb.STAMP_BY_LAWYER_FEE_TEXT), st)
        st.set_state.assert_awaited_with(Form.stamp_calc_lawyer_fee_amount)

        st = _state()
        m = _msg("۱٬۰۰۰٬۰۰۰٬۰۰۰")
        await h.stamp_calc_lawyer_fee_handler(m, st)
        assert "۸۷٬۵۰۰٬۰۰۰" in m.answer.await_args.args[0]
        st.clear.assert_awaited()
        assert runtime_state.get_user_usage(777)["stamp"] == 1

        m = _msg("abc")
        await h.stamp_calc_lawyer_fee_handler(m, _state())
        assert "فقط عدد" in m.answer.await_args.args[0]

    asyncio.run(scenario())


def test_stamp_calc_existing_options_unchanged():
    import stamp_calc_handlers as h

    async def scenario():
        st = _state()
        await h.stamp_calc_claim_type_handler(_msg("1️⃣ دعوی مالی است و مبلغ خواسته را می‌دانم"), st)
        st.set_state.assert_awaited_with(Form.stamp_calc_claim_amount)

    asyncio.run(scenario())


def test_ealam_lawyer_fee_flow(monkeypatch):
    import keyboards as kb
    import lavayeh_handlers as lh
    monkeypatch.setattr(lh, "_ask_lavayeh_text_ealam", AsyncMock())

    async def scenario():
        st = _state()
        await lh.ealam_in_lavayeh_claim_type(_msg(kb.STAMP_BY_LAWYER_FEE_EALAM_TEXT), st)
        st.set_state.assert_awaited_with(Form.ealam_vakalaht_lawyer_fee_amount)

        st = _state()
        await lh.ealam_in_lavayeh_lawyer_fee_amount(_msg("1000000000"), st)
        st.set_state.assert_awaited_with(Form.ealam_vakalaht_stamp_type)
        kwargs = st.update_data.await_args.kwargs
        assert kwargs["ealam_stamp_calc_mode"] == "lawyer_fee"
        result = kwargs["ealam_stamp_result"]

        # انتخاب تمبر بدوی (نخستین) → ۳۰ میلیون ریال
        st = _state({"ealam_stamp_result": result, "ealam_stamp_calc_mode": "lawyer_fee"})
        await lh.ealam_in_lavayeh_stamp_type(_msg("📌 تمبر بدوی"), st)
        st.update_data.assert_awaited_with(ealam_stamp_amount=30_000_000, ealam_stamp_type="بدوی")

        # بازگشت از انتخاب نوع تمبر → دوباره مبلغ حق‌الوکاله
        st = _state({"ealam_stamp_result": result, "ealam_stamp_calc_mode": "lawyer_fee"})
        await lh.ealam_in_lavayeh_stamp_type(_msg("🔙 بازگشت"), st)
        st.set_state.assert_awaited_with(Form.ealam_vakalaht_lawyer_fee_amount)

    asyncio.run(scenario())


# ── پاپ‌آپ ورود همزمان ───────────────────────────────────────────────────

SAMPLE = ("با این شناسه «2281365549»، در ساعت 15:32 ورود به سامانه در صفحه یا رایانه ای دیگر "
          "انجام شده و اعتبار ورود قبلی ( ساعت 15:06 ) منقضی شده است")


def test_concurrent_login_text():
    from browser_helpers import is_concurrent_login_text
    assert is_concurrent_login_text(SAMPLE)
    assert is_concurrent_login_text(SAMPLE.replace("ی", "ي").replace("رایانه ای", "رایانه‌ای"))
    assert not is_concurrent_login_text("شماره قرارداد معتبر نمی باشد")
    assert not is_concurrent_login_text("")
    import tajdid_nazar_scenario as tn
    assert tn._is_session_error_text(SAMPLE.replace("ی", "ي"))
