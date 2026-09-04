# -*- coding: utf-8 -*-
"""
استخراج «شناسه پرداخت» از بخش هزینه سامانه قضایی + ثبت در گوگل‌شیت + ارسال فقط به مدیر.

طبق درخواست کارفرما:
  - در کلیه بخش‌های ربات «به جز استعلام»، وقتی ربات وارد قسمت هزینه شد
    (مرحله «محاسبه و دريافت هزينه» در سامانه)، شناسه پرداخت (مثل
    140520260315135806) از صفحه استخراج شود.
  - شناسه در گوگل‌شیت ذخیره شود (اسپردشیت «BotData»، ورک‌شیت «شناسه پرداخت»).
  - نتیجه فقط برای مدیر (ADMIN_ID) ارسال شود — به کاربر هیچ پیامی ارسال نمی‌شود.

⭐ v1.3:
  - علاوه بر گوگل‌شیت، شناسه پرداخت + «هزینه سامانه» روی پروندهٔ پنل ادمین
    (فیلدهای paymentId / systemCost) ثبت می‌شود تا در بخش «آماده ارسال»
    نمایش داده شود و مبنای محاسبه «سود» باشد.
  - چون استخراج «قبل از» ثبت نهایی پرونده در پنل رخ می‌دهد، سینک در
    پس‌زمینه با چند تلاشِ تاخیری (۰/۴۵/۱۵۰/۴۲۰ ثانیه) انجام می‌شود و
    هرگز فلوی اصلی ربات را نمی‌شکند.

نحوه استفاده در سناریوها (بلافاصله بعد از محاسبه هزینه و «قبل از» کلیک
بازگشت به فهرست، چون صفحه هنوز در بخش هزینه است):

    from payment_id_capture import capture_and_report_payment_ids
    await capture_and_report_payment_ids(
        sana_page, bot, user_id,
        service_name="لایحه",
        tracking_code=lavayeh_bill_no or tracking_code,
        amount=court_total,
        exclude_values=[tracking_code, lavayeh_bill_no],
        log_prefix="LAVAYEH")

نکته مهم: شناسه پرداخت یک عدد ۱۸ رقمی است؛ در گوگل‌شیت اگر به‌صورت عدد
ثبت شود دقتش از بین می‌رود (float64). برای همین با value_input_option=RAW
و به‌صورت رشته ثبت می‌شود.
"""
import asyncio
import datetime
import logging

import aiohttp
import gspread
from google.oauth2.service_account import Credentials

from config import ADMIN_ID, ADMIN_API_BASE

# ────────────────────────── سینک به پنل ادمین (v1.3) ──────────────────────────
# نگاشت «نام بخش» فارسی (که سناریوها پاس می‌دهند) به serviceType پنل
SERVICE_TYPE_MAP = {
    "دادخواست چک": "CHECK",
    "چک": "CHECK",
    "لایحه": "LAVAYEH",
    "اظهارنامه": "EZHHARNAMEH",
    "اعلام وکالت": "EALAM_VAKALAHT",
    "تجدیدنظر": "TAJDID_NAZAR",
}

# تاخیرهای تلاش برای یافتن/به‌روزرسانی پرونده در پنل (ثانیه).
# شناسه پرداخت «قبل از» ثبت نهایی پرونده در پنل استخراج می‌شود (upsert پرونده
# کمی بعد در send_lavayeh_result انجام می‌شود)؛ برای همین چند تلاش تاخیری داریم.
_PANEL_SYNC_DELAYS = (0, 45, 150, 420)


def _resolve_service_type(service_name: str) -> str | None:
    """تبدیل نام فارسی بخش به serviceType پنل (اگر شناخته نشد None)."""
    if not service_name:
        return None
    name = str(service_name).strip()
    if name in SERVICE_TYPE_MAP:
        return SERVICE_TYPE_MAP[name]
    for key, val in SERVICE_TYPE_MAP.items():
        if key in name or name in key:
            return val
    return None


