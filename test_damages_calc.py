"""تست محاسبهٔ خسارت تأخیر تأدیه و مهریه — اجرا: python -m pytest test_damages_calc.py"""
import pytest

import damages_calc as dc


@pytest.fixture(autouse=True)
def _tmp_cpi(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "CPI_FILE", str(tmp_path / "cpi_index.json"))
    rows = [(1400, m, 100 + m) for m in range(1, 13)]      # میانگین سال ۱۴۰۰ = 106.5
    rows += [(1401, m, 150 + m) for m in range(1, 13)]     # میانگین ۱۴۰۱ = 156.5
    rows += [(1402, m, 200 + m) for m in range(1, 7)]
    rows += [(1380, None, 5.0)]
    dc.import_rows(rows, base="1400=100")


def test_late_payment_uses_prev_month_of_calc_date():
    r = dc.calc_late_payment(1_000_000, (1400, 3, 10), (1402, 5, 1))
    assert r["due_key"] == "1400/03" and r["target_key"] == "1402/04"
    assert r["updated_amount"] == round(1_000_000 * 204 / 103)
    assert r["damages"] == r["updated_amount"] - 1_000_000
    assert not r["used_latest_available"]


def test_late_payment_falls_back_to_latest_month():
    r = dc.calc_late_payment(1_000_000, (1401, 1, 1), (1403, 1, 1))
    assert r["target_key"] == "1402/06" and r["used_latest_available"]


def test_late_payment_missing_due_month():
    with pytest.raises(dc.CpiMissing):
        dc.calc_late_payment(1_000_000, (1399, 1, 1), (1402, 5, 1))


def test_mahrieh_uses_year_before_payment_and_averages():
    r = dc.calc_mahrieh(10_000_000, 1400, payment_year=1402)
    assert r["target_year"] == 1401
    assert r["updated_amount"] == round(10_000_000 * 156.5 / 106.5)


def test_mahrieh_explicit_annual_index():
    r = dc.calc_mahrieh(1_000, 1380, payment_year=1401)
    assert r["base_index"] == 5.0 and r["target_index"] == 106.5


def test_missing_required_month():
    assert dc.missing_required_month((1402, 7, 3)) is None
    assert dc.missing_required_month((1402, 8, 3)) == (1402, 7)


def test_parse_inputs():
    assert dc.parse_jalali_date("۱۴۰۲/۰۸/۱۵") == (1402, 8, 15)
    assert dc.parse_jalali_date("1402/08/31") is None
    assert dc.parse_amount("۵۰۰,۰۰۰") == 500000
