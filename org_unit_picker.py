"""
org_unit_picker.py — انتخاب «واحد زیر مجموعه شخص حقوقی» (تعریف‌شده در سامانه ثنا)
══════════════════════════════════════════════════════════════════════════════

⭐ اصلاحیهٔ کارفرما (۱۴۰۵/۰۷): در تمام بخش‌های ربات، وقتی شناسه ملی شخص حقوقی
استعلام شد و فیلد «واحد زیر مجموعه شخص حقوقی « تعریف شده در سامانه ثنا »»
(#txtOrganizationChartTitle / #txtOrganizationChartCode) در فرم ظاهر شد:

  ۱. دکمهٔ «انتخاب» (data-target="#organizationChartModal") زده می‌شود تا
     درخت واحدها نمایش داده شود.
  ۲. همهٔ واحدها با دکمهٔ شیشه‌ای برای کاربر ارسال می‌شوند تا *فقط یک مورد*
     را انتخاب کند. واحدهایی که علامت «+» دارند (زیرمجموعه دارند) با «➕»
     مشخص می‌شوند؛ اگر کاربر آن‌ها را انتخاب کرد، زیرمجموعه‌شان در فهرستی
     جداگانه نمایش داده می‌شود (و اگر خودِ واحد هم قابل انتخاب بود، گزینهٔ
     انتخاب خودش هم داده می‌شود).
  ۳. ربات حداکثر ۶۰ دقیقه منتظر انتخاب کاربر می‌ماند و سپس ادامهٔ ثبت را
     انجام می‌دهد. پس از ۶۰ دقیقه بدون انتخاب، ثبت با خطای قطعی همان بخش
     متوقف می‌شود.
  ۴. برای اینکه کار سایر کاربران معطل نماند، تب فعلی (که فرم نیمه‌کارهٔ همین
     کاربر در آن است) کنار گذاشته می‌شود و یک تب جدید جای sana_page را
     می‌گیرد؛ browser_worker تسک‌های بعدی را در تب جدید ادامه می‌دهد و این
     تسک در تب خودش منتظر پاسخ کاربر می‌ماند (run_detachable).

انتخاب کاربر برای هر (کاربر، شناسه ملی شرکت) در حافظه نگه داشته می‌شود تا اگر
همان تسک به‌خاطر خطای گذرا از نو تلاش شد، دوباره از کاربر پرسیده نشود.
"""

import asyncio
import contextvars
import logging
import secrets
import time

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import runtime_state
from config import ADMIN_ID

logger = logging.getLogger(__name__)

WAIT_MINUTES = 60
PAGE_SIZE = 20
_TITLE_MAX = 60
OFFICES_URL = "https://sakha2.adliran.ir/Offices/Index"

org_unit_router = Router()

# sid → جلسهٔ انتخاب (کاربر، فهرست جاری، future انتظار)
_sessions: dict = {}

# (user_id, شناسه ملی شرکت) → مسیر عنوان‌های انتخاب‌شده
_choice_cache: dict = {}
_CHOICE_CACHE_TTL = 6 * 3600

# تب‌هایی که تسکِ منتظرِ انتخاب واحد در آن‌ها کار می‌کند (نباید بسته شوند)
_parked_pages: set = set()

# (Event, holder) تسک اصلیِ browser_worker — برای آزاد کردن حلقهٔ اصلی
_detach_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "org_unit_detach_ctx", default=None)


# ════════════════════════════════════════════════════════════════════════════
# ۱) اجرای تسک اصلی به‌صورت «قابل جداشدن» از browser_worker
# ════════════════════════════════════════════════════════════════════════════

def is_parked_page(page) -> bool:
    return page is not None and page in _parked_pages


async def _release_pages(holder: dict):
    for p in holder.get("pages", []):
        _parked_pages.discard(p)
        if p is runtime_state.sana_page:
            continue
        try:
            if not p.is_closed():
                await p.close()
            logger.info("[ORG-UNIT] تب کنارگذاشته‌شدهٔ تسک بسته شد")
        except Exception:
            pass
    holder["pages"] = []