async def _find_panel_case(service_type: str, bale_user_id, tracking_code: str):
    """
    یافتن پروندهٔ مربوطه در پنل برای ثبت شناسه پرداخت.
    اول جستجو با کد رهگیری؛ اگر پیدا نشد با آیدی کاربر (آخرین پروندهٔ همان سرویس).
    """
    url = f"{ADMIN_API_BASE}/admin/cases"
    search_value = str(tracking_code).strip() if tracking_code else str(bale_user_id)
    params = {"search": search_value, "serviceType": service_type, "limit": "50"}

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception as e:
        logging.debug(f"[PAY-ID] خطا در جستجوی پرونده در پنل: {e}")
        return None

    cases = data.get("cases") or []
    uid = str(bale_user_id)
    same_user = [c for c in cases if str(c.get("baleUserId")) == uid]
    if not same_user:
        return None

    # اولویت ۱: تطابق دقیق کد رهگیری
    if tracking_code:
        tc = str(tracking_code).strip()
        for c in same_user:
            if c.get("trackingCode") == tc:
                return c
        # کد رهگیری مرکب اعلام وکالت: "X | کد لایحه: Y"
        for c in same_user:
            if c.get("trackingCode") and tc in str(c.get("trackingCode")):
                return c

    # اولویت ۲: جدیدترین پروندهٔ همین سرویس
    try:
        same_user.sort(key=lambda c: c.get("createdAt") or "", reverse=True)
    except Exception:
        pass
    return same_user[0]


async def _update_panel_case(case_id: str, payment_id: str, system_cost) -> bool:
    """به‌روزرسانی paymentId/systemCost روی پروندهٔ موجود در پنل."""
    url = f"{ADMIN_API_BASE}/admin/cases"
    payload = {"id": case_id, "paymentId": str(payment_id)}
    if isinstance(system_cost, (int, float)) and system_cost:
        payload["systemCost"] = int(system_cost)

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.put(url, json=payload) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                logging.warning(
                    f"[PAY-ID] پنل پرونده را نپذیرفت (HTTP {resp.status}): {body[:200]}")
                return False
    except Exception as e:
        logging.debug(f"[PAY-ID] خطا در به‌روزرسانی پرونده در پنل: {e}")
        return False


