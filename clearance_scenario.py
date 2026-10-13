"""
clearance_scenario.py — مراحل سامانه برای «درخواست گواهی عدم سوءپیشینه» (۱۴۰۵/۰۷)
══════════════════════════════════════════════════════════════════════════════

طبق دستور کارفرما هر درخواست در *تب اختصاصی خودش* انجام می‌شود (چون روند
طول می‌کشد و اطلاعات باید روی صفحه بماند) و تب تا پایان درخواست باز می‌ماند.

فازها (هر فاز روی تب همان درخواست؛ قفل جداگانه برای هر درخواست):
  send_code  (در نوبت — job_queue: CLEARANCE_SEND_CODE)
      منوی «درخواست گواهی عدم سوءپیشینه» → کدملی → تاریخ تولد → «ارسال رمز موقت»
        «رمز موقت به شماره همراه ارسال شد» / «… طی ۱۰ دقیقه گذشته ارسال شده»
            → به کاربر: ۷ دقیقه فرصت ارسال کد
        «اطلاعاتی بااین شماره ملی وتاریخ تولد پیدا نشد» → پنجرهٔ ۴۵ دقیقه‌ای ویرایش
        هر خطای دیگر → یک‌بار تکرار کل روند
  code       (خارج از نوبت — مستقیماً با asyncio.create_task)
      ورود رمز ۵ رقمی → «دریافت مشخصات از ثنا» → محو شدن نوار لودینگ بدون خطا
        «زمان اعتبار رمز موقت منقضی شده…» → ۳۰ دقیقه بعد ارسال مجدد کد
        هر خطای دیگر → یک‌بار تکرار
      سپس (ادامهٔ همان تسک) ثبت:
      گزینهٔ «شخص» → توضیحات → «ثبت موقت درخواست» (تا ۲ تکرار) → «محاسبه هزینه»
      → شناسه پرداخت (اگر نیامد «محاسبه هزینه گواهی…» تا ۲ بار) → فقط برای مدیر
  finalize   (در نوبت — job_queue: CLEARANCE_FINALIZE، پس از «پرداخت کردم» مدیر)
      «جستجو» → «بازیابی اطلاعات با موفقیت…» (بستن) → «تایید نهایی…» → پیام
      «… سابقه یابی خودکار …» (بستن) → «چاپ رسید…» → ارسال چاپ برای کاربر

در هر مرحله پاپ‌آپ «ورود همزمان» (رایانه ای دیگر) به مدیر اعلام می‌شود
(handle_session_expired — لاگین مجدد) و همان مرحله دوباره انجام می‌شود.
نتیجهٔ هر فاز با on_* در clearance_handlers به کاربر/مدیر اعلام می‌شود.
"""

import asyncio
import logging
import os
import re

from aiogram import Bot

import runtime_state
from browser_helpers import (
    _consume_session_lost_flag, handle_session_expired, is_concurrent_login_text,
    print_page_session_expired,
    wait_for_angular_idle, wait_for_sana_inquiry_loading)
from config import temp_path
from error_catalog import normalize

logger = logging.getLogger(__name__)

OFFICES_URL = "https://sakha2.adliran.ir/Offices/Index"
MENU_TEXT = "درخواست گواهی عدم سو"

SEL_NID = "#txtNationalityCode"
SEL_BIRTH = "input[name='txtpersonBirthDate']"
SEL_SEND_TEMP = "button[ng-click='actions.sendTempPassword()']"
SEL_TEMP_PASS = "input[ng-model='viewModel.tempPassword']"
SEL_GET_SANA = "button[ng-click='actions.getPersonDataFromSana()']"
SEL_PERSON_RADIO = "#person"
SEL_DESCRIPTION = "#txtDescription"
SEL_TEMP_SAVE = "button[ng-click='actions.setClearanceData()']"
SEL_CALC_CASH = "#btnCalculateCash"
SEL_SEARCH = "#btnGetClearanceCertRequestData"

# مرحلهٔ اول پس از کلیک منو: «ثبت درخواست گواهی عدم سوء پیشینه» (۱۴۰۵/۰۷)
STEP_REGISTER = "ثبت درخواست گواهی عدم سو"
STEP_COST = "محاسبه هزینه"
STEP_FINAL = "تایید نهایی گواهی عدم سو"
STEP_PRINT = "چاپ رسید درخواست گواهی"