async def run_detachable(coro):
    """اجرای تسک اصلی (process_task) — رفتار عادی دقیقاً مثل await مستقیم است
    (نتیجه/خطا به فراخوان برمی‌گردد)، مگر اینکه تسک با release_main_worker
    اعلام کند منتظر کاربر است؛ در آن صورت این تابع بلافاصله برمی‌گردد تا
    browser_worker تسک بعدی را (در تب جدید) شروع کند و تسک فعلی در پس‌زمینه
    ادامه می‌یابد."""
    ev = asyncio.Event()
    holder = {"pages": []}

    async def _runner():
        _detach_ctx.set((ev, holder))
        return await coro

    task = asyncio.create_task(_runner())
    waiter = asyncio.create_task(ev.wait())
    try:
        done, _ = await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        task.cancel()
        waiter.cancel()
        raise

    if task in done:
        waiter.cancel()
        if holder["pages"]:
            await _release_pages(holder)
        return task.result()

    logger.info("[ORG-UNIT] تسک منتظر انتخاب کاربر است — حلقهٔ اصلی آزاد شد")

    def _on_done(t: asyncio.Task):
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            exc = None
        if exc is not None:
            logger.error(f"[ORG-UNIT] خطا در ادامهٔ تسک جداشده: {exc!r}", exc_info=exc)
            bot = holder.get("bot")
            if bot is not None:
                asyncio.create_task(_notify_admin(
                    bot, f"🚨 [ORG-UNIT] خطا در ادامهٔ تسک پس از انتخاب واحد: {str(exc)[:300]}"))
        asyncio.create_task(_release_pages(holder))

    task.add_done_callback(_on_done)
    return None


async def _notify_admin(bot: Bot, text: str):
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception:
        pass


async def release_main_worker(page, bot: Bot) -> bool:
    """تب فعلی را برای همین تسک نگه می‌دارد، تب جدیدی به‌جای sana_page باز
    می‌کند و حلقهٔ اصلی را آزاد می‌کند. خروجی True یعنی آزاد شد (یا قبلاً
    آزاد شده بود)."""
    ctx = _detach_ctx.get()
    if ctx is None:
        return False
    ev, holder = ctx
    if ev.is_set():
        return True
    if page is not runtime_state.sana_page:
        # تسک روی تب دیگری کار می‌کند؛ sana_page آزاد است
        holder["bot"] = bot
        ev.set()
        return True
    browser_context = runtime_state.browser_context
    if browser_context is None:
        return False
    try:
        new_page = await browser_context.new_page()
    except Exception as e:
        logger.warning(f"[ORG-UNIT] باز کردن تب جدید ناموفق — انتظار در همین تب: {e}")
        return False
    try:
        from scenarios import _attach_debug_listeners
        await _attach_debug_listeners(new_page)
    except Exception:
        pass
    try:
        await new_page.goto(OFFICES_URL, timeout=60000)
    except Exception as e:
        logger.warning(f"[ORG-UNIT] بارگذاری صفحهٔ اصلی در تب جدید: {e}")
    _parked_pages.add(page)
    holder["pages"].append(page)
    holder["bot"] = bot
    runtime_state.sana_page = new_page
    ev.set()
    logger.info("[ORG-UNIT] تب جدید جایگزین sana_page شد؛ تسک فعلی در تب قبلی منتظر کاربر است")
    return True


# ════════════════════════════════════════════════════════════════════════════
# ۲) کار با فرم/درخت سامانه
# ════════════════════════════════════════════════════════════════════════════

_JS_FIELD_STATE = '''() => {
    const t = document.querySelector('#txtOrganizationChartTitle');
    if (!t) return null;
    const c = document.querySelector('#txtOrganizationChartCode');
    return {visible: t.offsetParent !== null, title: (t.value || '').trim(),
            code: c ? (c.value || '').trim() : ''};
}'''

# پیدا کردن ul ریشه / li در مسیر داده‌شده (مسیر = فهرست ایندکس‌ها)
_JS_TREE_HELPERS = '''
    const kids = (el, tag) => Array.from(el ? el.children : []).filter(e => e.tagName === tag);
    const rootUl = () => {
        const modal = document.querySelector('#organizationChartModal') || document;
        return modal.querySelector('[jud-tree] > ul[jud-tree-nodes]')
            || modal.querySelector('.tree-container ul[jud-tree-nodes]');
    };
    const liAt = (path) => {
        let ul = rootUl();
        let li = null;
        for (const idx of path) {
            li = kids(ul, 'LI')[idx];
            if (!li) return null;
            ul = kids(li, 'UL')[0] || null;
        }
        return li;
    };
    const handleOf = (li) => kids(li, 'DIV').find(d => d.hasAttribute('ui-tree-handle')) || li;
'''

