"""تنظیمات مشترک pytest — فایل‌های وضعیت در تست‌ها به پوشهٔ موقت می‌روند، نه پوشهٔ پروژه."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_invoice_guard_store(tmp_path, monkeypatch):
    try:
        import invoice_guard
    except Exception:
        yield
        return
    monkeypatch.setattr(invoice_guard, "STORE_FILE", str(tmp_path / "invoice_guard.json"))
    monkeypatch.setattr(invoice_guard, "_store", {})
    monkeypatch.setattr(invoice_guard, "_loaded", True)
    yield