# نتایج فازها
OK = "ok"
WRONG_ID = "wrong_id"
CODE_EXPIRED = "code_expired"
FAILED = "failed"
TAB_LOST = "tab_lost"

# تب اختصاصی هر درخواست (rid → page) و قفل هر درخواست
_tabs: dict = {}
_locks: dict = {}

# حداکثر دفعات لاگین مجدد در یک مرحله (جلوگیری از حلقهٔ بی‌پایان)
_MAX_RELOGINS = 3


def is_clearance_page(page) -> bool:
    return page is not None and any(p is page for p in _tabs.values())


def _lock(rid: str) -> asyncio.Lock:
    lk = _locks.get(rid)
    if lk is None:
        lk = _locks[rid] = asyncio.Lock()
    return lk


def _page_usable(page) -> bool:
    if page is None:
        return False
    try:
        return (not page.is_closed()) and page.context is runtime_state.browser_context
    except Exception:
        return False


def has_tab(rid: str) -> bool:
    return _page_usable(_tabs.get(rid))


async def close_tab(rid: str):
    page = _tabs.pop(rid, None)
    _locks.pop(rid, None)
    if page is None or page is runtime_state.sana_page:
        return
    try:
        if not page.is_closed():
            await page.close()
        logger.info(f"[CLEARANCE] تب درخواست {rid} بسته شد")
    except Exception:
        pass


async def _new_tab(rid: str):
    await close_tab_only(rid)
    ctx = runtime_state.browser_context
    if ctx is None:
        raise RuntimeError("browser_context در دسترس نیست")
    page = await ctx.new_page()
    _tabs[rid] = page
    try:
        from scenarios import _attach_debug_listeners
        await _attach_debug_listeners(page)
    except Exception:
        pass
    logger.info(f"[CLEARANCE] تب جدید برای درخواست {rid} باز شد")
    return page


async def close_tab_only(rid: str):
    """بستن تب بدون حذف قفل (داخل قفل همان درخواست صدا زده می‌شود)."""
    page = _tabs.pop(rid, None)
    if page is None or page is runtime_state.sana_page:
        return
    try:
        if not page.is_closed():
            await page.close()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# ابزار صفحه
# ════════════════════════════════════════════════════════════════════════════

_JS_POPUP_TEXT = '''() => {
    const popups = Array.from(document.querySelectorAll('.sweet-alert'));
    for (const popup of popups) {
        const st = window.getComputedStyle(popup);
        if (st.display === 'none' || st.visibility === 'hidden') continue;
        if (!popup.classList.contains('showSweetAlert') && !popup.classList.contains('visible')) continue;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const txt = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(t => t && t.trim()).join(' - ').trim();
        return txt || (popup.innerText || '').trim() || '(popup)';
    }
    return '';
}'''

_JS_CLOSE_POPUP = '''() => {
    const popups = Array.from(document.querySelectorAll('.sweet-alert.showSweetAlert'));
    for (const popup of popups) {
        if (window.getComputedStyle(popup).display === 'none') continue;
        const btn = popup.querySelector('button.confirm') || popup.querySelector('button.cancel');
        if (btn) { btn.click(); return true; }
    }
    return false;
}'''

_JS_STEP_BOX = '''(args) => {
    const norm = t => String(t || '').replace(/ي/g, 'ی').replace(/ك/g, 'ک')
        .replace(/[\\u200c\\u200d]/g, '').replace(/\\s+/g, ' ').trim();
    const heads = Array.from(document.querySelectorAll('.box .heading h5, .box h5'));
    const h = heads.find(el => norm(el.innerText).includes(norm(args.text)));
    if (!h) return false;
    const box = h.closest('.box');
    if (!box) return false;
    const r = box.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    if (args.click) box.click();
    return true;
}'''

_JS_PAYMENT_ID = '''() => {
    const fa = '۰۱۲۳۴۵۶۷۸۹', ar = '٠١٢٣٤٥٦٧٨٩';
    const toEn = s => String(s || '').replace(/[۰-۹]/g, d => fa.indexOf(d))
        .replace(/[٠-٩]/g, d => ar.indexOf(d)).replace(/\\s+/g, '');
    for (const td of Array.from(document.querySelectorAll('td'))) {
        const r = td.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        const t = toEn(td.innerText);
        if (/^\\d{16,22}$/.test(t)) return t;
    }
    return '';
}'''