_JS_LIST = '''(path) => {''' + _JS_TREE_HELPERS + '''
    let ul;
    if (path.length === 0) { ul = rootUl(); }
    else { const li = liAt(path); ul = li ? (kids(li, 'UL')[0] || null) : null; }
    if (!ul) return null;
    return kids(ul, 'LI').map(li => {
        const h = handleOf(li);
        const radio = h.querySelector('input[type="radio"]');
        const plus = h.querySelector('span.fa-plus, span.fa-minus, span[id^="icon_"]');
        const lbl = h.querySelector('label.unit-title') || h.querySelector('label');
        const sub = kids(li, 'UL')[0];
        return {
            title: (lbl ? lbl.innerText : '').replace(/\\s+/g, ' ').trim(),
            selectable: !!radio,
            expandable: !!plus || (sub ? kids(sub, 'LI').length > 0 : false),
        };
    });
}'''

_JS_CHILD_COUNT = '''(path) => {''' + _JS_TREE_HELPERS + '''
    const li = liAt(path);
    if (!li) return -1;
    const sub = kids(li, 'UL')[0];
    return sub ? kids(sub, 'LI').length : 0;
}'''

_JS_EXPAND = '''(path) => {''' + _JS_TREE_HELPERS + '''
    const li = liAt(path);
    if (!li) return false;
    const h = handleOf(li);
    const plus = h.querySelector('span.fa-plus, span.fa-minus, span[id^="icon_"]')
        || h.querySelector('[ng-click*="getOrganizationChart"]');
    if (!plus) return false;
    plus.click();
    return true;
}'''

_JS_SELECT = '''(path) => {''' + _JS_TREE_HELPERS + '''
    const li = liAt(path);
    if (!li) return false;
    const radio = handleOf(li).querySelector('input[type="radio"]');
    if (!radio) return false;
    radio.click();
    return true;
}'''

_JS_OPEN_MODAL = '''() => {
    const btns = Array.from(document.querySelectorAll('button[data-target="#organizationChartModal"]'));
    const btn = btns.find(b => !b.disabled && b.offsetParent !== null) || btns.find(b => !b.disabled);
    if (!btn) return false;
    btn.click();
    return true;
}'''

_JS_MODAL_OPEN = '''() => {
    const m = document.querySelector('#organizationChartModal');
    if (!m) return false;
    const st = window.getComputedStyle(m);
    return st.display !== 'none' && st.visibility !== 'hidden';
}'''

_JS_CLOSE_MODAL = '''() => {
    const m = document.querySelector('#organizationChartModal');
    if (!m) return 'none';
    const st = window.getComputedStyle(m);
    if (st.display === 'none') return 'closed';
    const btns = Array.from(m.querySelectorAll('button, a.btn')).filter(b => b.offsetParent !== null && !b.disabled);
    const txt = b => (b.innerText || b.getAttribute('tooltip') || '').replace(/\\s+/g, ' ').trim();
    const ok = btns.find(b => /تایید|تأیید|ثبت|انتخاب/.test(txt(b)));
    if (ok) { ok.click(); return 'ok'; }
    const dismiss = btns.find(b => b.getAttribute('data-dismiss') === 'modal') || btns.find(b => /بستن|انصراف/.test(txt(b)));
    if (dismiss) { dismiss.click(); return 'dismiss'; }
    try { if (window.jQuery) { window.jQuery(m).modal('hide'); return 'jquery'; } } catch (e) {}
    return 'stuck';
}'''


async def _field_state(page):
    try:
        return await page.evaluate(_JS_FIELD_STATE)
    except Exception:
        return None


async def _poll(fn, timeout_s: float, interval_s: float = 0.5):
    end = time.monotonic() + timeout_s
    while True:
        try:
            res = await fn()
        except Exception:
            res = None
        if res:
            return res
        if time.monotonic() >= end:
            return res
        await asyncio.sleep(interval_s)


async def _open_modal(page) -> bool:
    if not await page.evaluate(_JS_MODAL_OPEN):
        if not await page.evaluate(_JS_OPEN_MODAL):
            return False
    ok = await _poll(lambda: page.evaluate(_JS_MODAL_OPEN), 15)
    if not ok:
        return False
    items = await _poll(lambda: page.evaluate(_JS_LIST, []), 30)
    return bool(items)


async def _list(page, path: list) -> list:
    items = await page.evaluate(_JS_LIST, path)
    return items or []


