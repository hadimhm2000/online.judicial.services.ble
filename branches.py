"""
ماژول مدیریت شعب قضایی
این ماژول برای نمایش درختی شعب و واحدهای قضایی استفاده می‌شود
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from states import Form

branches_router = Router()

# ──────────────────────────────────────────────────────────────────────────────
# بارگذاری داده‌های شعب
# ──────────────────────────────────────────────────────────────────────────────

UNITS_DATA = []
ID_TO_NODE = {}
CHILDREN_BY_PARENT = {}
INDEX_TO_ID = {}
ID_TO_INDEX = {}
ROOT_NODES = []

def load_units_data():
    """بارگذاری و پردازش داده‌های شعب"""
    global UNITS_DATA, ID_TO_NODE, CHILDREN_BY_PARENT, INDEX_TO_ID, ID_TO_INDEX, ROOT_NODES
    
    # جستجوی فایل داده
    possible_paths = [
        Path("units_compact.json"),
        Path("all_units.json"),
        Path("sample_units.json"),  # فایل نمونه برای تست
    ]
    
    data_file = None
    for path in possible_paths:
        if path.exists():
            data_file = path
            break
    
    if not data_file:
        logging.warning("⚠️ فایل داده شعب پیدا نشد. قابلیت /branches غیرفعال است.")
        return False
    
    try:
        with data_file.open("r", encoding="utf-8") as f:
            UNITS_DATA = json.load(f)
        
        logging.info(f"✅ {len(UNITS_DATA)} واحد از {data_file} بارگذاری شد")
        
        # ساخت دیکشنری‌های کمکی
        ID_TO_NODE.clear()
        CHILDREN_BY_PARENT.clear()
        INDEX_TO_ID.clear()
        ID_TO_INDEX.clear()
        ROOT_NODES.clear()
        
        # ایجاد نقشه Id به Node
        for idx, node in enumerate(UNITS_DATA):
            node_id = node.get("Id")
            if node_id:
                ID_TO_NODE[node_id] = node
                INDEX_TO_ID[idx] = node_id
                ID_TO_INDEX[node_id] = idx
        
        # ایجاد نقشه Parent به Children
        for node in UNITS_DATA:
            parent_id = node.get("ParentId") or node.get("ParentUnitId")
            node_id = node.get("Id")
            
            if parent_id:
                if parent_id not in CHILDREN_BY_PARENT:
                    CHILDREN_BY_PARENT[parent_id] = []
                CHILDREN_BY_PARENT[parent_id].append(node)
        
        # یافتن نودهای ریشه
        for node in UNITS_DATA:
            parent_id = node.get("ParentId") or node.get("ParentUnitId")
            depth = node.get("Depth", 0)
            
            # ریشه: عمق 0 یا بدون والد یا والد در دیتا نیست
            if depth == 0 or not parent_id or parent_id not in ID_TO_NODE:
                ROOT_NODES.append(node)
        
        if not ROOT_NODES:
            # اگر ریشه پیدا نشد، اولین نود را ریشه فرض کن
            ROOT_NODES.append(UNITS_DATA[0])
        
        logging.info(f"📊 آمار: {len(ROOT_NODES)} ریشه، {len(ID_TO_NODE)} نود، {len(CHILDREN_BY_PARENT)} والد")
        return True
        
    except Exception as e:
        logging.error(f"❌ خطا در بارگذاری داده شعب: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# توابع کمکی
# ──────────────────────────────────────────────────────────────────────────────

def get_children(parent_id: str) -> List[dict]:
    """دریافت فرزندان یک نود"""
    return CHILDREN_BY_PARENT.get(parent_id, [])


def create_branches_keyboard(
    nodes: List[dict],
    page: int = 0,
    parent_id: Optional[str] = None,
    page_size: int = 8
) -> InlineKeyboardMarkup:
    """
    ساخت کیبورد inline برای نمایش شعب با صفحه‌بندی
    
    Args:
        nodes: لیست نودها برای نمایش
        page: شماره صفحه فعلی (از 0 شروع)
        parent_id: شناسه نود والد (برای دکمه بازگشت)
        page_size: تعداد آیتم در هر صفحه
    """
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_nodes = nodes[start_idx:end_idx]
    
    buttons = []
    
    # حداکثر طول قابل‌اطمینان برای متن دکمه‌های اینلاین بله.
    # برخی نام‌های واحدها تا ۱۳۰ کاراکتر می‌رسند و کلاینت تلگرام در این
    # حالت به‌طور غیرقابل‌پیش‌بینی متن را برش می‌زند (حتی گاهی آیکون ابتدای
    # متن را هم پنهان می‌کند)، بنابراین خودمان با کنترل کامل کوتاهش می‌کنیم.
    MAX_LABEL_LEN = 60
    
    # دکمه‌های شعب/واحدها
    for node in page_nodes:
        node_id = node.get("Id")
        node_name = node.get("UnitName", "نامشخص")
        unit_no = node.get("UnitNo")
        has_child = node.get("HasChildUnit", False)
        can_select = node.get("HasSelectUnit", False)
        code = node.get("Code", "")
        
        # آیکون بر اساس نوع واحد
        if has_child:
            icon = "📁"
        elif code:  # واحد نهایی با کد
            icon = "✅"
        else:  # واحد نهایی بدون کد
            icon = "⚪️"
        
        # پیشوند: آیکون + شماره واحد (این بخش‌ها مهم‌اند و هرگز نباید بریده شوند)
        prefix = f"{icon} "
        if unit_no:
            prefix += f"({unit_no}) "
        
        # فقط قسمت توصیفیِ نام را در صورت طولانی‌بودن کوتاه می‌کنیم
        budget = MAX_LABEL_LEN - len(prefix)
        if budget > 1 and len(node_name) > budget:
            display_name = prefix + node_name[: budget - 1].rstrip() + "…"
        else:
            display_name = prefix + node_name
        
        # استفاده از index به جای Id کامل (برای کوتاه‌تر کردن callback_data)
        idx = ID_TO_INDEX.get(node_id, 0)
        
        if has_child:
            # واحد دارای زیرمجموعه - قابل باز شدن
            # نکته مهم: صفحه‌ی لیست فرزندان همیشه باید از صفر شروع شود،
            # نه صفحه‌ی فعلیِ لیستی که این دکمه در آن قرار دارد
            # (باگ قبلی باعث می‌شد لیست فرزندانِ نودهایی که در صفحات
            # بالاتر بودند، خالی به نظر برسد)
            callback = f"br:open:{idx}:0"
        elif code:
            # واحد نهایی با کد - قابل انتخاب
            callback = f"br:sel:{idx}"
        else:
            # واحد نهایی بدون کد - غیرقابل انتخاب (نمایش اطلاعات)
            callback = f"br:info:{idx}"
        
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=callback)])
    
    # دکمه‌های صفحه‌بندی
    nav_buttons = []
    total_pages = (len(nodes) + page_size - 1) // page_size
    
    if page > 0:
        # دکمه صفحه قبل
        parent_idx = ID_TO_INDEX.get(parent_id, 0) if parent_id else 0
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ قبلی", callback_data=f"br:page:{parent_idx}:{page-1}")
        )
    
    if page < total_pages - 1:
        # دکمه صفحه بعد
        parent_idx = ID_TO_INDEX.get(parent_id, 0) if parent_id else 0
        nav_buttons.append(
            InlineKeyboardButton(text="بعدی ▶️", callback_data=f"br:page:{parent_idx}:{page+1}")
        )
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # دکمه‌های کنترلی
    control_buttons = []
    
    if parent_id:
        # دکمه بازگشت
        parent_idx = ID_TO_INDEX.get(parent_id, 0)
        # پیدا کردن والد والد (جد)
        parent_node = ID_TO_NODE.get(parent_id)
        if parent_node:
            grandparent_id = parent_node.get("ParentId") or parent_node.get("ParentUnitId")
            if grandparent_id and grandparent_id in ID_TO_NODE:
                grandparent_idx = ID_TO_INDEX.get(grandparent_id, 0)
                control_buttons.append(
                    InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"br:back:{grandparent_idx}:0")
                )
            else:
                # برگشت به ریشه
                control_buttons.append(
                    InlineKeyboardButton(text="🔙 بازگشت", callback_data="br:root:0")
                )
    
    # دکمه شروع از اول (همیشه)
    control_buttons.append(
        InlineKeyboardButton(text="🏠 ریشه", callback_data="br:root:0")
    )
    
    if control_buttons:
        buttons.append(control_buttons)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_unit_info(node: dict) -> str:
    """فرمت‌دهی اطلاعات یک واحد برای نمایش"""
    unit_name = node.get("UnitName", "نامشخص")
    code = node.get("Code", "ندارد")
    unit_id = node.get("Id", "ندارد")
    unit_no = node.get("UnitNo", "ندارد")
    unit_type = node.get("UnitType", "ندارد")
    path = node.get("Path", "ندارد")
    
    text = (
        f"📋 *اطلاعات واحد*\n\n"
        f"📌 نام: *{unit_name}*\n"
        f"🔢 کد: `{code}`\n"
        f"🆔 شناسه: `{unit_id}`\n"
        f"🔢 شماره واحد: *{unit_no}*\n"
        f"📊 نوع واحد: *{unit_type}*\n"
    )
    
    if path and len(path) > 0:
        text += f"🗂 مسیر:\n`{path}`\n"
    
    return text


# ──────────────────────────────────────────────────────────────────────────────
# هندلرها
# ──────────────────────────────────────────────────────────────────────────────

@branches_router.message(Command("branches"))
async def cmd_branches(message: Message, state: FSMContext):
    """نمایش لیست شعب (ریشه درخت)"""
    if not UNITS_DATA:
        await message.answer(
            "⚠️ داده‌های شعب در دسترس نیست.\n"
            "لطفاً فایل `units_compact.json` یا `all_units.json` را در ریشه پروژه قرار دهید."
        )
        return
    
    await message.answer(
        "🏛 *سامانه جستجوی شعب قضایی*\n\n"
        "لطفاً از لیست زیر انتخاب کنید:",
        reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))


@branches_router.callback_query(F.data.startswith("br:"))
async def process_branch_callback(callback: CallbackQuery, state: FSMContext):
    """پردازش callback های مربوط به شعب"""
    await callback.answer()
    
    data_parts = callback.data.split(":")
    action = data_parts[1]
    
    if action == "root":
        # بازگشت به ریشه
        await callback.message.edit_text(
            "🏛 *سامانه جستجوی شعب قضایی*\n\n"
            "لطفاً از لیست زیر انتخاب کنید:",
            reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
        return
    
    idx = int(data_parts[2])
    node_id = INDEX_TO_ID.get(idx)
    
    if not node_id or node_id not in ID_TO_NODE:
        await callback.message.edit_text("❌ خطا: واحد مورد نظر یافت نشد.")
        return
    
    node = ID_TO_NODE[node_id]
    
    if action == "open":
        # باز کردن فرزندان
        children = get_children(node_id)
        
        if not children:
            await callback.message.edit_text(
                f"ℹ️ واحد «{node.get('UnitName')}» فرزندی ندارد.\n\n"
                + format_unit_info(node))
            return
        
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        
        await callback.message.edit_text(
            f"📁 *{node.get('UnitName')}*\n\n"
            "لطفاً یکی از موارد زیر را انتخاب کنید:",
            reply_markup=create_branches_keyboard(children, page=page, parent_id=node_id))
    
    elif action == "page":
        # تغییر صفحه
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        children = get_children(node_id)
        
        await callback.message.edit_reply_markup(
            reply_markup=create_branches_keyboard(children, page=page, parent_id=node_id)
        )
    
    elif action == "back":
        # بازگشت به والد
        parent_id = INDEX_TO_ID.get(idx)
        if not parent_id or parent_id not in ID_TO_NODE:
            # برگشت به ریشه
            await callback.message.edit_text(
                "🏛 *سامانه جستجوی شعب قضایی*\n\n"
                "لطفاً از لیست زیر انتخاب کنید:",
                reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
            return
        
        parent_node = ID_TO_NODE[parent_id]
        children = get_children(parent_id)
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        
        await callback.message.edit_text(
            f"📁 *{parent_node.get('UnitName')}*\n\n"
            "لطفاً یکی از موارد زیر را انتخاب کنید:",
            reply_markup=create_branches_keyboard(children, page=page, parent_id=parent_id))
    
    elif action == "sel":
        # انتخاب واحد نهایی (با کد)
        branch_code = node.get("Code", "")

        # بررسی وجود کد
        if not branch_code:
            await callback.answer(
                "⚠️ این واحد فاقد کد است و قابل انتخاب نیست.",
                show_alert=True
            )
            return

        # نمایش اطلاعات واحد
        await callback.message.edit_text(
            format_unit_info(node))

        current_state = await state.get_state()

        # اگر در حالت انتخاب شعبه برای چک هستیم
        if current_state == Form.check_branch_code:
            from states import Form as FormCheck
            branch_name = node.get("UnitName", "")
            branch_path = node.get("Path", "")

            await state.update_data(
                check_branch_name=branch_name,
                check_branch_code=branch_code,
                check_branch_path=branch_path
            )

            await callback.message.answer(
                f"✅ *دادگاه انتخاب شد:*\n\n"
                f"📋 نام: *{branch_name}*\n"
                f"🔢 کد: `{branch_code}`")

            # رفتن به پیش‌نمایش چک
            from check_handlers import _go_to_check_preview
            await _go_to_check_preview(callback.message, state)
            return

        # اگر در حالت انتخاب شعبه برای لایحه هستیم
        if current_state == Form.lavayeh_branch_name:
            # ذخیره نام شعبه و کد شعبه
            branch_name = node.get("UnitName", "")
            branch_path = node.get("Path", "")
            
            await state.update_data(
                lavayeh_branch_name=branch_name,
                lavayeh_branch_code=branch_code,
                lavayeh_branch_path=branch_path
            )
            
            await callback.message.answer(
                f"✅ *شعبه انتخاب شد:*\n\n"
                f"📋 نام: *{branch_name}*\n"
                f"🔢 کد: `{branch_code}`")
            
            # نکته مهم: انتخاب شعبه از لیست فقط در مسیر «شماره بایگانی» اتفاق می‌افتد.
            # در این مسیر، سایت سنا هیچ‌گاه فیلد استان را نمی‌خواهد (فقط شماره
            # بایگانی + کد شعبه کافی است — نگاه کنید به lavayeh_scenario.py،
            # بخش archive_number)، پس دیگر لازم نیست از کاربر استان پرسیده شود.
            data = await state.get_data()
            title = data.get("lavayeh_title", "")
            
            if title == "اعلام وکالت":
                from keyboards import back_only_kb
                await callback.message.answer(
                    "👤 لطفاً *کد ملی وکیل* را ارسال فرمایید:",
                    reply_markup=back_only_kb)
                await state.set_state(Form.ealam_vakalaht_national_id)
            else:
                from keyboards import create_person_type_kb
                await state.update_data(lavayeh_persons=[], _current_person_index=0)
                await callback.message.answer(
                    "👥 لطفاً نوع شخصیت ارائه‌دهنده لایحه را انتخاب کنید:",
                    reply_markup=create_person_type_kb())
                await state.set_state(Form.lavayeh_person_type)
    
    elif action == "info":
        # نمایش اطلاعات واحد بدون کد (غیرقابل انتخاب)
        await callback.answer(
            "⚠️ این واحد فاقد کد است و قابل انتخاب نیست.",
            show_alert=True
        )


# ──────────────────────────────────────────────────────────────────────────────
# بارگذاری اولیه
# ──────────────────────────────────────────────────────────────────────────────

# بارگذاری داده‌ها هنگام import
load_units_data()
