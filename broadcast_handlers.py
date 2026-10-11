"""
broadcast_handlers.py — ارسال همگانی پیام مدیر به همهٔ کاربران ربات
══════════════════════════════════════════════════════════════════════════════

دستورات مدیر:
  /broadcast        شروع: مدیر یک متن، عکس، فایل، ویدیو، صدا یا موزیک (با کپشن
                    دلخواه) می‌فرستد، پیش‌نمایش و تعداد گیرندگان را می‌بیند و
                    پس از تأیید، ارسال به همهٔ کاربران در پس‌زمینه آغاز می‌شود.
  /broadcaststop    توقف ارسال همگانی در حال اجرا
  /cancel           لغو، پیش از تأیید

فهرست گیرندگان همان فهرست ارسال همگانی راهنماست: user_registry.py
(+ کاربران سابقه‌دار پنل از طریق guide_handlers.seed_from_panel).
فایل‌ها با file_id ارسال می‌شوند تا فقط یک‌بار بارگذاری شوند.
"""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import user_registry
from config import ADMIN_ID

logger = logging.getLogger(__name__)

broadcast_router = Router()

SEND_INTERVAL_SECONDS = 0.5      # فاصلهٔ ارسال‌ها (مثل ارسال همگانی راهنما)
PROGRESS_EVERY = 100             # گزارش پیشرفت به مدیر هر چند ارسال

_broadcast_task: asyncio.Task | None = None


class BroadcastStates(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirm = State()


def _is_admin(m) -> bool:
    return bool(m.from_user) and m.from_user.id == ADMIN_ID


def _running() -> bool:
    return bool(_broadcast_task and not _broadcast_task.done())


def extract_payload(message: Message) -> dict | None:
    """محتوای قابل ارسال پیام مدیر. None = نوع پشتیبانی‌نشده."""
    caption = message.caption or None
    if message.photo:
        return {"kind": "photo", "file_id": message.photo[-1].file_id, "caption": caption}
    for kind in ("document", "video", "voice", "audio"):
        media = getattr(message, kind, None)
        if media:
            return {"kind": kind, "file_id": media.file_id, "caption": caption}
    if message.text:
        return {"kind": "text", "text": message.text}
    return None


async def send_payload(bot: Bot, chat_id: int, payload: dict) -> None:
    kind = payload["kind"]
    if kind == "text":
        await bot.send_message(chat_id, payload["text"], parse_mode=None)
        return
    sender = {
        "photo": bot.send_photo,
        "document": bot.send_document,
        "video": bot.send_video,
        "voice": bot.send_voice,
        "audio": bot.send_audio,
    }[kind]
    await sender(chat_id, payload["file_id"], caption=payload.get("caption"), parse_mode=None)


async def _targets() -> tuple[list[int], bool]:
    """(گیرندگان، آیا فهرست پنل دریافت شد؟)"""
    from guide_handlers import seed_from_panel
    panel = await seed_from_panel()
    targets = [u for u in user_registry.all_user_ids() if u != ADMIN_ID]
    return targets, panel is not None


# ══════════════════════════════════════════════════════════════════
# دستورات مدیر
# ══════════════════════════════════════════════════════════════════
@broadcast_router.message(StateFilter("*"), Command("broadcast"), _is_admin)
async def cmd_broadcast(message: Message, state: FSMContext):
    if _running():
        await message.answer("⏳ یک ارسال همگانی در حال اجراست. برای توقف: /broadcaststop", parse_mode=None)
        return
    await state.set_state(BroadcastStates.waiting_for_content)
    await message.answer(
        "📣 ارسال همگانی به همهٔ کاربران\n\n"
        "پیام موردنظر را بفرستید: متن، عکس، فایل، ویدیو، صدا یا موزیک (کپشن هم ارسال می‌شود).\n"
        "پیش از ارسال، پیش‌نمایش و تعداد گیرندگان نمایش داده می‌شود و تأیید شما لازم است.\n\n"
        "برای لغو: /cancel", parse_mode=None)


@broadcast_router.message(StateFilter(BroadcastStates), F.text == "/cancel", _is_admin)
async def cmd_broadcast_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ ارسال همگانی لغو شد.", parse_mode=None)


@broadcast_router.message(Command("broadcaststop"), _is_admin)
async def cmd_broadcast_stop(message: Message):
    if _running():
        _broadcast_task.cancel()
        await message.answer("⏹ درخواست توقف ارسال همگانی ثبت شد.", parse_mode=None)
    else:
        await message.answer("ارسال همگانی فعالی وجود ندارد.", parse_mode=None)


@broadcast_router.message(BroadcastStates.waiting_for_content, _is_admin)
async def broadcast_content(message: Message, state: FSMContext, bot: Bot):
    payload = extract_payload(message)
    if payload is None:
        await message.answer("⚠️ این نوع پیام پشتیبانی نمی‌شود. متن، عکس، فایل، ویدیو، صدا یا موزیک بفرستید.\n"
                             "برای لغو: /cancel", parse_mode=None)
        return
    targets, panel_ok = await _targets()
    if not targets:
        await state.clear()
        await message.answer("✅ کاربری برای ارسال وجود ندارد.", parse_mode=None)
        return
    await state.update_data(_broadcast_payload=payload)
    await state.set_state(BroadcastStates.waiting_for_confirm)

    await message.answer("👇 پیش‌نمایش پیامی که برای کاربران ارسال می‌شود:", parse_mode=None)
    try:
        await send_payload(bot, message.chat.id, payload)
    except Exception as e:
        logger.warning(f"[BROADCAST] پیش‌نمایش ناموفق: {e}")
    note = "" if panel_ok else "\n⚠️ فهرست کاربران پنل دریافت نشد؛ فقط کاربران ثبت‌شده در ربات شمرده شده‌اند."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ ارسال به {len(targets):,} کاربر", callback_data="bcast:go")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="bcast:cancel")],
    ])
    await message.answer(
        f"📣 تعداد گیرندگان: {len(targets):,}\n"
        f"زمان تقریبی: {max(1, round(len(targets) * (SEND_INTERVAL_SECONDS + 0.3) / 60)):,} دقیقه"
        f"{note}\n\nتأیید می‌کنید؟", reply_markup=kb, parse_mode=None)


