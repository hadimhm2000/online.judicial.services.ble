"""
guide_handlers.py — PDF «راهنمای جامع ربات» برای کاربران
══════════════════════════════════════════════════════════════════════════════

۱) ارسال خودکار: اولین /start هر کاربر جدید → PDF راهنما (guide_pdf.py)
   یک‌بار برایش ارسال می‌شود (send_welcome_guide_if_new از cmd_start صدا زده می‌شود).
۲) کاربران قدیمی: فقط با دستور مدیر و پس از تأیید او (هیچ ارسال همگانی خودکاری
   وجود ندارد).

دستورات مدیر:
  /guide          پیش‌نمایش PDF راهنما + آمار کاربران
  /guidesend      ارسال راهنما به همهٔ کاربرانی که هنوز آن را نگرفته‌اند (با تأیید)
  /guidesendall   ارسال دوباره به همهٔ کاربران (با تأیید)
  /guidestop      توقف ارسال همگانی در حال اجرا

فهرست کاربران: user_registry.py (+ کاربران سابقه‌دار پنل از /api/admin/bot-users).
ارسال با file_id انجام می‌شود تا فایل فقط یک‌بار بارگذاری شود؛ این ارسال در
«سوابق و فاکتورهای من» ثبت نمی‌شود و نظرسنجی پس از تحویل را فعال نمی‌کند.
"""
import asyncio
import json
import logging
import os

import aiohttp
from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import user_registry
from config import ADMIN_ID, BALE_API_BASE, BALE_SSL_CONTEXT, BOT_TOKEN, temp_path
from guide_pdf import GUIDE_FILENAME, build_guide_pdf

logger = logging.getLogger(__name__)

guide_router = Router()

CAPTION = ("📘 راهنمای جامع ربات خدمات قضایی آنلاین\n"
           "معرفی همهٔ امکانات ربات و نحوهٔ استفاده از آن‌ها")
SEND_INTERVAL_SECONDS = 0.5      # فاصلهٔ ارسال‌ها در ارسال همگانی
PROGRESS_EVERY = 100             # گزارش پیشرفت به مدیر هر چند ارسال

_pdf_path: str | None = None
_file_id: str | None = None
_build_lock = asyncio.Lock()
_broadcast_task: asyncio.Task | None = None


def _is_admin(m) -> bool:
    return bool(m.from_user) and m.from_user.id == ADMIN_ID


# ══════════════════════════════════════════════════════════════════
# ثبت کاربران
# ══════════════════════════════════════════════════════════════════
class RegistryMiddleware(BaseMiddleware):
    """هر کاربری که پیام بدهد یک‌بار در user_registry ثبت می‌شود."""

    async def __call__(self, handler, event, data):
        try:
            if getattr(event, "from_user", None):
                user_registry.touch(event.from_user.id)
        except Exception:
            pass
        return await handler(event, data)


async def seed_from_panel() -> int | None:
    """کاربران سابقه‌دار پنل را (بدون ارسال خودکار راهنما) به فهرست اضافه می‌کند."""
    try:
        from panel_sync import get_bot_users
        users = await get_bot_users()
        if users is None:
            return None
        added = user_registry.add_seed_users(users)
        if added:
            logger.info(f"[GUIDE] {added} کاربر قدیمی از پنل ثبت شد")
        return added
    except Exception as e:
        logger.warning(f"[GUIDE] دریافت کاربران پنل ناموفق: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# ساخت و ارسال PDF
# ══════════════════════════════════════════════════════════════════
async def _ensure_pdf() -> str | None:
    global _pdf_path
    async with _build_lock:
        if _pdf_path and os.path.exists(_pdf_path):
            return _pdf_path
        path = temp_path("bot_guide.pdf")
        ok = await asyncio.get_running_loop().run_in_executor(None, build_guide_pdf, path)
        if ok and os.path.exists(path):
            _pdf_path = path
            return path
        return None


async def _api_send_document(chat_id: int, document) -> tuple[dict | None, dict]:
    """sendDocument؛ document = file_id (str) یا bytes. خروجی: (result, پاسخ کامل)."""
    url = f"{BALE_API_BASE.rstrip('/')}/bot{BOT_TOKEN}/sendDocument"
    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat_id))
    form.add_field("caption", CAPTION)
    if isinstance(document, bytes):
        form.add_field("document", document, filename=GUIDE_FILENAME, content_type="application/pdf")
    else:
        form.add_field("document", document)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=60),
                                ssl=BALE_SSL_CONTEXT) as resp:
            body = await resp.json(content_type=None)
    return (body.get("result") if body.get("ok") else None), body