async def _popup_text(page) -> str:
    try:
        return await page.evaluate(_JS_POPUP_TEXT) or ""
    except Exception:
        return ""


async def _close_popup(page):
    try:
        if await page.evaluate(_JS_CLOSE_POPUP):
            await asyncio.sleep(1.2)
    except Exception:
        pass


async def _session_lost(page, popup_text: str = "") -> bool:
    """پاپ‌آپ «ورود همزمان» (یا علامت ناظر صفحه)؟ — فقط عبارت‌های اختصاصی آن،
    نه «منقضی» تنها (پیام «زمان اعتبار رمز موقت منقضی شده» نباید اشتباه شود)."""
    if popup_text and is_concurrent_login_text(popup_text):
        await _consume_session_lost_flag(page)
        return True
    return bool(await _consume_session_lost_flag(page))


async def _relogin(page, bot: Bot, user_id: int):
    """اطلاع به مدیر برای لاگین مجدد و انتظار تا تایید (همان روند سایر بخش‌ها)."""
    logger.warning(f"[CLEARANCE] ورود همزمان — درخواست لاگین مجدد از مدیر (user={user_id})")
    await handle_session_expired(bot, user_id, page=page)


async def _settle(page, prefix: str = "CLEARANCE"):
    """انتظار برای نوار لودینگ بالای صفحه + آرام شدن انگولار."""
    try:
        await wait_for_sana_inquiry_loading(page, appear_grace=3.0, max_wait=120, prefix=prefix)
    except Exception:
        pass


async def _wait_popup(page, seconds: float = 4.0) -> str:
    """پس از پایان لودینگ تا چند ثانیه منتظر پاپ‌آپ می‌ماند؛ متن آن یا ''."""
    loop = asyncio.get_event_loop()
    end = loop.time() + seconds
    while True:
        txt = await _popup_text(page)
        if txt or loop.time() >= end:
            return txt
        await asyncio.sleep(0.5)


async def _wait_enabled(page, selector: str, timeout: float = 30.0, state: str = "visible") -> bool:
    try:
        await page.wait_for_selector(f"{selector}:not([disabled])", state=state,
                                     timeout=int(timeout * 1000))
        return True
    except Exception:
        return False


async def _fill(page, selector: str, value: str):
    loc = page.locator(selector).first
    await loc.click()
    await loc.fill("")
    await loc.type(value, delay=60)
    try:
        await loc.dispatch_event("input")
        await loc.dispatch_event("change")
        await loc.dispatch_event("blur")
    except Exception:
        pass


async def _step_box(page, text: str, click: bool) -> bool:
    try:
        return bool(await page.evaluate(_JS_STEP_BOX, {"text": text, "click": click}))
    except Exception:
        return False


async def _wait_step_box(page, text: str, seconds: float) -> bool:
    loop = asyncio.get_event_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        if await _step_box(page, text, click=False):
            return True
        if await _popup_text(page):
            return False
        await asyncio.sleep(0.7)
    return False


def _norm(text: str) -> str:
    return normalize(text or "").replace(" ", "")


# ════════════════════════════════════════════════════════════════════════════
# فاز ۱: باز کردن فرم + ارسال رمز موقت
# ════════════════════════════════════════════════════════════════════════════

async def _open_form(page, nid: str, birth: str) -> bool:
    """صفحهٔ اصلی → منوی گواهی عدم سوءپیشینه → کدملی و تاریخ تولد."""
    from browser_helpers import click_sana_main_menu
    await page.goto(OFFICES_URL, timeout=60000)
    await asyncio.sleep(2)
    await wait_for_angular_idle(page)
    if not await click_sana_main_menu(page, MENU_TEXT, timeout_sec=25, prefix="CLEARANCE"):
        return False
    await _settle(page)
    # ⭐ گزینهٔ «ثبت درخواست گواهی عدم سوء پیشینه» و سپس ادامهٔ همان مراحل
    if not await _wait_step_box(page, STEP_REGISTER, 25):
        logger.warning("[CLEARANCE] گزینهٔ «ثبت درخواست گواهی عدم سوء پیشینه» پیدا نشد")
        return False
    await _step_box(page, STEP_REGISTER, click=True)
    await _settle(page)
    try:
        await page.wait_for_selector(SEL_NID, state="visible", timeout=30000)
    except Exception:
        return False
    await _settle(page)
    await _fill(page, SEL_NID, nid)
    await asyncio.sleep(0.5)
    await _fill(page, SEL_BIRTH, birth)
    await asyncio.sleep(0.8)
    return True


