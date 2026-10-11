"""
pending_jobs.py — دفتر ماندگار تسک‌های ثبت در سامانه (ری‌استارت هیچ درخواستی را گم نکند)
══════════════════════════════════════════════════════════════════════════════

مشکل قبلی: runtime_state.job_queue فقط در حافظه بود. هر ثبت (لایحه، اظهارنامه،
دادخواست، اعتراضی و …) که پرداختش انجام شده و در صف منتظر مرورگر/لاگین بود، با
ری‌استارت، کرش یا انتقال سرور از بین می‌رفت و پرونده‌اش در پنل پس از ۲۴ ساعت
خودکار «لغو» می‌شد.

حالا:
  - هر تسکی که روی job_queue / priority_job_queue گذاشته می‌شود (به‌جز امضا،
    PRE_CHECK، گواهی عدم سوءپیشینه و چاپ نهایی که ماندگاری خودشان را دارند)
    با یک شناسهٔ _jid در pending_jobs.json ثبت می‌شود.
  - browser_worker هنگام شروع پردازش آن را «running» و پس از پایان حذف می‌کند.
  - در استارت ربات (bot.py)، تسک‌هایی که هنوز شروع نشده بودند به همان ترتیب
    ثبت، جلوتر از هر درخواست جدیدی دوباره وارد صف می‌شوند (و اگر خارج از ساعت
    کاری باشد، به صف ماندگار sana_gate می‌روند).
  - تسکی که وسط پردازش قطع شد (ری‌استارت/کرش) یا با خطای بحرانی تمام شد،
    خودکار دوباره اجرا نمی‌شود (ممکن است بخشی از آن در سامانه ثبت شده باشد و
    اجرای دوباره، ثبت تکراری بسازد) — در فهرست «ناموفق» می‌ماند تا مدیر با
    /pending بررسی و با یک دکمه دوباره در صف بگذارد.
  - کاربران این فهرست‌ها از لغو خودکار ۲۴ ساعته (stale_requests) مستثنی‌اند.
"""
import datetime
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_jobs.json")
FAILED_KEEP_DAYS = 7

# این تسک‌ها ماندگاری/بازیابی مخصوص خودشان را دارند یا فوری‌اند
_SKIP_TASK_TYPES = frozenset({
    "LAVAYEH_SEND_SIGN_CODE", "LAVAYEH_SUBMIT_SIGN",
    "TN_SEND_SIGN_CODE", "TN_SUBMIT_SIGN",
    "EZHHARNAMEH_SEND_SIGN_CODE", "EZHHARNAMEH_SUBMIT_SIGN",
    "PRE_CHECK", "CLEARANCE_SEND_CODE", "CLEARANCE_FINALIZE",
})

_state = {
    "jobs": {},     # jid -> {"job": {...}, "queued_at": iso, "status": "queued"|"running", "started_at": iso|None}
    "failed": [],   # [{"jid", "job", "failed_at", "error", "user_id", "label"}]
}


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _json_default(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    return str(obj)


def _save():
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, default=_json_default, indent=1)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.error(f"[PENDING_JOBS] خطا در ذخیره: {e}")


def load():
    """بارگذاری دفتر از دیسک — یک‌بار در استارت (bot.py)، قبل از هر put."""
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _state["jobs"] = data.get("jobs") or {}
        _state["failed"] = data.get("failed") or []
        _prune_failed()
        logger.info(f"[PENDING_JOBS] بارگذاری شد — در صف/در حال اجرا: {len(_state['jobs'])} | "
                    f"ناموفق: {len(_state['failed'])}")
    except Exception as e:
        logger.error(f"[PENDING_JOBS] خطا در بارگذاری {STATE_FILE}: {e}")


def _prune_failed():
    cutoff = datetime.datetime.now() - datetime.timedelta(days=FAILED_KEEP_DAYS)
    kept = []
    for it in _state["failed"]:
        try:
            if datetime.datetime.fromisoformat(it.get("failed_at", "")) >= cutoff:
                kept.append(it)
        except ValueError:
            pass
    _state["failed"] = kept[-500:]


