"""تست راهنمای PDF و فهرست کاربران — اجرا: python -m pytest test_guide.py"""
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import guide_handlers
import user_registry
from guide_pdf import build_guide_pdf


@pytest.fixture(autouse=True)
def _tmp_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(user_registry, "_HERE", str(tmp_path))
    monkeypatch.setattr(user_registry, "STORE_FILE", str(tmp_path / "users_registry.json"))
    user_registry._store = {"users": {}, "seeded_local": False}
    user_registry._loaded = False
    return tmp_path


def test_old_users_from_local_files_do_not_get_welcome_guide(_tmp_registry):
    (_tmp_registry / "wallet.json").write_text(json.dumps({"users": {"111": {"balance": 0}}}))
    (_tmp_registry / "user_files.json").write_text(json.dumps({"222": []}))
    user_registry.touch(111)      # کاربر قدیمی
    user_registry.touch(333)      # کاربر جدید
    assert not user_registry.needs_welcome_guide(111)
    assert not user_registry.needs_welcome_guide(222)
    assert user_registry.needs_welcome_guide(333)
    assert sorted(user_registry.users_without_guide()) == [111, 222, 333]


def test_welcome_guide_sent_once(monkeypatch):
    user_registry.touch(500)
    send = AsyncMock(return_value=(True, {}))
    monkeypatch.setattr(guide_handlers, "send_guide", send)
    msg = MagicMock()
    msg.from_user.id = 500
    msg.chat.id = 500

    asyncio.run(guide_handlers.send_welcome_guide_if_new(msg))
    asyncio.run(guide_handlers.send_welcome_guide_if_new(msg))
    assert send.await_count == 1
    assert user_registry.stats()["with_guide"] == 1
    assert 500 not in user_registry.users_without_guide()


def test_panel_seed_users_are_not_new():
    user_registry.add_seed_users(["700", "x", "701"])
    user_registry.touch(700)
    assert not user_registry.needs_welcome_guide(700)
    assert user_registry.stats()["seed"] == 2


def test_guide_pdf_builds(tmp_path):
    out = tmp_path / "guide.pdf"
    assert build_guide_pdf(str(out))
    assert out.read_bytes()[:4] == b"%PDF"