async def _expand(page, path: list) -> list:
    count = await page.evaluate(_JS_CHILD_COUNT, path)
    if count is not None and count > 0:
        return await _list(page, path)
    await page.evaluate(_JS_EXPAND, path)
    await _poll(lambda: _child_count_pos(page, path), 30)
    return await _list(page, path)


async def _child_count_pos(page, path):
    c = await page.evaluate(_JS_CHILD_COUNT, path)
    return c if (c or 0) > 0 else None


async def _select(page, path: list) -> dict | None:
    if not await page.evaluate(_JS_SELECT, path):
        return None
    await asyncio.sleep(1)
    await _poll(lambda: _code_filled(page), 8)
    for _ in range(3):
        res = await page.evaluate(_JS_CLOSE_MODAL)
        if res in ("closed", "none"):
            break
        await asyncio.sleep(1.5)
    st = await _field_state(page)
    if st and (st.get("title") or st.get("code")):
        return st
    return None


async def _code_filled(page):
    st = await _field_state(page)
    return st if st and (st.get("code") or st.get("title")) else None


async def _select_by_titles(page, titles: list) -> dict | None:
    """انتخاب خودکار با مسیر عنوان‌ها (انتخاب قبلی همین کاربر)."""
    path: list = []
    for depth, title in enumerate(titles):
        items = await (_list(page, path) if depth == 0 else _expand(page, path))
        idx = next((i for i, it in enumerate(items) if it.get("title") == title), None)
        if idx is None:
            return None
        path = path + [idx]
    return await _select(page, path)


# ════════════════════════════════════════════════════════════════════════════
# ۳) گفتگو با کاربر
# ════════════════════════════════════════════════════════════════════════════

def _short(title: str) -> str:
    title = (title or "—").strip()
    return title if len(title) <= _TITLE_MAX else title[:_TITLE_MAX - 1] + "…"


def _render(sess: dict):
    items = sess["items"]
    page_no = sess.get("page_no", 0)
    start = page_no * PAGE_SIZE
    chunk = items[start:start + PAGE_SIZE]
    sid = sess["sid"]
    rows = []
    if sess.get("self_selectable"):
        rows.append([InlineKeyboardButton(
            text=f"✅ انتخاب خودِ «{_short(sess['crumbs'][-1])}»",
            callback_data=f"orgu:{sid}:self")])
    for i, it in enumerate(chunk, start=start):
        icon = "➕" if it.get("expandable") else "🔘"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {_short(it.get('title'))}",
            callback_data=f"orgu:{sid}:i{i}")])
    nav = []
    if page_no > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"orgu:{sid}:p{page_no - 1}"))
    if start + PAGE_SIZE < len(items):
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"orgu:{sid}:p{page_no + 1}"))
    if nav:
        rows.append(nav)
    if sess.get("crumbs"):
        rows.append([InlineKeyboardButton(text="🔙 بازگشت به فهرست قبلی", callback_data=f"orgu:{sid}:back")])

    lines = [
        "🏢 *انتخاب واحد زیر مجموعه شخص حقوقی*",
        "",
        f"برای شخص حقوقی با شناسه ملی `{sess.get('company_id') or '—'}` در سامانه ثنا "
        "«واحد زیر مجموعه» تعریف شده است و ثبت درخواست شما تا انتخاب این مورد "
        "متوقف مانده است.",
        "",
        "لطفاً *فقط یک مورد* را انتخاب و تایید کنید.",
        "➕ = این واحد زیرمجموعه دارد؛ با انتخاب آن، فهرست زیرمجموعه‌اش نمایش داده می‌شود.",
    ]
    if sess.get("crumbs"):
        lines += ["", "📂 " + " ← ".join(_short(c) for c in sess["crumbs"])]
    if len(items) > PAGE_SIZE:
        total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
        lines += ["", f"صفحه {page_no + 1} از {total_pages}"]
    lines += ["", f"⏰ مهلت انتخاب: *{WAIT_MINUTES} دقیقه*"]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _show(bot: Bot, sess: dict):
    text, kb = _render(sess)
    msg_id = sess.get("message_id")
    if msg_id:
        try:
            await bot.edit_message_text(text, chat_id=sess["user_id"], message_id=msg_id,
                                        reply_markup=kb, parse_mode="Markdown")
            return
        except Exception:
            pass
    msg = await bot.send_message(sess["user_id"], text, reply_markup=kb, parse_mode="Markdown")
    sess["message_id"] = msg.message_id


