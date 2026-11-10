"""دکمهٔ «⚖️ اتوماسیون ویژه خدمات حقوقی»: فقط مدیر، ردیف اول، لینک با توکن معتبر."""
import base64

import pytest

import keyboards as kb
from config import ADMIN_ID


def _texts(markup):
    return [[b.text for b in row] for row in markup.keyboard]


def test_button_first_row_only_for_admin(monkeypatch):
    monkeypatch.delenv("LEGAL_BETA_IDS", raising=False)
    rows = _texts(kb.get_flow_type_kb(ADMIN_ID))
    assert rows[0] == [kb.LEGAL_AUTOMATION_TEXT]
    other = _texts(kb.get_flow_type_kb(ADMIN_ID + 12345))
    assert [kb.LEGAL_AUTOMATION_TEXT] not in other
    assert kb.LEGAL_AUTOMATION_TEXT not in str(_texts(kb.flow_type_kb))


def test_beta_env_opens_button(monkeypatch):
    monkeypatch.setenv("LEGAL_BETA_IDS", "555, 777")
    assert kb.legal_automation_allowed(555)
    assert not kb.legal_automation_allowed(556)


class _Msg:
    def __init__(self, uid):
        self.from_user = type("U", (), {"id": uid})()
        self.sent = []

    async def answer(self, text, reply_markup=None, **kw):
        self.sent.append((text, reply_markup))


@pytest.mark.asyncio
async def test_handler_server_side_check_and_link(monkeypatch):
    import legal_automation_handlers as h
    from legal_handoff import verify_token

    monkeypatch.setenv("LEGAL_BOT_USERNAME", "@legal_auto_bot")
    monkeypatch.setenv("HANDOFF_SECRET", "s3")
    monkeypatch.delenv("LEGAL_BETA_IDS", raising=False)
    m = _Msg(ADMIN_ID + 1)
    await h.open_legal_automation(m)
    assert m.sent[0][1] is None and "به‌زودی" in m.sent[0][0]
    m = _Msg(ADMIN_ID)
    await h.open_legal_automation(m)
    url = m.sent[0][1].inline_keyboard[0][0].url
    assert url.startswith("https://ble.ir/legal_auto_bot?start=")
    token = url.split("start=")[1]
    assert len(token) < 64 and verify_token(token, "s3", ADMIN_ID)