def classify_send_code_popup(text: str) -> str:
    n = _norm(text)
    if not n:
        return FAILED
    if "پیدانشد" in n and ("شمارهملی" in n or "تاریختولد" in n):
        return WRONG_ID
    if "رمزموقت" in n and "ارسال" in n and "خطا" not in n:
        # «رمز موقت به شماره همراه ارسال شد» یا «… طی ۱۰ دقیقه گذشته ارسال شده است»
        return OK
    return FAILED


async def send_code(rid: str, req: dict, bot: Bot) -> tuple[str, str]:
    """خروجی: (نتیجه، متن آخرین پاپ‌آپ/خطا)."""
    user_id = req["uid"]
    last = ""
    attempts, relogins = 0, 0
    while attempts < 2:
        attempts += 1
        try:
            page = await _new_tab(rid)
            if not await _open_form(page, req["nid"], req["birth"]):
                if await _session_lost(page, await _popup_text(page)) and relogins < _MAX_RELOGINS:
                    relogins += 1
                    await _relogin(page, bot, user_id)
                    attempts -= 1
                    continue
                last = "فرم درخواست گواهی در سامانه باز نشد"
                logger.warning(f"[CLEARANCE] {last} (تلاش {attempts}/2، rid={rid})")
                continue
            if not await _wait_enabled(page, SEL_SEND_TEMP):
                last = "دکمهٔ «ارسال رمز موقت» فعال نشد"
                continue
            await page.click(SEL_SEND_TEMP)
            await _settle(page)
            txt = await _wait_popup(page, 8)
            if await _session_lost(page, txt):
                if relogins < _MAX_RELOGINS:
                    relogins += 1
                    await _relogin(page, bot, user_id)
                    attempts -= 1
                continue
            kind = classify_send_code_popup(txt)
            last = txt or "پاسخی از سامانه دریافت نشد"
            await _close_popup(page)
            logger.info(f"[CLEARANCE] ارسال رمز موقت rid={rid}: {kind} — {txt[:120]}")
            if kind in (OK, WRONG_ID):
                return kind, txt
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error(f"[CLEARANCE] خطا در ارسال رمز موقت (تلاش {attempts}/2، rid={rid}): {e}",
                         exc_info=True)
    return FAILED, last


# ════════════════════════════════════════════════════════════════════════════
# فاز ۲: ورود رمز موقت + ثبت موقت + شناسه پرداخت
# ════════════════════════════════════════════════════════════════════════════

def classify_code_popup(text: str) -> str:
    n = _norm(text)
    if not n:
        return OK
    if "رمزموقت" in n and "منقضی" in n:
        return CODE_EXPIRED
    return FAILED


async def submit_code(rid: str, req: dict, code: str, bot: Bot) -> tuple[str, str]:
    user_id = req["uid"]
    page = _tabs.get(rid)
    if not _page_usable(page):
        # تب از دست رفته (مثلاً بازسازی مرورگر) — فرم از نو، بدون ارسال رمز جدید
        page = await _new_tab(rid)
        if not await _open_form(page, req["nid"], req["birth"]):
            return TAB_LOST, "فرم درخواست گواهی در سامانه باز نشد"
    last = ""
    attempts, relogins = 0, 0
    while attempts < 2:
        attempts += 1
        try:
            await _close_popup(page)
            if not await _wait_enabled(page, SEL_TEMP_PASS, 20):
                last = "فیلد رمز موقت فعال نیست"
                continue
            await _fill(page, SEL_TEMP_PASS, code)
            await asyncio.sleep(0.5)
            await page.click(SEL_GET_SANA)
            await _settle(page)
            txt = await _wait_popup(page, 4)
            if await _session_lost(page, txt):
                if relogins < _MAX_RELOGINS:
                    relogins += 1
                    await _relogin(page, bot, user_id)
                    attempts -= 1
                continue
            kind = classify_code_popup(txt)
            logger.info(f"[CLEARANCE] دریافت مشخصات از ثنا rid={rid}: {kind} — {txt[:120]}")
            if kind == OK:
                return OK, ""
            last = txt
            await _close_popup(page)
            if kind == CODE_EXPIRED:
                return CODE_EXPIRED, txt
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error(f"[CLEARANCE] خطا در دریافت مشخصات از ثنا (rid={rid}): {e}", exc_info=True)
    return FAILED, last


