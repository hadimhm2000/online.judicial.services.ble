# -*- coding: utf-8 -*-
"""
check_branches_tree.py
──────────────────────────────────────────────────────────────────────────
درخت انتخاب صلاحیت دادگاه، مخصوص بخش چک — از روی units_output.csv.

⚠️ چرا این ماژول جداگانه لازم است (و نباید branches.py را تغییر داد):
  branches.py (که هم لایحه هم چک از آن استفاده می‌کردند) درخت را از روی
  units_compact.json می‌سازد. آن فایل، برخلاف units_output.csv، زیرشعبه‌های
  «اجرای احکام» (مخصوص اجرای احکامِ صادرشده، نه ثبت دادخواست جدید) را هم به
  همراه دارد. طبق تصویری که فرستادید: زیر «دادگاه عمومی و انقلاب شهرستان
  یزد» به‌جای اینکه این واحد را مستقیماً بشود انتخاب کرد، ۸ شعبهٔ «اجرای
  احکام» نمایش داده می‌شد — که برای ثبت یک دادخواست/دادخواست چک جدید اصلاً
  گزینهٔ درستی نیست.

  در units_output.csv که فرستادید، همین واحد («دادگاه عمومی و انقلاب
  شهرستان یزد») اصلاً هیچ فرزندی ندارد — یعنی خودش مستقیماً قابل انتخاب
  است، دقیقاً همان چیزی که باید باشد. پس درخت چک را از این فایل می‌سازیم؛
  branches.py و مسیر لایحه که از آن استفاده می‌کند دست‌نخورده می‌ماند.

فرمت units_output.csv: Code, Name, Path, Level
  درخت از روی ستون Path (با جداکنندهٔ " > ") ساخته می‌شود؛ نیازی به
  Id/ParentId نیست چون خودِ Path مسیر کامل سلسله‌مراتبی است.

Callback prefix: "cbr:" (متفاوت از "br:" در branches.py — تا با فضای نام
callback_data شعب لایحه اصلاً برخورد نکند).
"""
import csv
import re
import logging
from pathlib import Path as FsPath
from typing import List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

CHECK_UNITS_CSV_PATH = FsPath("units_output.csv")

ROWS: List[dict] = []
PATH_TO_ROW = {}          # normalize(path) -> row
CHILDREN_BY_PATH = {}     # normalize(parent_path) -> [rows]
ROOT_NODES: List[dict] = []
INDEX_TO_PATH = {}
PATH_TO_INDEX = {}
_LOADED = False


def _normalize(text) -> str:
    if not text:
        return ""
    t = str(text)
    t = t.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ة", "ه")
    t = t.replace("‌", "").replace("‏", "").replace("‎", "").replace("‍", "")
    t = re.sub(r"[ً-ٰٟ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def load_check_units():
    global _LOADED, ROWS, PATH_TO_ROW, CHILDREN_BY_PATH, ROOT_NODES, INDEX_TO_PATH, PATH_TO_INDEX
    if _LOADED:
        return True
    if not CHECK_UNITS_CSV_PATH.exists():
        logger.warning(f"⚠️ {CHECK_UNITS_CSV_PATH} پیدا نشد — انتخاب دادگاه چک غیرفعال است.")
        return False

    ROWS.clear()
    PATH_TO_ROW.clear()
    CHILDREN_BY_PATH.clear()
    ROOT_NODES.clear()
    INDEX_TO_PATH.clear()
    PATH_TO_INDEX.clear()

    with CHECK_UNITS_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("Code") or "").strip()
            name = (row.get("Name") or "").strip()
            path = (row.get("Path") or "").strip()
            level = (row.get("Level") or "").strip()
            if not code or not name or not path:
                continue
            item = {"code": code, "name": name, "path": path, "level": level}
            ROWS.append(item)

    for idx, item in enumerate(ROWS):
        norm_path = _normalize(item["path"])
        PATH_TO_ROW[norm_path] = item
        INDEX_TO_PATH[idx] = norm_path
        PATH_TO_INDEX[norm_path] = idx

    for item in ROWS:
        segments = item["path"].split(" > ")
        if len(segments) == 1:
            ROOT_NODES.append(item)
        else:
            parent_path = " > ".join(segments[:-1])
            norm_parent = _normalize(parent_path)
            CHILDREN_BY_PATH.setdefault(norm_parent, []).append(item)

    _LOADED = True
    logger.info(
        f"✅ {len(ROWS)} واحد از {CHECK_UNITS_CSV_PATH} برای انتخاب صلاحیت دادگاه چک بارگذاری شد "
        f"({len(ROOT_NODES)} ریشه، {len(CHILDREN_BY_PATH)} گره دارای فرزند)"
    )
    return True


def get_children(norm_path: str) -> List[dict]:
    return CHILDREN_BY_PATH.get(norm_path, [])


def has_children(item: dict) -> bool:
    return bool(CHILDREN_BY_PATH.get(_normalize(item["path"])))


def create_check_branch_keyboard(
    nodes: List[dict],
    page: int = 0,
    parent_path: Optional[str] = None,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    load_check_units()
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_nodes = nodes[start_idx:end_idx]

    MAX_LABEL_LEN = 60
    buttons = []

    for node in page_nodes:
        norm_path = _normalize(node["path"])
        idx = PATH_TO_INDEX.get(norm_path, 0)
        is_folder = has_children(node)
        icon = "📁" if is_folder else "✅"

        name = node["name"]
        budget = MAX_LABEL_LEN - len(icon) - 1
        if budget > 1 and len(name) > budget:
            display_name = f"{icon} " + name[: budget - 1].rstrip() + "…"
        else:
            display_name = f"{icon} " + name

        if is_folder:
            callback = f"cbr:open:{idx}:0"
        else:
            callback = f"cbr:sel:{idx}"

        buttons.append([InlineKeyboardButton(text=display_name, callback_data=callback)])

    nav_buttons = []
    total_pages = (len(nodes) + page_size - 1) // page_size
    parent_idx = PATH_TO_INDEX.get(_normalize(parent_path), 0) if parent_path else 0

    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ قبلی", callback_data=f"cbr:page:{parent_idx}:{page-1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="بعدی ▶️", callback_data=f"cbr:page:{parent_idx}:{page+1}")
        )
    if nav_buttons:
        buttons.append(nav_buttons)

    control_buttons = []
    if parent_path:
        segments = parent_path.split(" > ")
        if len(segments) > 1:
            grandparent_path = " > ".join(segments[:-1])
            grandparent_idx = PATH_TO_INDEX.get(_normalize(grandparent_path))
            if grandparent_idx is not None:
                control_buttons.append(
                    InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"cbr:back:{grandparent_idx}:0")
                )
            else:
                control_buttons.append(
                    InlineKeyboardButton(text="🔙 بازگشت", callback_data="cbr:root:0")
                )
        else:
            control_buttons.append(
                InlineKeyboardButton(text="🔙 بازگشت", callback_data="cbr:root:0")
            )

    control_buttons.append(InlineKeyboardButton(text="🏠 ریشه", callback_data="cbr:root:0"))
    buttons.append(control_buttons)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


load_check_units()