@org_unit_router.callback_query(F.data.startswith("orgu:"))
async def org_unit_callback(callback: CallbackQuery, bot: Bot):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, sid, action = parts
    sess = _sessions.get(sid)
    if not sess or sess["future"].done():
        await callback.answer("⚠️ این فهرست منقضی شده است.")
        return
    if callback.from_user.id != sess["user_id"]:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    if action.startswith("p"):
        try:
            sess["page_no"] = max(0, int(action[1:]))
        except ValueError:
            pass
        await callback.answer()
        await _show(bot, sess)
        return

    if sess.get("busy"):
        await callback.answer("⏳ در حال بارگذاری...")
        return

    if action == "self":
        choice = ("self",)
    elif action == "back":
        choice = ("back",)
    elif action.startswith("i"):
        try:
            idx = int(action[1:])
        except ValueError:
            await callback.answer()
            return
        if idx >= len(sess["items"]):
            await callback.answer()
            return
        choice = ("item", idx)
    else:
        await callback.answer()
        return
    sess["busy"] = True
    await callback.answer("⏳ لطفاً چند لحظه صبر کنید...")
    sess["future"].set_result(choice)


async def handle_if_present(page, bot: Bot, user_id: int, company_id: str = "",
                            fatal_exc=None, prefix: str = "ORG-UNIT") -> bool:
    """اگر فیلد «واحد زیر مجموعه شخص حقوقی» در فرم ظاهر شده باشد، انتخاب
    واحد را از کاربر می‌گیرد و در فرم درج می‌کند.

    خروجی: True اگر واحد انتخاب و درج شد، False اگر فیلدی وجود نداشت (یا
    از قبل پر بود). در صورت پایان مهلت ۶۰ دقیقه یا عدم امکان درج،
    fatal_exc(پیام) (خطای قطعی همان بخش) raise می‌شود.
    """
    st = await _poll(lambda: _visible_empty_field(page), 1.5)
    if not st:
        return False

    company_id = str(company_id or "")
    logger.info(f"[{prefix}] فیلد «واحد زیر مجموعه شخص حقوقی» برای {company_id} ظاهر شد")

    def _fail(msg: str):
        if fatal_exc is not None:
            return fatal_exc(msg)
        return RuntimeError(msg)

    if not await _open_modal(page):
        # یک بار دیگر
        await asyncio.sleep(3)
        if not await _open_modal(page):
            await _notify_admin(bot, f"⚠️ [{prefix}] باز کردن فهرست «واحد زیر مجموعه شخص حقوقی» "
                                     f"کاربر {user_id} (شناسه {company_id}) ناموفق بود.")
            raise _fail("امکان باز کردن فهرست «واحد زیر مجموعه شخص حقوقی» در سامانه ثنا وجود نداشت.")

    # انتخاب قبلی همین کاربر برای همین شخص حقوقی (تلاش مجدد همان تسک)
    key = (user_id, company_id)
    cached = _choice_cache.get(key)
    if cached and time.time() - cached[1] < _CHOICE_CACHE_TTL:
        res = await _select_by_titles(page, cached[0])
        if res:
            logger.info(f"[{prefix}] واحد زیر مجموعه از انتخاب قبلی کاربر درج شد: {cached[0]}")
            return True
        # انتخاب قبلی پیدا نشد — از کاربر پرسیده می‌شود
        if not await page.evaluate(_JS_MODAL_OPEN):
            await _open_modal(page)

    items = await _list(page, [])
    if not items:
        raise _fail("فهرست «واحد زیر مجموعه شخص حقوقی» در سامانه ثنا خالی بود.")

    # آزاد کردن حلقهٔ اصلی تا کار سایر کاربران در تب جدید ادامه یابد
    await release_main_worker(page, bot)

    sid = secrets.token_hex(4)
    loop = asyncio.get_running_loop()
    sess = {
        "sid": sid, "user_id": user_id, "company_id": company_id,
        "items": items, "crumbs": [], "path": [], "page_no": 0,
        "self_selectable": False, "future": loop.create_future(),
        "busy": False,
    }
    _sessions[sid] = sess
    deadline = time.monotonic() + WAIT_MINUTES * 60
    await _notify_admin(bot, f"🏢 [{prefix}] کاربر {user_id} باید «واحد زیر مجموعه شخص حقوقی» "
                             f"(شناسه {company_id}) را انتخاب کند — حداکثر {WAIT_MINUTES} دقیقه انتظار.")
    try:
        await _show(bot, sess)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            choice = await asyncio.wait_for(asyncio.shield(sess["future"]), timeout=remaining)
            sess["future"] = loop.create_future()
            sess["busy"] = True
            try:
                await _ensure_session(page, bot, user_id)
                if not await page.evaluate(_JS_MODAL_OPEN):
                    await _open_modal(page)

                if choice[0] == "back":
                    if sess["path"]:
                        sess["path"].pop()
                        sess["crumbs"].pop()
                    items = await _list(page, sess["path"]) if sess["path"] else await _list(page, [])
                    sess["self_selectable"] = _parent_selectable(sess)
                    sess.update(items=items, page_no=0)
                    await _show(bot, sess)
                    continue

                if choice[0] == "self":
                    target_path = list(sess["path"])
                    titles = list(sess["crumbs"])
                else:
                    idx = choice[1]
                    it = sess["items"][idx]
                    if it.get("expandable"):
                        new_path = sess["path"] + [idx]
                        children = await _expand(page, new_path)
                        if children:
                            sess["parents"] = sess.get("parents", []) + [it]
                            sess["path"] = new_path
                            sess["crumbs"] = sess["crumbs"] + [it.get("title", "")]
                            sess["self_selectable"] = bool(it.get("selectable"))
                            sess.update(items=children, page_no=0)
                            await _show(bot, sess)
                            continue
                        if not it.get("selectable"):
                            await bot.send_message(user_id, "⚠️ زیرمجموعهٔ این واحد بارگذاری نشد؛ لطفاً دوباره انتخاب کنید.")
                            continue
                    target_path = sess["path"] + [idx]
                    titles = sess["crumbs"] + [it.get("title", "")]

                res = await _select(page, target_path)
                if not res:
                    await bot.send_message(
                        user_id, "⚠️ درج این واحد در سامانه انجام نشد؛ لطفاً دوباره انتخاب کنید.")
                    if not await page.evaluate(_JS_MODAL_OPEN):
                        await _open_modal(page)
                    continue

                _choice_cache[key] = (titles, time.time())
                try:
                    await bot.edit_message_text(
                        f"✅ واحد «{' ← '.join(titles)}» انتخاب شد.\n\n⏳ ادامهٔ ثبت درخواست شما در حال انجام است...",
                        chat_id=user_id, message_id=sess["message_id"])
                except Exception:
                    await bot.send_message(
                        user_id, f"✅ واحد «{' ← '.join(titles)}» انتخاب شد.\n\n⏳ ادامهٔ ثبت درخواست شما در حال انجام است...")
                logger.info(f"[{prefix}] واحد زیر مجموعه انتخاب و درج شد: {titles} (code={res.get('code')})")
                return True
            finally:
                sess["busy"] = False
    except asyncio.TimeoutError:
        try:
            await bot.edit_message_text(
                f"⌛ مهلت {WAIT_MINUTES} دقیقه‌ای انتخاب «واحد زیر مجموعه شخص حقوقی» به پایان رسید.",
                chat_id=user_id, message_id=sess.get("message_id"))
        except Exception:
            pass
        await _notify_admin(bot, f"⌛ [{prefix}] کاربر {user_id} ظرف {WAIT_MINUTES} دقیقه واحد زیر "
                                 f"مجموعه شخص حقوقی (شناسه {company_id}) را انتخاب نکرد.")
        raise _fail(f"مهلت {WAIT_MINUTES} دقیقه‌ای انتخاب «واحد زیر مجموعه شخص حقوقی» به پایان رسید.")
    finally:
        _sessions.pop(sid, None)


def _parent_selectable(sess: dict) -> bool:
    parents = sess.get("parents", [])[:len(sess["path"])]
    sess["parents"] = parents
    return bool(parents and parents[-1].get("selectable"))


async def _visible_empty_field(page):
    st = await _field_state(page)
    if st and st.get("visible") and not st.get("code") and not st.get("title"):
        return st
    return None


async def _ensure_session(page, bot: Bot, user_id: int):
    """پس از انتظار طولانی، پیش از کار با صفحه نشست بررسی/تمدید شود."""
    try:
        from browser_helpers import check_and_handle_expiry
        await check_and_handle_expiry(page, bot, user_id)
    except Exception as e:
        if type(e).__name__ == "NavigationResetError":
            raise
        logger.warning(f"[ORG-UNIT] بررسی نشست: {e}")