async def register(rid: str, req: dict, bot: Bot) -> tuple[str, str]:
    """گزینهٔ شخص + توضیحات + ثبت موقت + محاسبه هزینه → (نتیجه، شناسه پرداخت یا خطا)."""
    user_id = req["uid"]
    page = _tabs.get(rid)
    if not _page_usable(page):
        return TAB_LOST, "تب درخواست بسته شده است"
    last = ""
    relogins = 0

    # ── گزینهٔ «شخص» + توضیحات + «ثبت موقت درخواست» (اولی + تا ۲ تکرار) ──
    saved = False
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            await _close_popup(page)
            # رادیو ممکن است با CSS پنهان شده باشد (فقط برچسبش دیده شود)
            if not await _wait_enabled(page, SEL_PERSON_RADIO, 20, state="attached"):
                last = "گزینهٔ «شخص» فعال نشد (مشخصات از ثنا دریافت نشده)"
                continue
            try:
                await page.check(SEL_PERSON_RADIO, force=True, timeout=5000)
            except Exception:
                await page.evaluate(f"""() => {{
                    const r = document.querySelector("{SEL_PERSON_RADIO}");
                    if (r) {{ r.click(); r.dispatchEvent(new Event('change', {{bubbles: true}})); }}
                }}""")
            await asyncio.sleep(0.5)
            await page.locator(SEL_DESCRIPTION).first.fill(req.get("desc") or "")
            try:
                await page.locator(SEL_DESCRIPTION).first.dispatch_event("change")
            except Exception:
                pass
            await asyncio.sleep(0.5)
            await page.click(SEL_TEMP_SAVE)
            await _settle(page)
            if await _wait_step_box(page, STEP_COST, 15):
                saved = True
                break
            txt = await _popup_text(page)
            if await _session_lost(page, txt):
                if relogins < _MAX_RELOGINS:
                    relogins += 1
                    await _relogin(page, bot, user_id)
                    attempts -= 1
                continue
            last = txt or "گزینهٔ «محاسبه هزینه» ظاهر نشد"
            logger.warning(f"[CLEARANCE] ثبت موقت ناموفق (تلاش {attempts}/3، rid={rid}): {last[:150]}")
            await _close_popup(page)
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error(f"[CLEARANCE] خطا در ثبت موقت (rid={rid}): {e}", exc_info=True)
    if not saved:
        return FAILED, last

    # ── «محاسبه هزینه» → شناسه پرداخت (اگر نیامد «محاسبه هزینه گواهی…» تا ۲ بار) ──
    try:
        await _step_box(page, STEP_COST, click=True)
        await _settle(page)
        for attempt in range(3):
            pay_id = await _wait_payment_id(page, 10)
            if pay_id:
                return OK, pay_id
            txt = await _popup_text(page)
            if await _session_lost(page, txt) and relogins < _MAX_RELOGINS:
                relogins += 1
                await _relogin(page, bot, user_id)
            elif txt:
                last = txt
                await _close_popup(page)
            if attempt == 2:
                break
            if await _wait_enabled(page, SEL_CALC_CASH, 15):
                await page.click(SEL_CALC_CASH)
                await _settle(page)
        return FAILED, last or "شناسه پرداخت نمایش داده نشد"
    except Exception as e:
        logger.error(f"[CLEARANCE] خطا در محاسبه هزینه (rid={rid}): {e}", exc_info=True)
        return FAILED, f"{type(e).__name__}: {str(e)[:200]}"


async def _wait_payment_id(page, seconds: float) -> str:
    loop = asyncio.get_event_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        try:
            pid = await page.evaluate(_JS_PAYMENT_ID)
        except Exception:
            pid = ""
        if pid:
            return pid
        await asyncio.sleep(0.8)
    return ""


