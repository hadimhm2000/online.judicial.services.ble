"""
ساعت کاری ربات — از پنل ادمین (جدول WorkingHour، دیالوگ «ساعت کاری»).

قبلاً این فایل بازهٔ ۱۴ الی ۲۲ را هاردکد کرده بود و تنظیمات پنل هیچ‌جا خوانده
نمی‌شد. حالا:
  - refresh_loop() (از bot.py) هر REFRESH_SECONDS برنامهٔ هفتگی را از
    GET /api/admin/working-hours می‌خواند؛ تغییر در پنل حداکثر ظرف یک دقیقه
    اعمال می‌شود.
  - آخرین برنامهٔ دریافتی در working_hours_cache.json ذخیره می‌شود تا اگر پنل
    هنگام استارت ربات بالا نبود، همان برنامه (نه پیش‌فرض) استفاده شود.
  - اگر هیچ برنامه‌ای در دسترس نبود: پیش‌فرض قدیمی ۱۴ الی ۲۲ همهٔ روزها.

dayOfWeek پنل: 0=شنبه، 1=یکشنبه، … 6=جمعه (به وقت تهران).
اگر ساعت پایان ≤ ساعت شروع باشد، بازه از نیمه‌شب عبور می‌کند (مثلاً ۲۰ الی ۲).
"""
import asyncio
import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

# پیش‌فرض (فقط وقتی هیچ برنامه‌ای از پنل دریافت نشده)
START_HOUR = 14
END_HOUR = 22

REFRESH_SECONDS = 60
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "working_hours_cache.json")

_DAY_NAMES = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")


def _default_day(dow: int) -> dict:
    return {"dayOfWeek": dow, "startHour": START_HOUR, "startMin": 0,
            "endHour": END_HOUR, "endMin": 0, "enabled": True}


_schedule: dict[int, dict] = {d: _default_day(d) for d in range(7)}
_source = "default"   # default | cache | panel


def _normalize(items) -> dict[int, dict] | None:
    """اعتبارسنجی خروجی پنل؛ None اگر قابل استفاده نیست."""
    if not isinstance(items, list) or not items:
        return None
    out: dict[int, dict] = {}
    try:
        for it in items:
            dow = int(it["dayOfWeek"])
            if not 0 <= dow <= 6:
                return None
            day = {
                "dayOfWeek": dow,
                "startHour": int(it.get("startHour", START_HOUR)),
                "startMin": int(it.get("startMin", 0)),
                "endHour": int(it.get("endHour", END_HOUR)),
                "endMin": int(it.get("endMin", 0)),
                "enabled": bool(it.get("enabled", True)),
            }
            if not (0 <= day["startHour"] <= 23 and 0 <= day["endHour"] <= 23
                    and 0 <= day["startMin"] <= 59 and 0 <= day["endMin"] <= 59):
                return None
            out[dow] = day
    except (KeyError, TypeError, ValueError):
        return None
    # روزی که در پنل ردیف ندارد → تعطیل (پنل همیشه هر ۷ روز را ذخیره می‌کند)
    for d in range(7):
        out.setdefault(d, {**_default_day(d), "enabled": False})
    return out


def _load_cache():
    global _schedule, _source
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            sched = _normalize(json.load(f))
        if sched:
            _schedule = sched
            _source = "cache"
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"[WORKING_HOURS] خواندن {CACHE_FILE} ناموفق: {e}")


