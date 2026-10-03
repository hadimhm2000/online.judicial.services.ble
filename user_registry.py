"""
user_registry.py — فهرست ماندگار همهٔ کاربران ربات + وضعیت دریافت PDF راهنما
══════════════════════════════════════════════════════════════════════════════

هر کاربری که پیامی به ربات بدهد یک‌بار ثبت می‌شود (guide_handlers.RegistryMiddleware).
برای هر کاربر نگه‌داری می‌شود:
  first_seen  زمان اولین مشاهده
  src         "live"  = از زمان فعال شدن این ماژول دیده شده
              "seed"  = کاربر قدیمی (از فایل‌های موجود ربات یا پنل وارد شده)
  guide       زمان دریافت PDF راهنما (None = هنوز دریافت نکرده)

قاعده: PDF راهنما در /start فقط برای کاربر «live» که هنوز راهنما نگرفته ارسال
می‌شود؛ کاربران قدیمی (seed) فقط با دستور ارسال همگانی مدیر راهنما می‌گیرند.

ذخیره: users_registry.json (ماندگار در ری‌استارت).
"""
import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
STORE_FILE = os.path.join(_HERE, "users_registry.json")

_store: dict = {"users": {}, "seeded_local": False}
_loaded = False


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load():
    global _store, _loaded
    _loaded = True
    if not os.path.exists(STORE_FILE):
        return
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _store = {"users": data.get("users", {}), "seeded_local": bool(data.get("seeded_local"))}
    except Exception as e:
        logger.error(f"[REGISTRY] خطا در خواندن {STORE_FILE}: {e}")


def save():
    tmp = STORE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False)
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[REGISTRY] خطا در ذخیره: {e}")


def _ensure():
    if not _loaded:
        _load()
        if not _store.get("seeded_local"):
            seed_from_local_files()


def _valid_uid(uid) -> str | None:
    s = str(uid).strip()
    return s if s.isdigit() and int(s) > 0 else None


def _add(uid, src: str) -> bool:
    key = _valid_uid(uid)
    if not key or key in _store["users"]:
        return False
    _store["users"][key] = {"first_seen": _now(), "src": src, "guide": None}
    return True


# ── ثبت کاربران ─────────────────────────────────────────────────────────

def touch(user_id) -> None:
    """ثبت کاربر در اولین پیام. هرگز استثنا بیرون نمی‌دهد."""
    try:
        _ensure()
        if _add(user_id, "live"):
            save()
    except Exception as e:
        logger.warning(f"[REGISTRY] touch ناموفق: {e}")


def add_seed_users(user_ids) -> int:
    """افزودن کاربران قدیمی (بدون ارسال خودکار راهنما). تعداد کاربر جدید را برمی‌گرداند."""
    _ensure()
    added = sum(1 for uid in user_ids if _add(uid, "seed"))
    if added:
        save()
    return added


def _json_keys(path: str, *subkeys) -> list:
    full = os.path.join(_HERE, path)
    if not os.path.exists(full):
        return []
    try:
        with open(full, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in subkeys:
            data = (data or {}).get(k, {})
        return list((data or {}).keys()) if isinstance(data, dict) else []
    except Exception as e:
        logger.warning(f"[REGISTRY] خواندن {path} ناموفق: {e}")
        return []


def seed_from_local_files() -> int:
    """یک‌بار: کاربران قدیمی را از فایل‌های ماندگار موجود ربات وارد می‌کند."""
    ids = set()
    ids.update(_json_keys("wallet.json", "users"))
    ids.update(_json_keys("user_files.json"))
    ids.update(_json_keys("subscriptions_store.json"))
    ids.update(_json_keys("feedback_state.json", "last_asked"))
    ids.update(_json_keys("bot_persisted_state.json", "user_free_usage"))
    try:
        with open(os.path.join(_HERE, "data", "card_payments.json"), "r", encoding="utf-8") as f:
            for entry in (json.load(f) or {}).values():
                if isinstance(entry, dict) and entry.get("uid"):
                    ids.add(str(entry["uid"]))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"[REGISTRY] خواندن card_payments.json ناموفق: {e}")
    added = sum(1 for uid in ids if _add(uid, "seed"))
    _store["seeded_local"] = True
    save()
    logger.info(f"[REGISTRY] {added} کاربر قدیمی از فایل‌های محلی ثبت شد")
    return added


# ── راهنما ──────────────────────────────────────────────────────────────

def needs_welcome_guide(user_id) -> bool:
    """کاربر جدید (live) که هنوز راهنما نگرفته است."""
    _ensure()
    u = _store["users"].get(str(user_id))
    return bool(u) and u.get("src") == "live" and not u.get("guide")


def mark_guide_sent(user_id, persist: bool = True) -> None:
    _ensure()
    key = _valid_uid(user_id)
    if not key:
        return
    u = _store["users"].setdefault(key, {"first_seen": _now(), "src": "live", "guide": None})
    u["guide"] = _now()
    if persist:
        save()


def clear_guide_sent(user_id) -> None:
    """ارسال ناموفق بود: کاربر دوباره در فهرست «دریافت‌نکرده» قرار می‌گیرد."""
    _ensure()
    u = _store["users"].get(str(user_id))
    if u and u.get("guide"):
        u["guide"] = None
        save()


def all_user_ids() -> list[int]:
    _ensure()
    return [int(k) for k in _store["users"]]


def users_without_guide() -> list[int]:
    _ensure()
    return [int(k) for k, u in _store["users"].items() if not u.get("guide")]


def stats() -> dict:
    _ensure()
    users = _store["users"].values()
    return {
        "total": len(_store["users"]),
        "live": sum(1 for u in users if u.get("src") == "live"),
        "seed": sum(1 for u in users if u.get("src") == "seed"),
        "with_guide": sum(1 for u in users if u.get("guide")),
    }