# ════════════════════════════════════════════════════════════════════════════
# فاز ۳: پس از پرداخت مدیر — جستجو، تایید نهایی، چاپ رسید
# ════════════════════════════════════════════════════════════════════════════

def is_search_success(text: str) -> bool:
    return "بازیابیاطلاعاتباموفقیت" in _norm(text)


def is_final_success(text: str) -> bool:
    n = _norm(text)
    return "سابقهیابیخودکار" in n or "موردبررسیقرارگرفت" in n


async def finalize(rid: str, req: dict, bot: Bot) -> tuple[str, str]:
    """خروجی: (OK، مسیر فایل چاپ) یا (FAILED/TAB_LOST، متن خطا)."""
    user_id = req["uid"]
    page = _tabs.get(rid)
    if not _page_usable(page):
        return TAB_LOST, "تب درخواست بسته شده است (مثلاً پس از ری‌استارت ربات یا مرورگر)"
    relogins = 0

    # ── «جستجو» → «بازیابی اطلاعات با موفقیت انجام شد.» → بستن ──
    found, last = False, ""
    attempts = 0
    while attempts < 2:
        attempts += 1
        try:
            await _close_popup(page)
            if not await _wait_enabled(page, SEL_SEARCH, 20):
                last = "دکمهٔ «جستجو» پیدا/فعال نشد"
                continue
            await page.click(SEL_SEARCH)
            await _settle(page)
            txt = await _wait_popup(page, 8)
            if await _session_lost(page, txt):
                if relogins < _MAX_RELOGINS:
                    relogins += 1
                    await _relogin(page, bot, user_id)
                    attempts -= 1
                continue
            await _close_popup(page)
            if is_search_success(txt):
                found = True
                break
            last = txt or "پیام «بازیابی اطلاعات با موفقیت» نمایش داده نشد"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error(f"[CLEARANCE] خطا در جستجو (rid={rid}): {e}", exc_info=True)
    if not found:
        return FAILED, f"جستجو: {last}"

    # ── «تایید نهایی گواهی عدم سوءپیشینه» → پیام «… سابقه یابی خودکار …» ──
    confirmed = False
    attempts = 0
    while attempts < 2:
        attempts += 1
        try:
            await _close_popup(page)
            if not await _step_box(page, STEP_FINAL, click=True):
                last = "گزینهٔ «تایید نهایی گواهی عدم سوءپیشینه» پیدا نشد"
                await asyncio.sleep(2)
                continue
            await _settle(page)
            txt = await _wait_popup(page, 10)
            if await _session_lost(page, txt):
                if relogins < _MAX_RELOGINS:
                    relogins += 1
                    await _relogin(page, bot, user_id)
                    attempts -= 1
                continue
            await _close_popup(page)
            if is_final_success(txt):
                confirmed = True
                break
            last = txt or "پیام تایید نهایی نمایش داده نشد"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error(f"[CLEARANCE] خطا در تایید نهایی (rid={rid}): {e}", exc_info=True)
    if not confirmed:
        return FAILED, f"تایید نهایی: {last}"

    # ── «چاپ رسید درخواست گواهی سوءپیشینه» ──
    path = await _print_receipt(page, rid, bot, user_id)
    if not path:
        return FAILED, "چاپ رسید: فایل چاپ تهیه نشد"
    return OK, path