def _save_cache():
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([_schedule[d] for d in range(7)], f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        logger.warning(f"[WORKING_HOURS] ذخیرهٔ {CACHE_FILE} ناموفق: {e}")


_load_cache()


async def refresh() -> bool:
    """یک‌بار برنامه را از پنل بخوان؛ True در صورت موفقیت."""
    global _schedule, _source
    from panel_sync import get_working_hours
    sched = _normalize(await get_working_hours())
    if not sched:
        return False
    if sched != _schedule or _source != "panel":
        if sched != _schedule:
            logger.info(f"[WORKING_HOURS] برنامهٔ جدید از پنل: {describe_week(sched)}")
        _schedule = sched
        _source = "panel"
        _save_cache()
    return True


async def refresh_loop():
    while True:
        try:
            await refresh()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[WORKING_HOURS] خطا در به‌روزرسانی ساعت کاری: {e}")
        await asyncio.sleep(REFRESH_SECONDS)


# ── پرس‌وجو ──────────────────────────────────────────────────────────────

def now_tehran() -> datetime.datetime:
    return datetime.datetime.now(TEHRAN_TZ)


def _to_tehran(now: datetime.datetime | None) -> datetime.datetime:
    if now is None:
        return now_tehran()
    if now.tzinfo is None:
        return now.replace(tzinfo=TEHRAN_TZ)
    return now.astimezone(TEHRAN_TZ)


def panel_dow(d: datetime.date) -> int:
    """weekday پایتون (دوشنبه=0) → dayOfWeek پنل (شنبه=0)."""
    return (d.weekday() + 2) % 7


def _window(day_date: datetime.date):
    """(start, end) به وقت تهران برای بازهٔ کاری‌ای که در day_date شروع می‌شود؛ یا None."""
    cfg = _schedule.get(panel_dow(day_date))
    if not cfg or not cfg.get("enabled"):
        return None
    start = datetime.datetime.combine(
        day_date, datetime.time(cfg["startHour"], cfg["startMin"]), tzinfo=TEHRAN_TZ)
    end = datetime.datetime.combine(
        day_date, datetime.time(cfg["endHour"], cfg["endMin"]), tzinfo=TEHRAN_TZ)
    if end <= start:
        end += datetime.timedelta(days=1)   # عبور از نیمه‌شب
    return start, end


def is_working_hours(now: datetime.datetime | None = None) -> bool:
    now = _to_tehran(now)
    for day in (now.date(), now.date() - datetime.timedelta(days=1)):
        w = _window(day)
        if w and w[0] <= now < w[1]:
            return True
    return False


async def is_within_working_hours():
    """سازگاری با کد قدیمی: (در_بازه: bool, تنظیمات_امروز: dict)"""
    now = now_tehran()
    return is_working_hours(now), dict(_schedule.get(panel_dow(now.date())) or {})


def next_start(now: datetime.datetime | None = None) -> datetime.datetime | None:
    """شروع بازهٔ کاری بعدی (اگر الان داخل بازه‌ایم: شروع بازهٔ بعد از این)."""
    now = _to_tehran(now)
    for i in range(0, 8):
        w = _window(now.date() + datetime.timedelta(days=i))
        if w and w[0] > now:
            return w[0]
    return None


def _hm(h: int, m: int) -> str:
    return f"{h}:{m:02d}"


def today_label(now: datetime.datetime | None = None) -> str:
    """مثل «14:00 الی 22:00» یا «تعطیل» برای امروز."""
    cfg = _schedule.get(panel_dow(_to_tehran(now).date()))
    if not cfg or not cfg.get("enabled"):
        return "تعطیل"
    return f"{_hm(cfg['startHour'], cfg['startMin'])} الی {_hm(cfg['endHour'], cfg['endMin'])}"


def today_bounds(now: datetime.datetime | None = None) -> tuple[str, str]:
    """(شروع، پایان) امروز به‌صورت متن «H:MM» — برای قالب‌های {start}/{end}."""
    cfg = _schedule.get(panel_dow(_to_tehran(now).date()))
    if not cfg or not cfg.get("enabled"):
        return "—", "—"
    return _hm(cfg["startHour"], cfg["startMin"]), _hm(cfg["endHour"], cfg["endMin"])


def next_start_label(now: datetime.datetime | None = None) -> str:
    """مثل «14:00» (امروز) یا «فردا 8:30» یا «دوشنبه 9:00»."""
    now = _to_tehran(now)
    ns = next_start(now)
    if ns is None:
        return "—"
    hm = _hm(ns.hour, ns.minute)
    days = (ns.date() - now.date()).days
    if days == 0:
        return hm
    if days == 1:
        return f"فردا {hm}"
    return f"{_DAY_NAMES[panel_dow(ns.date())]} {hm}"


def describe_week(sched: dict | None = None) -> str:
    sched = sched or _schedule
    parts = []
    for d in range(7):
        c = sched.get(d)
        if not c or not c.get("enabled"):
            parts.append(f"{_DAY_NAMES[d]}: تعطیل")
        else:
            parts.append(f"{_DAY_NAMES[d]}: {_hm(c['startHour'], c['startMin'])}-{_hm(c['endHour'], c['endMin'])}")
    return " | ".join(parts)


def source() -> str:
    return _source