async def _sync_payment_to_panel_task(
    service_type: str, bale_user_id, tracking_code: str,
    payment_id: str, system_cost):
    """
    تسک پس‌زمینه: با چند تلاشِ تاخیری، پرونده را در پنل پیدا و
    paymentId + systemCost را ثبت می‌کند. هرگز exception نمی‌دهد.
    """
    for i, delay in enumerate(_PANEL_SYNC_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        try:
            case = await _find_panel_case(service_type, bale_user_id, tracking_code)
            if not case:
                logging.info(
                    f"[PAY-ID] تلاش {i + 1}/{len(_PANEL_SYNC_DELAYS)}: پرونده هنوز در پنل "
                    f"ایجاد نشده (type={service_type} user={bale_user_id})")
                continue
            ok = await _update_panel_case(case["id"], payment_id, system_cost)
            if ok:
                logging.info(
                    f"[PAY-ID] ✅ شناسه پرداخت {payment_id} روی پروندهٔ پنل "
                    f"ثبت شد (id={case['id']} type={service_type})")
                return
        except Exception as e:
            logging.warning(f"[PAY-ID] خطا در سینک به پنل (تلاش {i + 1}): {e}")

    logging.warning(
        f"[PAY-ID] ⚠️ شناسه پرداخت {payment_id} در پنل ثبت نشد "
        f"(پروندهٔ type={service_type} user={bale_user_id} پیدا نشد) — "
        f"در گوگل‌شیت ذخیره شده است.")


def _schedule_panel_sync(
    service_type: str, bale_user_id, tracking_code: str,
    payment_id: str, system_cost):
    """زمان‌بندی غیرمسدودکنندهٔ سینک شناسه پرداخت به پنل."""
    if not service_type:
        return
    try:
        task = asyncio.get_event_loop().create_task(
            _sync_payment_to_panel_task(
                service_type, bale_user_id, tracking_code, payment_id, system_cost))
        # نگه‌داشتن مرجع تسک تا garbage-collect نشود
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
    except Exception as e:
        logging.warning(f"[PAY-ID] زمان‌بندی سینک پنل ناموفق: {e}")


_BACKGROUND_TASKS = set()


# ────────────────────────── تنظیمات گوگل‌شیت ──────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = "BotData"
WORKSHEET_NAME = "شناسه پرداخت"
HEADER_ROW = [
    "تاریخ و ساعت",
    "بخش ربات",
    "آیدی کاربر",
    "کد رهگیری / پرونده",
    "شناسه پرداخت",
    "مبلغ هزینه (ریال)",
]

_gc = None
_gc_tried = False


def _get_client():
    """اتصال تنبل به گوگل‌شیت (همان google-credentials.json که sheets.py استفاده می‌کند).
    در صورت شکست، در تلاش بعدی دوباره تلاش می‌کند (خطای موقت شبکه)."""
    global _gc, _gc_tried
    if _gc:
        return _gc
    _gc_tried = True
    try:
        creds = Credentials.from_service_account_file(
            "google-credentials.json", scopes=SCOPES)
        _gc = gspread.authorize(creds)
        logging.info("✅ [PAY-ID] Google Sheets connected (payment_id_capture)")
    except Exception as e:
        logging.warning(f"⚠️ [PAY-ID] اتصال گوگل‌شیت ناموفق بود: {e}")
        _gc = None
    return _gc


def _get_or_create_worksheet(gc):
    """ورک‌شیت «شناسه پرداخت» را در اسپردشیت BotData برمی‌گرداند؛ اگر نبود با هدر می‌سازد."""
    sh = gc.open(SPREADSHEET_NAME)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except Exception:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=500, cols=len(HEADER_ROW))
        ws.append_row(HEADER_ROW, value_input_option="RAW")
        logging.info(f"✅ [PAY-ID] ورک‌شیت «{WORKSHEET_NAME}» ساخته شد")
    return ws


async def save_payment_id_to_sheet(
    service_name: str,
    user_id,
    tracking_code: str,
    payment_id: str,
    amount) -> bool:
    """ثبت یک ردیف شناسه پرداخت در گوگل‌شیت. True یعنی موفق."""
    def _append():
        gc = _get_client()
        if not gc:
            return False
        ws = _get_or_create_worksheet(gc)
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            service_name,
            str(user_id),
            str(tracking_code or ""),
            str(payment_id),  # RAW — دقیقاً به‌صورت متن ذخیره می‌شود
            str(amount if amount is not None else ""),
        ]
        ws.append_row(row, value_input_option="RAW")
        return True

    try:
        return await asyncio.to_thread(_append)
    except Exception as e:
        logging.error(f"❌ [PAY-ID] خطا در ثبت شناسه پرداخت در گوگل‌شیت: {e}")
        return False


