"""تست اعتبارسنجی کدملی و شناسه ملی — اجرا: python -m pytest test_id_validation.py"""
import asyncio

from id_validation import (
    IdValidationMiddleware, is_valid_legal_id, is_valid_national_id, normalize_digits)


def test_valid_national_ids():
    assert is_valid_national_id("0499370899")
    assert is_valid_national_id("0084575948")
    assert is_valid_national_id("۰۴۹۹۳۷۰۸۹۹")  # ارقام فارسی


def test_invalid_national_ids():
    assert not is_valid_national_id("0499370898")  # رقم کنترل غلط
    assert not is_valid_national_id("1111111111")  # همهٔ ارقام یکسان
    assert not is_valid_national_id("1230000002")  # ارقام میانی صفر
    assert not is_valid_national_id("123456789")   # ۹ رقم


def test_legal_ids():
    assert is_valid_legal_id("10380284790")
    assert not is_valid_legal_id("10380284791")
    assert not is_valid_legal_id("1038028479")


def test_normalize_digits():
    assert normalize_digits("۰۴۹ ۹۳۷-۰۸۹۹") == "0499370899"


class _FakeMessage:
    def __init__(self, text):
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def _run(text, raw_state):
    import aiogram.types as t
    msg = _FakeMessage(text)
    called = []

    async def handler(event, data):
        called.append(True)

    mw = IdValidationMiddleware()
    orig = t.Message
    t.Message = _FakeMessage  # isinstance در middleware
    try:
        asyncio.run(mw(handler, msg, {"raw_state": raw_state}))
    finally:
        t.Message = orig
    return bool(called), msg.answers


def test_middleware_blocks_bad_nid_in_nid_state():
    passed, answers = _run("0499370898", "Form:lavayeh_national_id")
    assert not passed and answers


def test_middleware_passes_good_nid_and_other_input():
    assert _run("0499370899", "Form:lavayeh_national_id")[0]
    assert _run("🔙 بازگشت", "Form:lavayeh_national_id")[0]
    assert _run("0499370898", "Form:lavayeh_title")[0]       # state غیرمرتبط
    assert _run("12345", "Form:check_plaintiff_national_id")[0]  # طول اشتباه → هندلر سرویس


def test_middleware_company_state():
    assert not _run("10380284791", "Form:check_defendant_company_id")[0]
    assert _run("10380284790", "Form:check_defendant_company_id")[0]