def is_journaled(job) -> bool:
    if not isinstance(job, dict) or not job.get("user_id"):
        return False
    if job.get("final_print"):
        return False
    return job.get("task_type", "PRINT") not in _SKIP_TASK_TYPES


def label(job: dict) -> str:
    try:
        import sana_gate
        return sana_gate._job_label(job)
    except Exception:
        return str(job.get("task_type") or job.get("query_type") or "نامشخص")


def track(job):
    """ثبت تسک در دفتر (از runtime_state هنگام put). تکراری بی‌اثر است."""
    if not is_journaled(job):
        return
    jid = job.get("_jid")
    if not jid:
        jid = job["_jid"] = uuid.uuid4().hex[:12]
    entry = _state["jobs"].get(jid)
    if entry is None:
        _state["jobs"][jid] = {"job": job, "queued_at": _now_iso(), "status": "queued", "started_at": None}
    else:
        entry["job"] = job
        entry["status"] = "queued"
        entry["started_at"] = None
    _save()


def mark_running(job):
    jid = job.get("_jid") if isinstance(job, dict) else None
    entry = _state["jobs"].get(jid) if jid else None
    if entry:
        entry["status"] = "running"
        entry["started_at"] = _now_iso()
        _save()


def done(job):
    """پایان پردازش (موفق یا با خطایی که خود سناریو به کاربر اعلام کرده)."""
    jid = job.get("_jid") if isinstance(job, dict) else None
    if jid and _state["jobs"].pop(jid, None) is not None:
        _save()


# به صف ماندگار sana_gate منتقل شد — آن‌جا نگهداری می‌شود
forget = done


def fail(job, error: str):
    """تسک ناموفق/قطع‌شده → فهرست «ناموفق» برای بررسی مدیر (اجرای خودکار مجدد نمی‌شود)."""
    if not is_journaled(job):
        return
    jid = job.get("_jid") or uuid.uuid4().hex[:12]
    job["_jid"] = jid
    _state["jobs"].pop(jid, None)
    _state["failed"] = [it for it in _state["failed"] if it.get("jid") != jid]
    _state["failed"].append({
        "jid": jid, "job": job, "failed_at": _now_iso(), "error": str(error)[:300],
        "user_id": job.get("user_id"), "label": label(job),
    })
    _prune_failed()
    _save()


def restore() -> tuple[list, list]:
    """استارت ربات: (تسک‌های شروع‌نشده برای ورود دوباره به صف، تسک‌های قطع‌شده).

    تسک‌های «running» (وسط پردازش قطع شده‌اند) به فهرست ناموفق منتقل می‌شوند.
    """
    queued, interrupted = [], []
    for jid, entry in sorted(_state["jobs"].items(), key=lambda kv: kv[1].get("queued_at") or ""):
        job = entry.get("job") or {}
        job["_jid"] = jid
        if entry.get("status") == "running":
            interrupted.append(job)
        else:
            queued.append(job)
    for job in interrupted:
        fail(job, "ری‌استارت/کرش ربات حین پردازش این درخواست")
    return queued, interrupted


def failed_items() -> list:
    return list(_state["failed"])


def queued_count() -> int:
    return len(_state["jobs"])


def pop_failed(jid: str) -> dict | None:
    for it in _state["failed"]:
        if it.get("jid") == jid:
            _state["failed"].remove(it)
            _save()
            return it.get("job")
    return None


def user_ids() -> set:
    """کاربرانی که درخواست در دفتر دارند — از لغو خودکار ۲۴ ساعته مستثنی‌اند."""
    out = {str((e.get("job") or {}).get("user_id")) for e in _state["jobs"].values()}
    out.update(str(it.get("user_id")) for it in _state["failed"])
    out.discard("None")
    return out