# ────────────────────────── استخراج از صفحه ──────────────────────────
# جاوااسکریپت استخراج شناسه پرداخت از صفحه بخش هزینه سامانه.
# دو روش:
#   ۱) لیبل‌محور: سلولی که متن «شناسه پرداخت» دارد → مقدار عددی سلول‌های
#      مجاور (همان ردیف یا ردیف بعدی).
#   ۲) الگومحور: هر td که متن آن عدد خالص ۱۶ تا ۲۰ رقمی با پیشوند «14»
#      (سال جلالی) باشد — مثل 140520260315135806. سلول‌های کلاس
#      ng-binding / padding-2 (مطابق HTML نمونه کارفرما) اولویت دارند.
_JS_EXTRACT_PAYMENT_IDS = r'''(excludeList) => {
    const excludes = (excludeList || []).map(v => String(v || '').trim()).filter(v => v.length > 3);
    const isExcluded = (v) => excludes.indexOf(v) !== -1;
    const digitRe = /^[0-9]+$/;
    const payRe = /^14[0-9]{14,18}$/;   // 16 تا 20 رقم، شروع با 14xx (سال جلالی)
    const visible = (el) => !!(el.offsetParent || el.getClientRects().length);

    const labeled = [];
    const pattern = [];

    // ── روش ۱: لیبل «شناسه پرداخت» ──
    const cells = Array.from(document.querySelectorAll('td, th'));
    for (const cell of cells) {
        const txt = (cell.innerText || '').trim();
        if (!txt || txt.length > 60) continue;
        if (!(txt.includes('شناسه پرداخت') || txt.includes('شناسه پرداخت‌') ||
              txt.includes('شناسه‌ی پرداخت') || txt.replace(/\u200c/g, '').includes('شناسه پرداخت'))) continue;

        // سلول‌های همان ردیف
        const row = cell.closest('tr');
        if (row) {
            const tds = Array.from(row.querySelectorAll('td'));
            for (const td of tds) {
                const v = (td.innerText || '').trim().replace(/\u200c/g, '').trim();
                if (td === cell) continue;
                if (digitRe.test(v) && v.length >= 10 && v.length <= 25 && !isExcluded(v)) labeled.push(v);
            }
        }
        // ردیف بعدی (چیدمان لیبل بالا / مقدار پایین)
        if (row && row.nextElementSibling) {
            const nextTds = Array.from(row.nextElementSibling.querySelectorAll('td'));
            for (const td of nextTds) {
                const v = (td.innerText || '').trim();
                if (digitRe.test(v) && v.length >= 10 && v.length <= 25 && !isExcluded(v)) labeled.push(v);
            }
        }
        // سلول بلافاصله بعد از لیبل (حتی اگر tr نباشد)
        let sib = cell.nextElementSibling;
        for (let i = 0; sib && i < 3; i++, sib = sib.nextElementSibling) {
            const v = (sib.innerText || '').trim();
            if (digitRe.test(v) && v.length >= 10 && v.length <= 25 && !isExcluded(v)) labeled.push(v);
        }
    }

    // ── روش ۲: الگوی عددی شناسه پرداخت ──
    const tds = Array.from(document.querySelectorAll('td'));
    // اول tdهایی با کلاس مطابق نمونه HTML سامانه (ng-binding / padding-2)
    const prioritized = tds.filter(td => /ng-binding/.test(td.className) || /padding-2/.test(td.className));
    const rest = tds.filter(td => !prioritized.includes(td));
    for (const td of prioritized.concat(rest)) {
        if (!visible(td)) continue;
        const v = (td.innerText || '').trim().replace(/[\s\u200c]/g, '');
        if (payRe.test(v) && !isExcluded(v)) pattern.push(v);
    }

    const uniq = (arr) => Array.from(new Set(arr));
    return { labeled: uniq(labeled), pattern: uniq(pattern) };
}'''


async def extract_payment_ids(page, exclude_values=None, attempts: int = 3, wait_sec: float = 4.0):
    """
    استخراج شناسه‌های پرداخت از صفحه بخش هزینه.
    چند بار تلاش می‌کند (جدول پرداخت‌ها ممکن است با تاخیر Angular رندر شود).
    خروجی: لیست شناسه‌های یکتا (لیبل‌محور اول، بعد الگومحور).
    """
    excludes = []
    for v in (exclude_values or []):
        if v:
            excludes.append(str(v).strip())

    collected = []
    seen = set()
    for attempt in range(max(1, attempts)):
        try:
            data = await page.evaluate(_JS_EXTRACT_PAYMENT_IDS, excludes)
        except Exception as e:
            logging.warning(f"⚠️ [PAY-ID] خطا در اجرای اسکریپت استخراج (تلاش {attempt + 1}): {e}")
            data = None

        if data:
            # اول لیبل‌محور، بعد الگومحور
            for pid in list(data.get("labeled") or []) + list(data.get("pattern") or []):
                pid = str(pid).strip()
                if pid and pid not in seen:
                    seen.add(pid)
                    collected.append(pid)

        if collected:
            return collected

        if attempt < attempts - 1:
            await asyncio.sleep(wait_sec)

    return collected