@broadcast_router.callback_query(F.data == "bcast:cancel", _is_admin)
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("❌ ارسال همگانی لغو شد.", parse_mode=None)


@broadcast_router.callback_query(F.data == "bcast:go", _is_admin)
async def cb_broadcast_go(callback: CallbackQuery, state: FSMContext, bot: Bot):
    global _broadcast_task
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if _running():
        await callback.message.answer("⏳ یک ارسال همگانی در حال اجراست.", parse_mode=None)
        return
    payload = (await state.get_data()).get("_broadcast_payload")
    await state.clear()
    if not payload:
        await callback.message.answer("⚠️ پیام ارسال همگانی پیدا نشد. دوباره با /broadcast شروع کنید.",
                                      parse_mode=None)
        return
    targets, _ = await _targets()
    _broadcast_task = asyncio.create_task(broadcast(bot, targets, payload))
    await callback.message.answer(
        f"🚀 ارسال همگانی به {len(targets):,} کاربر شروع شد. گزارش پیشرفت ارسال می‌شود.\n"
        "برای توقف: /broadcaststop", parse_mode=None)


async def _send_one(bot: Bot, uid: int, payload: dict) -> bool:
    try:
        await send_payload(bot, uid, payload)
        return True
    except TelegramRetryAfter as e:
        await asyncio.sleep(min(int(e.retry_after), 60) + 1)
        try:
            await send_payload(bot, uid, payload)
            return True
        except Exception as e2:
            logger.info(f"[BROADCAST] ارسال به {uid} ناموفق: {e2}")
    except Exception as e:
        logger.info(f"[BROADCAST] ارسال به {uid} ناموفق: {e}")
    return False


async def broadcast(bot: Bot, targets: list[int], payload: dict,
                    interval: float = SEND_INTERVAL_SECONDS) -> tuple[int, int]:
    sent = failed = 0
    try:
        for i, uid in enumerate(targets, 1):
            if await _send_one(bot, uid, payload):
                sent += 1
            else:
                failed += 1
            if i % PROGRESS_EVERY == 0:
                await bot.send_message(
                    ADMIN_ID, f"📣 پیشرفت ارسال همگانی: {i:,} از {len(targets):,} "
                              f"(موفق {sent:,}، ناموفق {failed:,})", parse_mode=None)
            await asyncio.sleep(interval)
        title = "✅ ارسال همگانی تمام شد."
    except asyncio.CancelledError:
        title = "⏹ ارسال همگانی متوقف شد."
    except Exception as e:
        logger.error(f"[BROADCAST] خطا در ارسال همگانی: {e}", exc_info=True)
        title = f"❌ ارسال همگانی با خطا متوقف شد: {e}"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"{title}\n\nموفق: {sent:,}\nناموفق (ربات را مسدود/حذف کرده‌اند یا خطا): {failed:,}",
            parse_mode=None)
    except Exception as e:
        logger.warning(f"[BROADCAST] گزارش پایان ارسال همگانی ناموفق: {e}")
    return sent, failed