async def send_guide(chat_id: int) -> tuple[bool, dict]:
    """ارسال PDF راهنما به یک کاربر. خروجی: (موفق؟، پاسخ API آخرین تلاش)."""
    global _file_id
    body: dict = {}
    try:
        if _file_id:
            result, body = await _api_send_document(chat_id, _file_id)
            if result:
                return True, body
        path = await _ensure_pdf()
        if not path:
            return False, {"description": "ساخت PDF راهنما ناموفق بود"}
        with open(path, "rb") as f:
            data = f.read()
        result, body = await _api_send_document(chat_id, data)
        if result:
            fid = (result.get("document") or {}).get("file_id")
            if fid:
                _file_id = fid
            return True, body
        logger.warning(f"[GUIDE] ارسال راهنما به {chat_id} ناموفق: {body.get('description')}")
    except Exception as e:
        logger.warning(f"[GUIDE] خطا در ارسال راهنما به {chat_id}: {e}")
        body = {"description": str(e)}
    return False, body


async def send_welcome_guide_if_new(message: Message) -> None:
    """در /start صدا زده می‌شود: کاربر جدیدی که راهنما نگرفته، یک‌بار PDF دریافت می‌کند."""
    user_id = message.from_user.id
    try:
        if not user_registry.needs_welcome_guide(user_id):
            return
        # پیش از ارسال علامت می‌خورد تا /start پشت‌سرهم دو بار ارسال نکند
        user_registry.mark_guide_sent(user_id)
        ok, _ = await send_guide(message.chat.id)
        if not ok:
            user_registry.clear_guide_sent(user_id)
            logger.warning(f"[GUIDE] ارسال راهنمای خوش‌آمد به {user_id} ناموفق بود")
    except Exception as e:
        logger.warning(f"[GUIDE] خطا در راهنمای خوش‌آمد {user_id}: {e}")


# ══════════════════════════════════════════════════════════════════
# دستورات مدیر
# ══════════════════════════════════════════════════════════════════
def _stats_text() -> str:
    s = user_registry.stats()
    return (f"👥 کاربران ثبت‌شده: {s['total']:,}\n"
            f"   قدیمی: {s['seed']:,} | جدید: {s['live']:,}\n"
            f"📘 راهنما را دریافت کرده‌اند: {s['with_guide']:,}\n"
            f"⏳ هنوز دریافت نکرده‌اند: {s['total'] - s['with_guide']:,}")


@guide_router.message(Command("guide"), _is_admin)
async def cmd_guide(message: Message):
    await seed_from_panel()
    ok, body = await send_guide(message.chat.id)
    if not ok:
        await message.answer(f"❌ ارسال PDF راهنما ناموفق بود: {body.get('description', '')}",
                             parse_mode=None)
    await message.answer(
        "📘 پیش‌نمایش PDF راهنما (بالا)\n\n" + _stats_text() +
        "\n\nارسال به کاربرانی که هنوز نگرفته‌اند: /guidesend"
        "\nارسال دوباره به همه: /guidesendall", parse_mode=None)


async def _ask_broadcast(message: Message, everyone: bool):
    if _broadcast_task and not _broadcast_task.done():
        await message.answer("⏳ یک ارسال همگانی در حال اجراست. برای توقف: /guidestop", parse_mode=None)
        return
    panel = await seed_from_panel()
    targets = user_registry.all_user_ids() if everyone else user_registry.users_without_guide()
    targets = [u for u in targets if u != ADMIN_ID]
    note = "" if panel is not None else "\n⚠️ فهرست کاربران پنل دریافت نشد؛ فقط کاربران ثبت‌شده در ربات شمرده شده‌اند."
    if not targets:
        await message.answer("✅ کاربری برای ارسال وجود ندارد.\n\n" + _stats_text() + note, parse_mode=None)
        return
    mode = "all" if everyone else "new"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ ارسال به {len(targets):,} کاربر", callback_data=f"guide:go:{mode}")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="guide:cancel")],
    ])
    who = "همهٔ کاربران (حتی کسانی که قبلاً گرفته‌اند)" if everyone else "کاربرانی که هنوز راهنما را نگرفته‌اند"
    await message.answer(
        f"📘 ارسال PDF راهنما به {who}\n\n"
        f"تعداد گیرندگان: {len(targets):,}\n"
        f"زمان تقریبی: {max(1, round(len(targets) * (SEND_INTERVAL_SECONDS + 0.3) / 60)):,} دقیقه"
        f"{note}\n\nتأیید می‌کنید؟", reply_markup=kb, parse_mode=None)