async def capture_and_report_payment_ids(
    page,
    bot,
    user_id,
    service_name: str,
    tracking_code: str = "",
    amount=None,
    exclude_values=None,
    log_prefix: str = "PAY-ID"):
    """
    تابع اصلی برای صدا زدن از سناریوها:
      ۱. شناسه پرداخت را از صفحه بخش هزینه استخراج می‌کند.
      ۲. هر شناسه را در گوگل‌شیت (ورک‌شیت «شناسه پرداخت») ذخیره می‌کند.
      ۳. یک پیام خلاصه «فقط» برای مدیر (ADMIN_ID) می‌فرستد.
      ۴. اگر شناسه‌ای پیدا نشد، فقط به مدیر هشدار می‌دهد (کاربر چیزی نمی‌بیند).
    هیچ‌وقت exception نمی‌دهد تا فلوی اصلی ربات مختل نشود.
    """
    try:
        excludes = list(exclude_values or [])
        if tracking_code:
            excludes.append(tracking_code)

        payment_ids = await extract_payment_ids(page, exclude_values=excludes)
        logging.info(
            f"[{log_prefix}] شناسه‌های پرداخت یافت‌شده: {payment_ids} "
            f"(بخش={service_name}, user={user_id})")

        if not payment_ids:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [{log_prefix}] شناسه پرداخت در بخش هزینه پیدا نشد.\n"
                    f"📌 بخش: {service_name}\n"
                    f"👤 کاربر: {user_id}\n"
                    f"🧾 کد رهگیری: {tracking_code or '—'}"
                )
            except Exception as send_err:
                logging.error(f"[{log_prefix}] خطا در ارسال هشدار به مدیر: {send_err}")
            return []

        # ── ثبت در گوگل‌شیت ──
        saved = 0
        for pid in payment_ids:
            ok = await save_payment_id_to_sheet(
                service_name=service_name,
                user_id=user_id,
                tracking_code=tracking_code,
                payment_id=pid,
                amount=amount,
            )
            if ok:
                saved += 1

        # ── ⭐ v1.3: سینک به پنل ادمین (paymentId + systemCost روی پرونده) ──
        # غیرمسدودکننده؛ در پس‌زمینه با چند تلاشِ تاخیری انجام می‌شود.
        service_type = _resolve_service_type(service_name)
        if service_type:
            _schedule_panel_sync(
                service_type=service_type,
                bale_user_id=user_id,
                tracking_code=tracking_code or "",
                payment_id=payment_ids[0],
                system_cost=amount,
            )

        amount_txt = f"{amount:,} ریال" if isinstance(amount, (int, float)) and amount else "—"
        sheet_txt = "✅ در گوگل‌شیت ذخیره شد" if saved == len(payment_ids) else f"⚠️ {saved}/{len(payment_ids)} ردیف ذخیره شد"

        # ── پیام فقط برای مدیر ──
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🆔 شناسه پرداخت — بخش هزینه\n\n"
                f"📌 بخش: {service_name}\n"
                f"👤 کاربر: {user_id}\n"
                f"🧾 کد رهگیری: {tracking_code or '—'}\n"
                f"💰 هزینه سامانه: {amount_txt}\n\n"
                f"🔖 شناسه پرداخت: {payment_ids[0]}"
                + (f"\n🔖 شناسه‌های دیگر: {', '.join(payment_ids[1:])}" if len(payment_ids) > 1 else "")
                + f"\n\n🗂 {sheet_txt}"
            )
        except Exception as send_err:
            logging.error(f"[{log_prefix}] خطا در ارسال پیام به مدیر: {send_err}")

        return payment_ids

    except Exception as e:
        # خطای این ماژول هرگز نباید فلوی اصلی ربات را بشکند
        logging.error(f"[{log_prefix}] خطای غیرمنتظره در capture_and_report_payment_ids: {e}", exc_info=True)
        return []