async def _print_receipt(page, rid: str, bot: Bot, user_id: int) -> str:
    from lavayeh_scenario import _is_valid_pdf_file
    pdf_path = temp_path(f"clearance_{rid}.pdf")
    png_path = temp_path(f"clearance_{rid}.png")
    ctx = runtime_state.browser_context
    for attempt in range(1, 3):
        target = None
        try:
            await _close_popup(page)
            try:
                async with ctx.expect_page(timeout=15000) as info:
                    if not await _step_box(page, STEP_PRINT, click=True):
                        raise RuntimeError("گزینهٔ «چاپ رسید» پیدا نشد")
                target = await info.value
                await target.wait_for_load_state("load", timeout=30000)
            except RuntimeError:
                raise
            except Exception:
                # چاپ در همان صفحه باز شد (تب جدیدی باز نشد)
                target = None
            await asyncio.sleep(6)
            shot_page = target or page
            txt = await _popup_text(shot_page)
            if await _session_lost(shot_page, txt):
                await _relogin(shot_page, bot, user_id)
                continue
            if target is not None and await print_page_session_expired(target):
                # ⭐ تب چاپ به‌جای رسید فقط اعلان انقضای نشست را دارد: بستن تب،
                # لاگین مجدد مدیر و زدن دوبارهٔ «چاپ رسید»
                try:
                    await target.close()
                except Exception:
                    pass
                await _relogin(page, bot, user_id)
                continue
            try:
                await shot_page.pdf(path=pdf_path, format="A4", print_background=True)
            except Exception as e:
                logger.info(f"[CLEARANCE] PDF چاپ ممکن نشد ({e}) — تصویر صفحه گرفته می‌شود")
            if _is_valid_pdf_file(pdf_path):
                return pdf_path
            await shot_page.screenshot(path=png_path, full_page=True)
            if os.path.exists(png_path) and os.path.getsize(png_path) > 1024:
                return png_path
        except Exception as e:
            logger.error(f"[CLEARANCE] خطا در چاپ رسید (تلاش {attempt}/2، rid={rid}): {e}", exc_info=True)
        finally:
            if target is not None:
                try:
                    await target.close()
                except Exception:
                    pass
    return ""


# ════════════════════════════════════════════════════════════════════════════
# اجرای فازها (قفل هر درخواست) — از browser_worker و هندلرها
# ════════════════════════════════════════════════════════════════════════════

async def process_clearance_task(data: dict, bot: Bot):
    """تسک‌های در نوبت (job_queue): CLEARANCE_SEND_CODE / CLEARANCE_FINALIZE."""
    import clearance_handlers as ch
    rid = data.get("rid")
    req = ch.get_request(rid)
    if not req:
        logger.warning(f"[CLEARANCE] درخواست {rid} برای تسک {data.get('task_type')} پیدا نشد")
        return
    task_type = data.get("task_type")
    try:
        async with _lock(rid):
            if task_type == "CLEARANCE_SEND_CODE":
                await ch.on_phase_started(bot, rid, "send_code")
                kind, info = await send_code(rid, req, bot)
                await ch.on_send_code_result(bot, rid, kind, info)
            elif task_type == "CLEARANCE_FINALIZE":
                await ch.on_phase_started(bot, rid, "finalize")
                kind, info = await finalize(rid, req, bot)
                await ch.on_finalize_result(bot, rid, kind, info)
    except Exception as e:
        logger.error(f"[CLEARANCE] خطای مدیریت‌نشده در {task_type} (rid={rid}): {e}", exc_info=True)
        await ch.on_unexpected_error(bot, rid, task_type, e, page=_tabs.get(rid))


async def run_code_task(rid: str, code: str, bot: Bot):
    """⭐ خارج از نوبت: ورود رمز موقت و ادامهٔ ثبت تا شناسه پرداخت."""
    import clearance_handlers as ch
    req = ch.get_request(rid)
    if not req:
        return
    try:
        async with _lock(rid):
            kind, info = await submit_code(rid, req, code, bot)
            if kind != OK:
                await ch.on_code_result(bot, rid, kind, info)
                return
            await ch.on_code_result(bot, rid, OK, "")
            await run_register_locked(rid, req, bot)
    except Exception as e:
        logger.error(f"[CLEARANCE] خطای مدیریت‌نشده در ورود رمز (rid={rid}): {e}", exc_info=True)
        await ch.on_unexpected_error(bot, rid, "CLEARANCE_CODE", e, page=_tabs.get(rid))


async def run_register_locked(rid: str, req: dict, bot: Bot):
    import clearance_handlers as ch
    kind, info = await register(rid, req, bot)
    await ch.on_register_result(bot, rid, kind, info)


async def run_register_task(rid: str, bot: Bot):
    """تلاش مجدد ثبت (دکمهٔ مدیر) — خارج از نوبت، روی همان تب."""
    import clearance_handlers as ch
    req = ch.get_request(rid)
    if not req:
        return
    try:
        async with _lock(rid):
            await run_register_locked(rid, req, bot)
    except Exception as e:
        logger.error(f"[CLEARANCE] خطای مدیریت‌نشده در ثبت (rid={rid}): {e}", exc_info=True)
        await ch.on_unexpected_error(bot, rid, "CLEARANCE_REGISTER", e, page=_tabs.get(rid))