@guide_router.message(Command("guidesend"), _is_admin)
async def cmd_guide_send(message: Message):
    await _ask_broadcast(message, everyone=False)


@guide_router.message(Command("guidesendall"), _is_admin)
async def cmd_guide_send_all(message: Message):
    await _ask_broadcast(message, everyone=True)


@guide_router.message(Command("guidestop"), _is_admin)
async def cmd_guide_stop(message: Message):
    if _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        await message.answer("⏹ درخواست توقف ارسال همگانی ثبت شد.", parse_mode=None)
    else:
        await message.answer("ارسال همگانی فعالی وجود ندارد.", parse_mode=None)


@guide_router.callback_query(F.data == "guide:cancel", _is_admin)
async def cb_guide_cancel(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ ارسال همگانی راهنما لغو شد.", parse_mode=None)


@guide_router.callback_query(F.data.startswith("guide:go:"), _is_admin)
async def cb_guide_go(callback: CallbackQuery, bot: Bot):
    global _broadcast_task
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if _broadcast_task and not _broadcast_task.done():
        await callback.message.answer("⏳ یک ارسال همگانی در حال اجراست.", parse_mode=None)
        return
    everyone = callback.data.endswith(":all")
    targets = user_registry.all_user_ids() if everyone else user_registry.users_without_guide()
    targets = [u for u in targets if u != ADMIN_ID]
    _broadcast_task = asyncio.create_task(_broadcast(bot, targets))
    await callback.message.answer(
        f"🚀 ارسال راهنما به {len(targets):,} کاربر شروع شد. گزارش پیشرفت ارسال می‌شود.\n"
        "برای توقف: /guidestop", parse_mode=None)


async def _broadcast(bot: Bot, targets: list[int]):
    sent = failed = 0
    try:
        for i, uid in enumerate(targets, 1):
            ok, body = await send_guide(uid)
            if not ok:
                retry_after = ((body.get("parameters") or {}).get("retry_after"))
                if retry_after:
                    await asyncio.sleep(min(int(retry_after), 60) + 1)
                    ok, body = await send_guide(uid)
            if ok:
                sent += 1
                user_registry.mark_guide_sent(uid, persist=False)
            else:
                failed += 1
            if i % 50 == 0:
                user_registry.save()
            if i % PROGRESS_EVERY == 0:
                await bot.send_message(
                    ADMIN_ID, f"📘 پیشرفت ارسال راهنما: {i:,} از {len(targets):,} "
                              f"(موفق {sent:,}، ناموفق {failed:,})", parse_mode=None)
            await asyncio.sleep(SEND_INTERVAL_SECONDS)
        title = "✅ ارسال همگانی راهنما تمام شد."
    except asyncio.CancelledError:
        title = "⏹ ارسال همگانی راهنما متوقف شد."
    except Exception as e:
        logger.error(f"[GUIDE] خطا در ارسال همگانی: {e}", exc_info=True)
        title = f"❌ ارسال همگانی راهنما با خطا متوقف شد: {e}"
    finally:
        user_registry.save()
    try:
        await bot.send_message(
            ADMIN_ID,
            f"{title}\n\nموفق: {sent:,}\nناموفق (ربات را مسدود/حذف کرده‌اند یا خطا): {failed:,}",
            parse_mode=None)
    except Exception as e:
        logger.warning(f"[GUIDE] گزارش پایان ارسال همگانی ناموفق: {e}")


def setup_guide(dp) -> None:
    """ثبت روتر و middleware — در bot.py قبل از روتر اصلی صدا زده شود."""
    dp.include_router(guide_router)
    dp.message.outer_middleware(RegistryMiddleware())
