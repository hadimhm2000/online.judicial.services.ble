'''
لایه یکپارچه آپلود منضمات — بازنویسی‌شده بر اساس فایل توضیحات منضمات
Unified resilient upload layer for judicial system attachments.

هر ۳ سناریو (لایحه، اظهارنامه، اعلام وکالت) از این ماژول استفاده می‌کنند.

🆕 تغییرات این نسخه (اصلاح مشکل هنگ کردن بین btnUploadAll و btnApplyAll):
  ─────────────────────────────────────────────────────────────────────────
  ۱. بازنویسی کامل wait_for_loading_bar بر اساس انتخابگر دقیق سامانه ثنا:
     - .progress-bar-striped.progress-bar-animated.active[style*="0072c6"]
     - تشخیص نوار آبی بالا صفحه با background-color:#0072c6
     - پشتیبانی از چند بار ظاهر/محو شدن لودینگ (multi-cycle)

  ۲. تابع جدید click_upload_all_with_retry:
     - کلیک واقعی روی #btnUploadAll
     - انتظار قطعی اتمام آپلود:
       a) منتظر لودینگ می‌ماند
       b) پس از اتمام لودینگ، منتظر alert موفقیت می‌ماند
       c) سپس منتظر محو شدن alertها می‌ماند
       d) سپس منتظر viewModel.loading === false می‌ماند
     - تشخیص صحیح خطای ورود همزمان

  ۳. بازنویزی click_apply_all_with_retry:
     - قبل از کلیک: تضمین viewModel.loading === false
     - انتظار صحیح برای "پیوست مورد نظر با موفقیت تایید شد"
     - شمارش تجمعی (نه لحظه‌ای) alertها برای جلوگیری از تایم‌اوت
     - در خطای ورود همزمان: NOT delete-then-retry، بلکه صبر+کلیک مجدد
     - در خطای غیر از ورود همزمان: گزارش به کاربر بدون حذف خودکار

  ۴. حذف کامل fallback مخرب full_delete_attachment_row از روی خطای ApplyAll:
     - قبلاً اگر ApplyAll ناموفق بود، کل ردیف حذف و از اول ثبت می‌شد
     - این دقیقاً علت رفتار «پاک‌کردن پیوست‌ها و بازگشت به آماده‌سازی» بود
     - حالا: فقط گزارش خطا، اطلاع به کاربر/مدیر، توقف آپلود بدون حذف

  ۵. page_state_snapshot: تابع عکس‌برداری از وضعیت صفحه برای دیاگنوستیک

  ۶. لاگ‌گذاری پررنگ‌تر برای دیباگ آینده

  ادامه‌ی توابع موجود (تغییر نداده‌شده):
    - prepare_files_for_upload / _validate_file / _compress_image / _convert_to_jpeg_if_needed
    - delete_all_files_in_row / delete_document_row_by_title / full_delete_attachment_row
    - click_save_doc_with_retry / click_edit_document_for_title
    - _default_fill_other_attachment_form / resilient_upload_attachment_groups
    - مدیریت checkpoint

  مسیر دقیق طبق فایل توضیحات:
    ۱. ورود به بخش منضمات
    ۲. انتخاب نوع پیوست از #attachmentType
    ۳. پر کردن #txtNo و #txtName (و #txt001/#incAttach0 برای چندبرگ)
    ۴. کلیک #btnSaveDoc + انتظار لودینگ + بستن پاپ‌آپ موفقیت
    ۵. کلیک editDocument روی ردیف
    ۶. انتخاب فایل‌ها با #files_multipleFileUploader
    ۷. کلیک #btnUploadAll (آپلود همه) + انتظار کامل اتمام آپلود ⭐
    ۸. خطای ورود همزمان → اطلاع به مدیر → لاگین مجدد → حذف و شروع از اول
    ۹. انتظار محو شدن alertهای "پیوست مورد نظر با موفقیت ثبت گردید" ⭐
    ۱۰. کلیک #btnApplyAll (تایید همه) + انتظار تایید هر پیوست ⭐
    ۱۱. خطای ورود همزمان → لاگین مجدد → کلیک مجدد #btnApplyAll
    ۱۲. بازگشت به فهرست (#btnGotoMainPage)
'''

import os
import time
import asyncio
import logging
from typing import Optional, Callable, Tuple, List, Dict, Any

from aiogram import Bot

from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, wait_for_angular_idle,
    soft_click_if_exists, dismiss_expiry_popup)

# =========================================================
# تنظیمات
# =========================================================
MAX_IMAGE_BYTES = 450 * 1024       # 450 KB
UPLOAD_CONFIRM_TIMEOUT = 300       # ثانیه — افزایش از ۱۲۰ به ۳۰۰ برای فایل‌های زیاد
MAX_UPLOAD_ATTEMPTS = 3            # تلاش هر ردیف
MAX_SAVE_DOC_RETRIES = 3           # تلاش ذخیره سند
MAX_APPLY_ALL_RETRIES = 5          # تلاش اعمال همه — افزایش از ۳ به ۵
MAX_UPLOAD_ALL_RETRIES = 3         # تلاش آپلود همه (جدید)
CHECKPOINT_EXPIRY_HOURS = 24
LOADING_BAR_TIMEOUT = 90           # حداکثر انتظار برای نوار لودینگ (ثانیه) — افزایش از ۶۰ به ۹۰
UPLOAD_ALL_SETTLE_TIMEOUT = 120    # حداکثر انتظار برای آرام‌شدن صفحه بعد از آپلود همه
APPLY_ALL_SETTLE_TIMEOUT = 180     # حداکثر انتظار برای آرام‌شدن صفحه بعد از تایید همه
ALERT_DISMISS_TIMEOUT = 60         # حداکثر انتظار برای محو شدن alertها
INTER_STEP_DELAY = 2.0             # تأخیر بین مراحل (ثانیه)


def _log(prefix, msg, level='info'):
    """لاگ ساده با پیشوند."""
    fn = getattr(logging, level, logging.info)
    fn(f"[{prefix}] {msg}")


def _title_log(prefix, action, title):
    """لاگ با عنوان."""
    return f"{action} [{title}]"


# =========================================================
# ۱. اعتبارسنجی و آماده‌سازی فایل
# =========================================================

def _compress_image(path: str, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    try:
        if os.path.getsize(path) <= max_bytes:
            return path
    except OSError:
        return path

    try:
        from PIL import Image
    except ImportError:
        logging.warning(f"[UPLOAD] Pillow نصب نیست؛ فشرده‌سازی '{path}' انجام نشد.")
        return path

    try:
        img = Image.open(path).convert("RGB")
        out_path = os.path.splitext(path)[0] + "_compressed.jpg"

        quality = 90
        width, height = img.size
        while True:
            img.save(out_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(out_path) <= max_bytes or (quality <= 30 and width <= 600):
                break
            if quality > 30:
                quality -= 15
            else:
                width = int(width * 0.8)
                height = int(height * 0.8)
                img = img.resize((width, height), Image.LANCZOS)

        if out_path != path and os.path.exists(out_path):
            try:
                os.remove(path)
            except OSError:
                pass
            return out_path
        return path
    except Exception as e:
        logging.error(f"[UPLOAD] خطا در فشرده‌سازی '{path}': {e}")
        return path


def _convert_to_jpeg_if_needed(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        return path

    try:
        from PIL import Image
    except ImportError:
        return path

    try:
        img = Image.open(path).convert("RGB")
        out_path = os.path.splitext(path)[0] + ".jpg"
        img.save(out_path, "JPEG", quality=92, optimize=True)
        try:
            os.remove(path)
        except OSError:
            pass
        logging.info(f"[UPLOAD] تبدیل '{ext}' به JPEG: '{out_path}'")
        return out_path
    except Exception as e:
        logging.error(f"[UPLOAD] خطا در تبدیل '{path}' به JPEG: {e}")
        return path


def _validate_file(path: str) -> Tuple[bool, str]:
    if not os.path.exists(path):
        return False, f"فایل وجود ندارد: {path}"
    try:
        size = os.path.getsize(path)
        if size == 0:
            return False, f"فایل خالی است: {path}"
        if size > 5 * 1024 * 1024:
            return False, f"حجم فایل بیش از ۵ مگابایت: {path} ({size/1024/1024:.1f} MB)"
    except OSError as e:
        return False, f"خطا در خواندن فایل: {e}"
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
    except ImportError:
        pass
    except Exception as e:
        return False, f"فایل آسیب‌دیده (corrupt): {path} - {e}"
    return True, ""


async def prepare_files_for_upload(
    image_paths: List[str],
    bot: Bot = None,
    user_id: int = None,
    prefix: str = "UPLOAD",
    compress: bool = True,
    convert_to_jpeg: bool = True) -> Tuple[List[str], List[Dict[str, str]]]:
    """آماده‌سازی فایل‌ها: اعتبارسنجی، تبدیل به JPEG، فشرده‌سازی."""
    prepared = []
    errors = []

    for i, path in enumerate(image_paths):
        valid, err = _validate_file(path)
        if not valid:
            errors.append({"path": path, "error": err, "index": i})
            _log(prefix, f"فایل نامعتبر #{i}: {err}", 'error')
            continue

        current_path = path
        if convert_to_jpeg:
            current_path = _convert_to_jpeg_if_needed(current_path)
        if compress:
            current_path = _compress_image(current_path)

        try:
            final_size = os.path.getsize(current_path)
            if final_size > MAX_IMAGE_BYTES * 2:
                _log(prefix, f"فایل #{i} بعد از فشرده‌سازی بزرگ: {final_size/1024:.0f} KB", 'warning')
        except OSError:
            pass

        prepared.append(current_path)

    if errors and bot and user_id:
        error_summary = "\n".join(f"  - {e['error']}" for e in errors)
        _log(prefix, f"{len(errors)} فایل نامعتبر:\n{error_summary}", 'warning')

    return prepared, errors


async def download_images_from_bale(
    bot: Bot,
    file_ids: list,
    user_id: int,
    prefix: str = "UPLOAD") -> List[str]:
    """
    دانلود مجموعه‌ای از فایل‌های تلگرام (file_id) به‌صورت فایل‌های محلی
    و فشرده‌سازی آن‌ها — همان الگویی که در لایحه/اظهارنامه/اعلام وکالت
    (`_download_images_from_bale`) استفاده می‌شود، اینجا به‌صورت
    عمومی و مشترک قرار گرفته تا سایر ماژول‌ها (مثل تست منضمات در
    scenarios.py) هم بتوانند از آن استفاده کنند.

    بازگشت: لیست مسیرهای محلی فایل‌های دانلودشده (فقط مواردی که موفق بودند).
    """
    paths: List[str] = []
    for i, file_id in enumerate(file_ids):
        try:
            file_info = await bot.get_file(file_id)
            ext = "jpg"
            if file_info.file_path:
                ext = file_info.file_path.split(".")[-1].lower()
                if ext not in ("jpg", "jpeg", "png"):
                    ext = "jpg"

            path = f"attach_img_{user_id}_{i}_{int(time.time()*1000)}.{ext}"
            await bot.download_file(file_info.file_path, path)
            path = _compress_image(path)
            paths.append(path)
        except Exception as e:
            _log(prefix, f"خطا در دانلود تصویر #{i} برای کاربر {user_id}: {e}", 'error')

    return paths


# =========================================================
# ۲. تشخیص نوار لودینگ آبی سامانه ثنا + دیاگنوستیک
# =========================================================

async def page_state_snapshot(page, prefix: str = "UPLOAD") -> Dict[str, Any]:
    """
    عکس‌برداری از وضعیت فعلی صفحه برای دیاگنوستیک.
    در صورت بروز مشکل، این خروجی به فهمیدن علت کمک می‌کند.
    """
    try:
        snap = await page.evaluate('''() => {
            const result = {
                url: location.href,
                viewModel_loading: null,
                has_btnUploadAll: false,
                has_btnApplyAll: false,
                btnUploadAll_disabled: null,
                btnApplyAll_disabled: null,
                has_loading_bar_blue: false,
                has_blockUI: false,
                has_sweet_alert: false,
                sweet_alert_text: null,
                sweet_alert_is_success: false,
                sweet_alert_is_error: false,
                success_alert_count: 0,
                confirm_alert_count: 0,
                delete_alert_count: 0,
                visible_delete_buttons: 0,
                uploader_queue_length: null,
                timestamp: Date.now()
            };

            // بررسی viewModel.loading
            try {
                if (typeof angular !== 'undefined') {
                    const body = document.body || document.querySelector('[ng-app]');
                    if (body) {
                        const scope = angular.element(body).scope();
                        if (scope && scope.viewModel) {
                            result.viewModel_loading = !!scope.viewModel.loading;
                        }
                        if (scope && scope.uploader) {
                            result.uploader_queue_length = scope.uploader.queue ? scope.uploader.queue.length : 0;
                        }
                    }
                }
            } catch(e) {}

            // دکمه‌ها
            const btnUpload = document.querySelector('#btnUploadAll');
            const btnApply = document.querySelector('#btnApplyAll');
            result.has_btnUploadAll = !!btnUpload;
            result.has_btnApplyAll = !!btnApply;
            if (btnUpload) result.btnUploadAll_disabled = btnUpload.disabled;
            if (btnApply) result.btnApplyAll_disabled = btnApply.disabled;

            // نوار لودینگ آبی (سامانه ثنا)
            const blueBars = document.querySelectorAll(
                '.progress-bar.progress-bar-striped.progress-bar-animated'
            );
            for (const bar of blueBars) {
                const rect = bar.getBoundingClientRect();
                const style = window.getComputedStyle(bar);
                if (rect.width > 0 && rect.height > 0 && style.display !== 'none') {
                    if (style.backgroundColor.includes('0, 114, 198') ||
                        style.backgroundColor.includes('0,114,198') ||
                        (bar.style && bar.style.backgroundColor && bar.style.backgroundColor.includes('0072c6'))) {
                        result.has_loading_bar_blue = true;
                        break;
                    }
                    // اگر اصلاً نوار progress-bar-animated دیده شد، آن را حساب کن
                    result.has_loading_bar_blue = true;
                    break;
                }
            }

            // blockUI
            const blockUI = document.querySelector('.blockUI, .blockOverlay');
            if (blockUI && window.getComputedStyle(blockUI).display !== 'none') {
                result.has_blockUI = true;
            }

            // sweet-alert
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) {
                result.has_sweet_alert = true;
                const p = popup.querySelector('p');
                const h2 = popup.querySelector('h2');
                result.sweet_alert_text = ((h2 ? h2.innerText : '') + ' ' + (p ? p.innerText : '')).trim();
                const successIcon = popup.querySelector('.sa-icon.sa-success');
                const errorIcon = popup.querySelector('.sa-icon.sa-error');
                if (successIcon && window.getComputedStyle(successIcon).display !== 'none') {
                    result.sweet_alert_is_success = true;
                }
                if (errorIcon && window.getComputedStyle(errorIcon).display !== 'none') {
                    result.sweet_alert_is_error = true;
                }
            }

            // alertهای موفقیت
            const alerts = Array.from(document.querySelectorAll('.alert-success [ng-bind-html], [ng-bind-html]'));
            for (const el of alerts) {
                const t = el.innerText || '';
                if (t.includes('پیوست مورد نظر با موفقیت ثبت گردید')) result.success_alert_count++;
                if (t.includes('پیوست مورد نظر با موفقیت تایید شد')) result.confirm_alert_count++;
                if (t.includes('پیوست مورد نظر با موفقیت حذف گردید')) result.delete_alert_count++;
            }

            // دکمه‌های btnDelete قابل مشاهده
            const delBtns = document.querySelectorAll('button[id^="btnDelete"]:not([disabled])');
            for (const btn of delBtns) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) result.visible_delete_buttons++;
            }

            return result;
        }''')
        return snap or {}
    except Exception as e:
        _log(prefix, f"خطا در page_state_snapshot: {e}", 'error')
        return {"error": str(e)}


async def wait_for_loading_bar(
    page,
    timeout: int = LOADING_BAR_TIMEOUT,
    prefix: str = "UPLOAD",
    expected_cycles: int = 1) -> bool:
    """
    انتظار برای نوار لودینگ آبی سامانه ثنا.

    نوار لودینگ (طبق فایل توضیحات):
        <div class="progress-bar progress-bar-striped progress-bar-animated active width-full"
             style="background-color:#0072c6" role="progressbar" ...>

    رفتار:
        ۱. ابتدا بررسی می‌کند آیا لودینگ در حال حاضر فعال است یا در ۲ ثانیه آینده فعال می‌شود.
        ۲. اگر فعال شد، منتظر ناپدید شدن کامل آن می‌ماند.
        ۳. اگر چند بار لودینگ ظاهر/محو شد (expected_cycles)، همه را طی می‌کند.

    بازگشت:
        True اگر لودینگ ظاهر و محو شد (یا اصلاً ظاهر نشد و صفحه آرام بود).
        False اگر تایم‌اوت رخ داد.
    """
    # بررسی اولیه: لودینگ فعالی وجود دارد؟
    async def is_loading_visible():
        return await page.evaluate('''() => {
            // ۱. نوار لودینگ آبی اصلی سامانه ثنا
            const bars = document.querySelectorAll(
                '.progress-bar.progress-bar-striped.progress-bar-animated'
            );
            for (const bar of bars) {
                const rect = bar.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 &&
                    window.getComputedStyle(bar).display !== 'none') {
                    return true;
                }
            }
            // ۲. blockUI
            const blockUI = document.querySelector('.blockUI, .blockOverlay');
            if (blockUI && window.getComputedStyle(blockUI).display !== 'none') {
                const rect = blockUI.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
            // ۳. spinner کلی سامانه
            const spinner = document.querySelector('.loading, .spinner, .ajax-loader');
            if (spinner && window.getComputedStyle(spinner).display !== 'none') {
                const rect = spinner.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
            return false;
        }''')

    cycles_completed = 0
    waited = 0
    loading_seen_in_cycle = False

    # مرحله ۱: چک اولیه + ۲ ثانیه صبر برای ظاهر شدن احتمالی
    initial = await is_loading_visible()
    if not initial:
        await asyncio.sleep(1)
        recheck = await is_loading_visible()
        if not recheck:
            # شاید اصلاً لودینگ نیاید — اگر expected_cycles == 0 یا صفحه آرام است، True
            _log(prefix, "نوار لودینگ ظاهر نشد — صفحه آرام است", 'debug')
            return True
        loading_seen_in_cycle = True
    else:
        loading_seen_in_cycle = True
        _log(prefix, "نوار لودینگ از قبل فعال بود — منتظر اتمام...", 'debug')

    # مرحله ۲: چرخه‌های انتظار
    while waited < timeout:
        await asyncio.sleep(1)
        waited += 1

        still_visible = await is_loading_visible()

        if still_visible:
            loading_seen_in_cycle = True
            # هنوز در حال لود است
            if waited % 15 == 0:
                _log(prefix, f"لودینگ همچنان فعال است — {waited} ثانیه گذشته")
            continue

        # لودینگ ناپدید شده
        if loading_seen_in_cycle:
            cycles_completed += 1
            _log(prefix, f"لودینگ بعد از {waited} ثانیه ناپدید شد (چرخه {cycles_completed}/{expected_cycles})")
            loading_seen_in_cycle = False

            if cycles_completed >= expected_cycles:
                await asyncio.sleep(1)  # تأخیر کوتاه برای آرام‌شدن کامل
                return True

            # اگر انتظار چرخه‌ی بعدی را داریم، ۲ ثانیه صبر کن
            await asyncio.sleep(2)
        # else: لودینگ هنوز نیامده — ادامه انتظار

    _log(prefix, f"تایم‌اوت نوار لودینگ ({timeout} ثانیه) — cycles_completed={cycles_completed}", 'warning')
    return False


async def detect_concurrent_login_popup(page) -> bool:
    """تشخیص پاپ‌آپ ورود همزمان (concurrent login)."""
    is_concurrent = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;

        const errorIcon = popup.querySelector('.sa-icon.sa-error');
        if (!errorIcon) return false;
        if (window.getComputedStyle(errorIcon).display === 'none') return false;

        const popupText = popup.innerText || "";
        const isConcurrent =
            popupText.includes("رایانه ای دیگر") ||
            popupText.includes("رایانه ای ديگر") ||
            (popupText.includes("اعتبار ورود") && popupText.includes("منقضی")) ||
            popupText.includes("منقضي شده");

        return isConcurrent;
    }''')
    return bool(is_concurrent)


async def get_and_close_error_popup_text(page) -> Optional[str]:
    """دریافت متن خطای پاپ‌آپ و بستن آن (فقط پاپ‌آپ‌های خطا)."""
    text = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return null;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim();
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); }
        return msg || null;
    }''')
    if text:
        await asyncio.sleep(1)
    return text


async def close_error_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def close_success_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def close_any_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


def detect_error_type(error_text: str) -> str:
    if not error_text:
        return "unknown"
    text = error_text.strip()
    if any(kw in text for kw in ["تعداد صفحات", "صفحات اشتباه", "صفحه اشتباه", "تعداد صفحه"]):
        return "page_count"
    if any(kw in text for kw in ["حجم فایل", "حجم بیش", "حجم مجاز", "سایز فایل", "اندازه فایل"]):
        return "file_size"
    if any(kw in text for kw in ["نوع فایل", "فرمت فایل", "پسوند فایل"]):
        return "file_type"
    if any(kw in text for kw in [
        "انقض", "نشست", "session", "ورود", "لاگین",
        "از ساعت ورود شما می‌گذرد",
        "اصل اولویت", "احراز هویت", "تمدید",
        "رایانه ای دیگر", "رایانه ای ديگر",
        "اعتبار ورود", "منقضی", "منقضي",
    ]):
        return "session"
    if any(kw in text for kw in ["تکراری", "قبلا", "موجود"]):
        return "duplicate"
    if any(kw in text for kw in ["خطا", "مشکل", "امکان", "سرور"]):
        return "general"
    return "unknown"


# =========================================================
# ۳. کلیک editDocument روی ردیف + انتظار آپلودر
# =========================================================

async def click_edit_document_for_title(
    page,
    title: str,
    bot: Bot = None,
    user_id: int = None,
    prefix: str = "UPLOAD",
    table_wait_timeout: int = 15,
    uploader_wait_timeout: int = 15) -> bool:
    """کلیک روی دکمه editDocument ردیف مربوط به title."""
    title_variants = [title]
    if 'نمایندگی' in title:
        title_variants.extend(['مدرک نمايندگي', 'مدرک نمایندگی', 'تصوير مدرک نمايندگي', 'تصویر مدرک نمایندگی'])
    if 'ضمایم' in title or 'ضمائم' in title:
        title_variants.extend(['ساير ضمائم', 'سایر ضمائم'])
    title_variants = list(dict.fromkeys(title_variants))

    found_btn = False
    for i in range(table_wait_timeout * 2):
        if i % 10 == 0 and bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین انتظار جدول پیوست‌ها تمدید شد")
                await asyncio.sleep(2)

        result = await page.evaluate('''(variants) => {
            const rows = document.querySelectorAll('table tbody tr');
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                for (const cell of cells) {
                    const text = (cell.innerText || '').trim();
                    for (const v of variants) {
                        if (text.includes(v)) {
                            const editBtn = row.querySelector('button[ng-click*="editDocument"]');
                            if (editBtn && !editBtn.disabled) {
                                editBtn.setAttribute('data-target-edit', '1');
                                return { found: true, rowCount: rows.length };
                            }
                            return { found: false, reason: 'no_button', rowCount: rows.length };
                        }
                    }
                }
            }
            return { found: false, reason: 'not_found', rowCount: rows.length };
        }''', title_variants)

        if result.get("found"):
            _log(prefix, f"ردیف [{title}] در جدول پیدا شد ({result['rowCount']} ردیف کل)")
            found_btn = True
            break
        elif result.get("reason") == "no_button":
            _log(prefix, f"ردیف [{title}] پیدا شد ولی دکمه ویرایش یافت نشد", 'warning')
            return False
        await asyncio.sleep(0.5)

    if not found_btn:
        _log(prefix, f"ردیف [{title}] در جدول ظاهر نشد", 'warning')
        return False

    try:
        target = page.locator('button[data-target-edit="1"]')
        await target.scroll_into_view_if_needed(timeout=5000)
        await asyncio.sleep(0.5)
        await target.click(timeout=10000)
        _log(prefix, f"دکمه editDocument ردیف [{title}] با Playwright کلیک شد")
    except Exception as e:
        _log(prefix, f"کلیک Playwright ناموفق، تلاش با JavaScript: {e}", 'warning')
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[data-target-edit="1"]');
            if (!btn) return false;
            try {
                if (typeof angular !== 'undefined') {
                    const scope = angular.element(btn).scope();
                    if (scope && scope.$parent && scope.$parent.actions) {
                        const $index = scope.$parent.$index !== undefined ? scope.$parent.$index : 0;
                        scope.$apply(() => { scope.$parent.actions.editDocument($index); });
                        return true;
                    }
                    if (scope && scope.actions) {
                        const $index = scope.$index !== undefined ? scope.$index : 0;
                        scope.$apply(() => { scope.actions.editDocument($index); });
                        return true;
                    }
                }
            } catch(e) {}
            btn.click();
            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            return true;
        }''')
        if not clicked:
            _log(prefix, "هیچ روش کلیکی کار نکرد", 'error')
            await page.evaluate('''() => {
                const btn = document.querySelector('button[data-target-edit="1"]');
                if (btn) btn.removeAttribute('data-target-edit');
            }''')
            return False

    await page.evaluate('''() => {
        const btn = document.querySelector('button[data-target-edit="1"]');
        if (btn) btn.removeAttribute('data-target-edit');
    }''')

    _log(prefix, "انتظار برای ظاهر شدن آپلودر...")
    for i in range(uploader_wait_timeout * 2):
        if i % 10 == 0 and bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین انتظار آپلودر تمدید شد")
                await asyncio.sleep(2)

        uploader_count = await page.evaluate('''() => {
            return document.querySelectorAll('#files_multipleFileUploader').length;
        }''')
        if uploader_count > 0:
            _log(prefix, f"#files_multipleFileUploader ظاهر شد (بعد از {(i+1)*0.5:.1f} ثانیه)")
            await asyncio.sleep(1)
            return True

        await asyncio.sleep(0.5)

    _log(prefix, f"#files_multipleFileUploader بعد از {uploader_wait_timeout} ثانیه ظاهر نشد", 'warning')
    return False


# =========================================================
# ۴. حذف کامل ردیف پیوست (فقط برای خطای ورود همزمان)
# =========================================================

async def delete_all_files_in_row(page, bot: Bot = None, user_id: int = None, prefix: str = "UPLOAD") -> int:
    """حذف دانه‌به‌دانه تمام فایل‌های آپلودشده در ردیف فعلی."""
    deleted_count = 0
    max_deletes = 50

    while deleted_count < max_deletes:
        if bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین حذف فایل‌های ردیف تمدید شد.")
                await asyncio.sleep(2)

        clicked = await page.evaluate('''() => {
            const allBtns = Array.from(document.querySelectorAll(
                'button[id^="btnDelete"]:not([disabled])'
            ));
            for (const btn of allBtns) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 &&
                    window.getComputedStyle(btn).display !== 'none') {
                    btn.click();
                    return btn.id;
                }
            }
            const btnAttach = document.querySelector('button[ng-click*="removeAttachment"]:not([disabled])');
            if (btnAttach) {
                const rect = btnAttach.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    btnAttach.click();
                    return 'removeAttachment';
                }
            }
            return null;
        }''')

        if not clicked:
            break

        deleted_count += 1
        _log(prefix, f"فایل #{deleted_count} حذف شد ({clicked})")

        await wait_for_loading_bar(page, timeout=LOADING_BAR_TIMEOUT, prefix=prefix)
        await asyncio.sleep(1)

    _log(prefix, f"مجموعاً {deleted_count} فایل از ردیف حذف شد")
    return deleted_count


async def delete_document_row_by_title(page, title: str, prefix: str = "UPLOAD") -> bool:
    """حذف یک ردیف پیوست از فهرست (سطل زباله removeDocument)."""
    escaped = title.replace("`", "'").replace("\\", "").replace('"', '\\"')

    result = await page.evaluate(f'''() => {{
        const rows = Array.from(document.querySelectorAll('table tbody tr, .table tbody tr'));
        let targetRow = null;
        for (const row of rows) {{
            const cells = row.querySelectorAll('td');
            for (const cell of cells) {{
                if (cell.innerText && cell.innerText.includes("{escaped}")) {{
                    targetRow = row;
                    break;
                }}
            }}
            if (targetRow) break;
        }}
        if (targetRow) {{
            let trashBtn = targetRow.querySelector('button[ng-click*="removeDocument"]');
            if (!trashBtn) {{
                const nextRow = targetRow.nextElementSibling;
                if (nextRow) trashBtn = nextRow.querySelector('button[ng-click*="removeDocument"]');
            }}
            if (trashBtn && !trashBtn.disabled) {{
                trashBtn.click();
                return 'found_and_clicked';
            }}
            return 'btn_disabled';
        }}
        const allTrash = Array.from(document.querySelectorAll('button[ng-click*="removeDocument"]'));
        if (allTrash.length > 0) {{
            allTrash[allTrash.length - 1].click();
            return 'last_row_clicked';
        }}
        return 'not_found';
    }}''')

    if result in ('found_and_clicked', 'last_row_clicked'):
        _log(prefix, f"ردیف [{title}] حذف شد (removeDocument) — result: {result}")
        await asyncio.sleep(2)

        deletion_confirmed = await page.evaluate('''() => {
            const alerts = Array.from(document.querySelectorAll('[ng-bind-html]'));
            return alerts.some(el =>
                el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت حذف گردید")
            );
        }''')

        if deletion_confirmed:
            _log(prefix, f"تایید حذف ردیف [{title}] دریافت شد ✓")
        else:
            _log(prefix, f"پیام تایید حذف برای [{title}] یافت نشد", 'warning')

        await close_any_popup(page)
        await asyncio.sleep(1)
        return True
    elif result == 'btn_disabled':
        _log(prefix, f"دکمه removeDocument برای [{title}] غیرفعال است", 'warning')
        return False
    else:
        _log(prefix, f"ردیف [{title}] برای حذف پیدا نشد", 'warning')
        return False


async def full_delete_attachment_row(
    page,
    title: str,
    bot: Bot = None,
    user_id: int = None,
    prefix: str = "UPLOAD") -> bool:
    """
    حذف کامل یک ردیف پیوست (editDocument → حذف فایل‌ها → removeDocument).

    ⭐ اصلاح مهم: بین «حذف تمام فایل‌های ردیف» و «زدن دکمه سطل‌زباله
    (removeDocument) همان ردیف» هیچ کلیک بازگشتی لازم نیست، چون جدول
    ردیف‌ها (Model.theJSSPetitionDocument) و نمای ویرایش (editDocument)
    هر دو در همان صفحه‌ی منضمات هستند — بدون ناوبری صفحه.

    قبلاً اینجا `soft_click_if_exists(page, "بازگشت به فهرست")` صدا زده
    می‌شد. تنها دکمه‌ای با این متن در کل صفحه #btnGotoMainPage
    (actions.gotoMainStep) است که کاربر را کاملاً از صفحه‌ی منضمات به
    فهرست اصلی مراحل خارج می‌کند — و باعث می‌شد جدول ردیف‌ها و فرم‌های
    بعدی (#attachmentType، #btnSaveDoc) دیگر پیدا نشوند (دقیقاً همان
    علت لاگ خطای «ردیف برای حذف پیدا نشد» + «ذخیره سند: پاسخی دریافت
    نشد»). این کلیک حذف شده است.
    """
    _log(prefix, f"شروع حذف کامل ردیف [{title}]...")

    try:
        escaped = title.replace("`", "'").replace("\\", "").replace('"', '\\"')
        edit_clicked = await page.evaluate(f'''() => {{
            const rows = Array.from(document.querySelectorAll('table tbody tr, .table tbody tr'));
            for (const row of rows) {{
                const cells = row.querySelectorAll('td');
                for (const cell of cells) {{
                    if (cell.innerText && cell.innerText.includes("{escaped}")) {{
                        let editBtn = row.querySelector('button[ng-click*="editDocument"]');
                        if (!editBtn) {{
                            const nextRow = row.nextElementSibling;
                            if (nextRow) editBtn = nextRow.querySelector('button[ng-click*="editDocument"]');
                        }}
                        if (editBtn && !editBtn.disabled) {{
                            editBtn.click();
                            return true;
                        }}
                    }}
                }}
            }}
            return false;
        }}''')

        if edit_clicked:
            await asyncio.sleep(4)
            _log(prefix, f"وارد حالت ویرایش ردیف [{title}] شدیم")

        files_deleted = await delete_all_files_in_row(page, bot, user_id, prefix)
        _log(prefix, f"{files_deleted} فایل از ردیف [{title}] حذف شد")

        # ⭐ بدون کلیک «بازگشت به فهرست» — همان صفحه، فقط بستن پاپ‌آپ باقی‌مانده
        # و اطمینان از آرام‌شدن Angular قبل از جست‌وجوی دکمه حذف ردیف
        await close_any_popup(page)
        await wait_for_angular_idle(page)
        await asyncio.sleep(1.5)

        row_deleted = await delete_document_row_by_title(page, title, prefix)
        if not row_deleted:
            _log(prefix, f"حذف ردیف [{title}] ناموفق با عنوان، تلاش با آخرین ردیف...", 'warning')
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[ng-click*="removeDocument"]'));
                if (btns.length > 0) btns[btns.length - 1].click();
            }''')
            await asyncio.sleep(2)
            await close_any_popup(page)

        await asyncio.sleep(2)
        await close_any_popup(page)
        _log(prefix, f"حذف کامل ردیف [{title}] پایان یافت")
        return True

    except Exception as e:
        _log(prefix, f"خطا در حذف ردیف [{title}]: {e}", 'error')
        return False


# =========================================================
# ۵. کلیک ذخیره سند
# =========================================================

async def click_save_doc_with_retry(
    page, bot: Bot = None, user_id: int = None,
    max_retries: int = MAX_SAVE_DOC_RETRIES,
    prefix: str = "UPLOAD") -> bool:
    """کلیک روی «ثبت و ویرایش پیوست» (#btnSaveDoc) با تلاش مجدد."""
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (btn && !btn.disabled) btn.click();
        }''')

        await wait_for_loading_bar(page, timeout=LOADING_BAR_TIMEOUT, prefix=prefix)

        if bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین ذخیره سند تمدید شد")
                continue
        else:
            await asyncio.sleep(3)

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success:
            await close_success_popup(page)
            return True

        error_text = await get_and_close_error_popup_text(page)
        if error_text:
            _log(prefix, f"خطا در ذخیره سند (تلاش {attempt+1}/{max_retries}): {error_text}", 'warning')
            await asyncio.sleep(4)
            continue

        _log(prefix, f"ذخیره سند: پاسخی دریافت نشد (تلاش {attempt+1}/{max_retries})")
        await asyncio.sleep(4)

    return False


# =========================================================
# ۶. 🆕 کلیک آپلود همه (#btnUploadAll) — کاملاً بازنویسی‌شده
# =========================================================

async def _get_view_model_loading_state(page) -> Optional[bool]:
    """بررسی viewModel.loading از scope انگولار."""
    try:
        state = await page.evaluate('''() => {
            try {
                if (typeof angular === 'undefined') return null;
                const body = document.body || document.querySelector('[ng-app]');
                if (!body) return null;
                const scope = angular.element(body).scope();
                if (!scope || !scope.viewModel) return null;
                return !!scope.viewModel.loading;
            } catch(e) { return null; }
        }''')
        return state
    except Exception:
        return None


async def _count_alerts(page, alert_text_substring: str) -> int:
    """شمارش alertهایی که متن مشخصی دارند."""
    try:
        count = await page.evaluate(f'''() => {{
            const alerts = Array.from(document.querySelectorAll('[ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("{alert_text_substring}")).length;
        }}''')
        return int(count) if count else 0
    except Exception:
        return 0


async def click_upload_all_with_retry(
    page,
    expected_file_count: int,
    bot: Bot,
    user_id: int,
    doc_title: str,
    prefix: str = "UPLOAD",
    max_retries: int = MAX_UPLOAD_ALL_RETRIES) -> Dict[str, Any]:
    """
    کلیک روی «آپلود همه» (#btnUploadAll) + انتظار کامل اتمام آپلود.

    مسیر دقیق (طبق فایل توضیحات):
      ۱. قبل از کلیک: مطمئن شو viewModel.loading === false
      ۲. کلیک روی #btnUploadAll (با ۴ روش فال‌بک AngularJS)
      ۳. تشخیص خطای ورود همزمان → اطلاع به مدیر → خروج با error_type='session'
      ۴. انتظار نوار لودینگ آبی (شدنی در چند چرخه اگر فایل زیاد است)
      ۵. انتظار ظاهر شدن alert "پیوست مورد نظر با موفقیت ثبت گردید" به تعداد expected_file_count
         (شمارش تجمعی — alertها خودبه‌خود محو می‌شوند ولی ما تعداد دیده‌شده را نگه می‌داریم)
      ۶. انتظار محو شدن همه alertها از صفحه
      ۷. تضمین نهایی: viewModel.loading === false و #btnUploadAll موجود و غیرفعال یا ناپدید شده

    بازگشت:
      {
        "success": bool,
        "error_type": str|None,  # 'session', 'click_failed', 'timeout', 'general'
        "error": str|None,
        "alerts_seen": int,
        "method": str,
      }
    """
    result = {
        "success": False,
        "error_type": None,
        "error": None,
        "alerts_seen": 0,
        "method": None,
    }

    for attempt in range(1, max_retries + 1):
        _log(prefix, f"━━━ آپلود همه [{doc_title}] — تلاش {attempt}/{max_retries} ━━━")

        # ─── ۰. بررسی انقضای نشست ───
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            _log(prefix, "نشست قبل از آپلود همه تمدید شد — تلاش مجدد")
            await asyncio.sleep(3)
            continue

        # ─── ۱. انتظار برای آرام‌شدن انگولار + viewModel.loading === false ───
        await wait_for_angular_idle(page)
        for _ in range(10):
            vm_loading = await _get_view_model_loading_state(page)
            if vm_loading is False:
                break
            if vm_loading is None:
                # نمی‌توانیم بررسی کنیم — ادامه
                break
            _log(prefix, f"viewModel.loading === true — صبر ۱ ثانیه...", 'debug')
            await asyncio.sleep(1)

        await asyncio.sleep(INTER_STEP_DELAY)

        # ─── ۲. بررسی وجود و فعال بودن دکمه ───
        btn_status = await page.evaluate('''() => {
            const btn = document.querySelector('#btnUploadAll');
            if (!btn) return { exists: false };
            const rect = btn.getBoundingClientRect();
            return {
                exists: true,
                enabled: !btn.disabled,
                visible: rect.width > 0 && rect.height > 0,
                disabled_reason: btn.disabled ? 'attribute_disabled' : null
            };
        }''')

        if not btn_status.get('exists'):
            result["error_type"] = "click_failed"
            result["error"] = "دکمه #btnUploadAll پیدا نشد"
            _log(prefix, result["error"], 'error')
            # عکس وضعیت برای دیباگ
            snap = await page_state_snapshot(page, prefix)
            _log(prefix, f"وضعیت صفحه: {snap}", 'warning')
            await asyncio.sleep(3)
            continue

        if not btn_status.get('enabled'):
            _log(prefix, f"دکمه #btnUploadAll غیرفعال است — ممکن است آپلود در حال انجام باشد", 'warning')
            # منتظر می‌مانیم تا فعال شود یا خطا بدهد
            for _w in range(30):
                await asyncio.sleep(2)
                enabled = await page.evaluate('''() => {
                    const btn = document.querySelector('#btnUploadAll');
                    return btn && !btn.disabled;
                }''')
                if enabled:
                    break
                # بررسی خطای ورود همزمان
                if await detect_concurrent_login_popup(page):
                    result["error_type"] = "session"
                    result["error"] = "خطای ورود همزمان هنگام انتظار برای فعال‌شدن دکمه"
                    _log(prefix, result["error"], 'error')
                    await check_and_handle_expiry(page, bot, user_id)
                    break
            else:
                _log(prefix, "دکمه #btnUploadAll بعد از ۶۰ ثانیه همچنان غیرفعال", 'warning')
                continue

            if result["error_type"] == "session":
                await asyncio.sleep(3)
                continue

        # ─── ۳. کلیک با ۴ روش فال‌بک AngularJS ───
        click_method = await page.evaluate('''() => {
            const btn = document.querySelector('#btnUploadAll');
            if (!btn || btn.disabled) return 'disabled_or_missing';

            // روش ۱: فراخوانی مستقیم تابع Angular از scope
            try {
                if (typeof angular !== 'undefined') {
                    const ngEl = angular.element(btn);
                    if (ngEl && ngEl.scope) {
                        const scope = ngEl.scope();
                        if (scope && scope.actions && typeof scope.actions.addMultipleDocumentFile === 'function') {
                            const uploadQueue = (scope.viewModel && scope.viewModel.directivesApiSingleUpload)
                                || scope.directivesApiSingleUpload
                                || (scope.$parent && scope.$parent.viewModel && scope.$parent.viewModel.directivesApiSingleUpload);
                            scope.$apply(() => {
                                scope.actions.addMultipleDocumentFile(uploadQueue);
                            });
                            return 'method_1_scope_direct';
                        }
                    }
                }
            } catch(e) { console.log('[UploadAll] Method 1 failed:', e); }

            // روش ۲: $eval روی ng-click expression
            try {
                if (typeof angular !== 'undefined') {
                    const ngEl = angular.element(btn);
                    if (ngEl && ngEl.scope) {
                        const scope = ngEl.scope();
                        const ngClick = btn.getAttribute('ng-click');
                        if (ngClick && scope) {
                            scope.$apply(() => { scope.$eval(ngClick); });
                            return 'method_2_ng_click_eval';
                        }
                    }
                }
            } catch(e) { console.log('[UploadAll] Method 2 failed:', e); }

            // روش ۳: dispatch mouse events + $apply روی rootScope
            try {
                btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                if (typeof angular !== 'undefined') {
                    const rootScope = angular.element(document).scope();
                    if (rootScope) rootScope.$apply();
                }
                return 'method_3_mouse_events';
            } catch(e) { console.log('[UploadAll] Method 3 failed:', e); }

            // فال‌بک: کلیک ساده
            btn.click();
            return 'fallback_simple_click';
        }''')

        result["method"] = click_method
        _log(prefix, f"آپلود همه: کلیک با روش {click_method}")

        if click_method == 'disabled_or_missing':
            _log(prefix, "دکمه در لحظه کلیک غیرفعال یا ناپدید شده", 'warning')
            await asyncio.sleep(3)
            continue

        # ─── ۴. بررسی فوری خطای ورود همزمان (داخل ۳ ثانیه اول) ───
        await asyncio.sleep(2)
        if await detect_concurrent_login_popup(page):
            result["error_type"] = "session"
            result["error"] = "خطای ورود همزمان بعد از کلیک آپلود همه"
            _log(prefix, result["error"], 'error')
            # اطلاع به مدیر و لاگین مجدد
            await check_and_handle_expiry(page, bot, user_id)
            # طبق فایل توضیحات: باید برگردی به همین قسمت — کل ردیف پاک و از اول
            # این کار در resilient_upload_attachment انجام می‌شود
            return result

        # ─── ۵. انتظار نوار لودینگ آبی (با چند چرخه) ───
        # به ازای هر فایل، ممکن است یک چرخه لودینگ رخ دهد
        # برای فایل‌های زیاد، expected_cycles را بیشتر می‌کنیم
        expected_cycles = min(expected_file_count, 5)
        loading_ok = await wait_for_loading_bar(
            page,
            timeout=LOADING_BAR_TIMEOUT,
            prefix=prefix,
            expected_cycles=1,  # فقط یک چرخه کافی — بقیه با wait_for_upload_confirmation پوشش داده می‌شود
        )
        if not loading_ok:
            _log(prefix, "لودینگ تایم‌اوت شد — ادامه با احتیاط", 'warning')

        # ─── ۶. بررسی خطای ورود همزمان بعد از لودینگ ───
        if await detect_concurrent_login_popup(page):
            result["error_type"] = "session"
            result["error"] = "خطای ورود همزمان بعد از اتمام لودینگ آپلود"
            _log(prefix, result["error"], 'error')
            await check_and_handle_expiry(page, bot, user_id)
            return result

        # ─── ۷. انتظار برای ظاهر شدن alert موفقیت آپلود ───
        # ⭐ شمارش تجمعی: alertها خودبه‌خود محو می‌شوند، ولی ما تعداد دیده‌شده را نگه می‌داریم
        alerts_seen_cumulative = 0
        last_logged_count = 0
        no_alert_progress_seconds = 0
        no_progress_warning_logged = False  # ⭐ flag برای جلوگیری از لاگ تکراری
        snapshot_logged = False  # ⭐ flag برای فقط یک‌بار لاگ snapshot

        _log(prefix, f"انتظار برای {expected_file_count} alert موفقیت آپلود (با شمارش تجمعی)...")

        for wait_i in range(UPLOAD_CONFIRM_TIMEOUT * 2):
            if wait_i % 4 == 0 and bot and user_id:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
                if had_expiry:
                    _log(prefix, "نشست حین انتظار alert موفقیت تمدید شد")
                    await asyncio.sleep(1)

            # بررسی خطای ورود همزمان
            if await detect_concurrent_login_popup(page):
                result["error_type"] = "session"
                result["error"] = "خطای ورود همزمان حین انتظار alert موفقیت"
                _log(prefix, result["error"], 'error')
                await check_and_handle_expiry(page, bot, user_id)
                return result

            # شمارش فعلی alertهای دیده‌شده در صفحه
            current_count = await _count_alerts(page, "پیوست مورد نظر با موفقیت ثبت گردید")

            # شمارش تجمعی: هر بار count فعلی را با max قبلی مقایسه کن
            # چون alertها محو می‌شوند، فقط تعداد جدید را به cumulative اضافه می‌کنیم
            # (این یک تقریب است — اگر count کاهش یافت، یعنی alertها در حال محو شدن‌اند)
            if current_count > alerts_seen_cumulative:
                # alertهای جدید ظاهر شده‌اند
                alerts_seen_cumulative = current_count

            # لاگ پیشرفت
            if alerts_seen_cumulative > last_logged_count:
                _log(prefix, f"alert موفقیت آپلود: {alerts_seen_cumulative}/{expected_file_count} دیده شد")
                last_logged_count = alerts_seen_cumulative
                no_alert_progress_seconds = 0
            else:
                no_alert_progress_seconds += 1

            # بررسی موفقیت
            if alerts_seen_cumulative >= expected_file_count:
                _log(prefix, f"✓ تمام {expected_file_count} alert موفقیت آپلود دیده شد")
                break

            # بررسی viewModel.loading
            vm_loading = await _get_view_model_loading_state(page)
            if vm_loading is True:
                no_alert_progress_seconds = 0  # هنوز در حال آپلود
                # ریست flagها چون ممکن است دوباره نیاز به لاگ باشد
                no_progress_warning_logged = False
                snapshot_logged = False
            elif vm_loading is False and no_alert_progress_seconds > 30:
                # ⭐ فقط یک بار لاگ کن — نه هر iteration
                if not no_progress_warning_logged:
                    _log(prefix, f"viewModel.loading === false و ۳۰ ثانیه بدون پیشرفت (alerts_seen={alerts_seen_cumulative}/{expected_file_count})", 'warning')
                    no_progress_warning_logged = True
                    # بررسی وضعیت دکمه‌ها — فقط یک بار
                    btn_apply_enabled = await page.evaluate('''() => {
                        const btn = document.querySelector('#btnApplyAll');
                        return btn && !btn.disabled;
                    }''')
                    _log(prefix, f"#btnApplyAll enabled={btn_apply_enabled}", 'info')
                    if btn_apply_enabled:
                        _log(prefix, "#btnApplyAll فعال است — آپلود احتمالاً تمام شده", 'info')
                        if alerts_seen_cumulative > 0:
                            _log(prefix, f"ادامه با {alerts_seen_cumulative} alert دیده‌شده (ممکن است بقیه محو شده باشند)")
                            break
                        else:
                            _log(prefix, "هیچ alertی دیده نشد ولی دکمه ApplyAll فعال — ادامه با احتیاط", 'warning')
                            break
                    else:
                        # دکمه ApplyAll هنوز غیرفعال است — یعنی آپلود هنوز تمام نشده
                        # یک snapshot از صفحه بگیریم برای دیباگ
                        if not snapshot_logged:
                            snap = await page_state_snapshot(page, prefix)
                            _log(prefix, f"وضعیت صفحه (snapshot): {snap}", 'warning')
                            snapshot_logged = True
                
                # ⭐ اگر ۶۰ ثانیه بدون پیشرفت بود — break کن (نه ۳۰)
                if no_alert_progress_seconds > 60:
                    _log(prefix, f"۶۰ ثانیه بدون پیشرفت — توقف انتظار برای alert (alerts_seen={alerts_seen_cumulative}/{expected_file_count})", 'warning')
                    if not snapshot_logged:
                        snap = await page_state_snapshot(page, prefix)
                        _log(prefix, f"وضعیت نهایی صفحه: {snap}", 'warning')
                    break

            await asyncio.sleep(0.5)
        else:
            # تایم‌اوت
            _log(prefix, f"تایم‌اوت انتظار alert موفقیت — دیده‌شده: {alerts_seen_cumulative}/{expected_file_count}", 'warning')
            # اگر حداقل نیمی از alertها دیده شده، ادامه بده
            if alerts_seen_cumulative >= max(1, expected_file_count // 2):
                _log(prefix, f"ادامه با {alerts_seen_cumulative} alert (بیش از نیمی از مورد انتظار)")
            else:
                # بررسی خطای غیر از ورود همزمان
                error_text = await get_and_close_error_popup_text(page)
                if error_text:
                    error_type = detect_error_type(error_text)
                    _log(prefix, f"خطای سامانه: {error_text} (نوع: {error_type})", 'error')
                    result["error_type"] = error_type
                    result["error"] = error_text
                    result["alerts_seen"] = alerts_seen_cumulative
                    return result
                # بدون خطای مشخص — ممکن است آپلود هنوز در حال انجام باشد
                snap = await page_state_snapshot(page, prefix)
                _log(prefix, f"وضعیت صفحه هنگام تایم‌اوت: {snap}", 'warning')
                result["error_type"] = "timeout"
                result["error"] = f"تایم‌اوت انتظار alert موفقیت آپلود — {alerts_seen_cumulative}/{expected_file_count}"
                result["alerts_seen"] = alerts_seen_cumulative
                # ادامه نمی‌دهیم — برگرد به retry
                await asyncio.sleep(3)
                continue

        result["alerts_seen"] = alerts_seen_cumulative

        # ─── ۸. انتظار برای محو شدن همه alertها از صفحه ───
        _log(prefix, "انتظار برای محو شدن کامل alertها از صفحه...")
        for dismiss_i in range(ALERT_DISMISS_TIMEOUT * 2):
            current_alerts = await _count_alerts(page, "پیوست مورد نظر با موفقیت ثبت گردید")
            if current_alerts == 0:
                _log(prefix, "✓ تمام alertهای موفقیت محو شدند — صفحه آماده تایید")
                break
            if dismiss_i % 10 == 0:
                _log(prefix, f"هنوز {current_alerts} alert در صفحه قابل مشاهده است", 'debug')
            await asyncio.sleep(0.5)
        else:
            _log(prefix, f"alertها بعد از {ALERT_DISMISS_TIMEOUT} ثانیه محو نشدند — ادامه با احتیاط", 'warning')

        # ─── ۹. تضمین نهایی: viewModel.loading === false + صفحه آرام ───
        await wait_for_angular_idle(page)
        for _final in range(15):
            vm_loading = await _get_view_model_loading_state(page)
            if vm_loading is False or vm_loading is None:
                break
            _log(prefix, f"viewModel.loading === true — صبر برای آرام‌شدن نهایی", 'debug')
            await asyncio.sleep(1)

        # ─── ۱۰. بررسی نهایی موفقیت ───
        # اطمینان از اینکه #btnApplyAll موجود و فعال است (نشانه‌ی اتمام آپلود)
        btn_apply_status = await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (!btn) return { exists: false };
            return {
                exists: true,
                enabled: !btn.disabled,
                visible: btn.getBoundingClientRect().width > 0
            };
        }''')

        if btn_apply_status.get('exists') and btn_apply_status.get('enabled'):
            _log(prefix, f"✓ آپلود همه با موفقیت کامل شد (alerts_seen={alerts_seen_cumulative})")
            result["success"] = True
            return result
        else:
            _log(prefix, f"#btnApplyAll موجود/فعال نیست — آپلود کامل نشده؟ وضعیت: {btn_apply_status}", 'warning')
            snap = await page_state_snapshot(page, prefix)
            _log(prefix, f"وضعیت صفحه: {snap}", 'warning')
            # اگر alertها دیده شدند، احتمالاً آپلود موفق بوده ولی دکمه هنوز فعال نشده
            if alerts_seen_cumulative >= expected_file_count:
                _log(prefix, "تعداد alertها کامل بود — موفق فرض می‌کنیم")
                result["success"] = True
                return result
            await asyncio.sleep(3)

    # پایان همه‌ی retryها
    if not result["error"]:
        result["error_type"] = "exhausted"
        result["error"] = f"آپلود همه بعد از {max_retries} تلاش ناموفق"
    return result


# =========================================================
# ۷. 🆕 کلیک تایید همه (#btnApplyAll) — کاملاً بازنویسی‌شده
# =========================================================

async def click_apply_all_with_retry(
    page,
    expected_count: int,
    bot: Bot = None,
    user_id: int = None,
    doc_title: str = "",
    max_retries: int = MAX_APPLY_ALL_RETRIES,
    prefix: str = "UPLOAD") -> Dict[str, Any]:
    """
    کلیک روی «تایید همه» (#btnApplyAll) + انتظار تایید هر پیوست.

    مسیر دقیق (طبق فایل توضیحات):
      ۱. قبل از کلیک: تضمین viewModel.loading === false + انگولار آرام
      ۲. کلیک با ۴ روش فال‌بک AngularJS (applyAllAttachment)
      ۳. تشخیص خطای ورود همزمان:
         → اطلاع به مدیر + لاگین مجدد
         → صبر + کلیک مجدد #btnApplyAll (بدون حذف فایل‌ها)
      ۴. انتظار برای alert "پیوست مورد نظر با موفقیت تایید شد" به تعداد expected_count
         (شمارش تجمعی)
      ۵. انتظار محو شدن alertها
      ۶. تضمین نهایی: viewModel.loading === false

    ⭐ تفاوت کلیدی با نسخه‌ی قبل:
      - اگر خطای غیر از ورود همزمان رخ دهد، فایل‌ها را حذف نمی‌کند
      - فقط گزارش خطا می‌دهد و error_type برمی‌گرداند
      - در خطای ورود همزمان، فقط منتظر لاگین مجدد می‌ماند و دوباره کلیک می‌کند

    بازگشت:
      {
        "success": bool,
        "error_type": str|None,
        "error": str|None,
        "alerts_seen": int,
        "method": str,
      }
    """
    result = {
        "success": False,
        "error_type": None,
        "error": None,
        "alerts_seen": 0,
        "method": None,
    }

    for attempt in range(1, max_retries + 1):
        _log(prefix, f"━━━ تایید همه [{doc_title}] — تلاش {attempt}/{max_retries} ━━━")

        # ─── ۰. بررسی انقضای نشست ───
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            _log(prefix, "نشست قبل از تایید همه تمدید شد — تلاش مجدد")
            await asyncio.sleep(3)
            continue

        # ─── ۱. تضمین آرام‌بودن صفحه ───
        await wait_for_angular_idle(page)
        for _ in range(15):
            vm_loading = await _get_view_model_loading_state(page)
            if vm_loading is False or vm_loading is None:
                break
            _log(prefix, "viewModel.loading === true — صبر قبل از تایید همه", 'debug')
            await asyncio.sleep(1)

        await asyncio.sleep(INTER_STEP_DELAY)

        # ─── ۲. بررسی دکمه ───
        btn_status = await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (!btn) return { exists: false };
            const rect = btn.getBoundingClientRect();
            return {
                exists: true,
                enabled: !btn.disabled,
                visible: rect.width > 0 && rect.height > 0
            };
        }''')

        if not btn_status.get('exists'):
            result["error_type"] = "click_failed"
            result["error"] = "دکمه #btnApplyAll پیدا نشد"
            _log(prefix, result["error"], 'error')
            snap = await page_state_snapshot(page, prefix)
            _log(prefix, f"وضعیت صفحه: {snap}", 'warning')
            await asyncio.sleep(3)
            continue

        if not btn_status.get('enabled'):
            _log(prefix, "دکمه #btnApplyAll غیرفعال است — ممکن است آپلود هنوز در حال انجام باشد", 'warning')
            # منتظر فعال شدن
            for _w in range(30):
                await asyncio.sleep(2)
                enabled = await page.evaluate('''() => {
                    const btn = document.querySelector('#btnApplyAll');
                    return btn && !btn.disabled;
                }''')
                if enabled:
                    break
                if await detect_concurrent_login_popup(page):
                    result["error_type"] = "session"
                    result["error"] = "خطای ورود همزمان حین انتظار برای فعال‌شدن ApplyAll"
                    _log(prefix, result["error"], 'error')
                    await check_and_handle_expiry(page, bot, user_id)
                    break
            else:
                _log(prefix, "دکمه #btnApplyAll بعد از ۶۰ ثانیه همچنان غیرفعال", 'warning')
                # چک کن آیا اصلاً آپلود تمام شده
                snap = await page_state_snapshot(page, prefix)
                _log(prefix, f"وضعیت صفحه: {snap}", 'warning')
                continue

            if result["error_type"] == "session":
                await asyncio.sleep(3)
                continue

        # ─── ۳. کلیک با ۴ روش فال‌بک AngularJS ───
        click_method = await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (!btn || btn.disabled) return 'disabled_or_missing';

            // روش ۱: فراخوانی مستقیم applyAllAttachment از scope
            try {
                if (typeof angular !== 'undefined') {
                    const ngEl = angular.element(btn);
                    if (ngEl && ngEl.scope) {
                        const scope = ngEl.scope();
                        if (scope && scope.actions && typeof scope.actions.applyAllAttachment === 'function') {
                            scope.$apply(() => { scope.actions.applyAllAttachment(); });
                            return 'method_1_scope_direct';
                        }
                    }
                }
            } catch(e) { console.log('[ApplyAll] Method 1 failed:', e); }

            // روش ۲: $eval روی ng-click
            try {
                if (typeof angular !== 'undefined') {
                    const ngEl = angular.element(btn);
                    if (ngEl && ngEl.scope) {
                        const scope = ngEl.scope();
                        const ngClick = btn.getAttribute('ng-click');
                        if (ngClick && scope) {
                            scope.$apply(() => { scope.$eval(ngClick); });
                            return 'method_2_ng_click_eval';
                        }
                    }
                }
            } catch(e) { console.log('[ApplyAll] Method 2 failed:', e); }

            // روش ۳: mouse events + $apply روی rootScope
            try {
                btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                if (typeof angular !== 'undefined') {
                    const rootScope = angular.element(document).scope();
                    if (rootScope) rootScope.$apply();
                }
                return 'method_3_mouse_events';
            } catch(e) { console.log('[ApplyAll] Method 3 failed:', e); }

            // فال‌بک: کلیک ساده
            btn.click();
            return 'fallback_simple_click';
        }''')

        result["method"] = click_method
        _log(prefix, f"تایید همه: کلیک با روش {click_method}")

        if click_method == 'disabled_or_missing':
            _log(prefix, "دکمه در لحظه کلیک غیرفعال یا ناپدید شده", 'warning')
            await asyncio.sleep(3)
            continue

        # ─── ۴. انتظار برای پاسخ سامانه ───
        # ابتدا ۳ ثانیه صبر کن تا عملیات شروع شود
        await asyncio.sleep(3)

        # بررسی خطای ورود همزمان فوری
        if await detect_concurrent_login_popup(page):
            result["error_type"] = "session"
            result["error"] = "خطای ورود همزمان بعد از کلیک تایید همه"
            _log(prefix, result["error"], 'error')
            await check_and_handle_expiry(page, bot, user_id)
            # طبق فایل توضیحات: بعد از لاگین مجدد، دوباره روی #btnApplyAll کلیک کن
            _log(prefix, "بعد از لاگین مجدد — تلاش مجدد برای تایید همه")
            await asyncio.sleep(5)
            continue

        # ─── ۵. انتظار نوار لودینگ ───
        await wait_for_loading_bar(page, timeout=LOADING_BAR_TIMEOUT, prefix=prefix)

        # بررسی خطای ورود همزمان بعد از لودینگ
        if await detect_concurrent_login_popup(page):
            result["error_type"] = "session"
            result["error"] = "خطای ورود همزمان بعد از لودینگ تایید همه"
            _log(prefix, result["error"], 'error')
            await check_and_handle_expiry(page, bot, user_id)
            _log(prefix, "بعد از لاگین مجدد — تلاش مجدد برای تایید همه")
            await asyncio.sleep(5)
            continue

        # ─── ۶. انتظار برای alert موفقیت تایید (شمارش تجمعی) ───
        alerts_seen_cumulative = 0
        last_logged_count = 0
        no_progress_seconds = 0
        no_progress_warning_logged = False  # ⭐ flag برای جلوگیری از لاگ تکراری
        snapshot_logged = False  # ⭐ flag برای فقط یک‌بار لاگ snapshot

        _log(prefix, f"انتظار برای {expected_count} alert موفقیت تایید (با شمارش تجمعی)...")

        for wait_i in range(APPLY_ALL_SETTLE_TIMEOUT * 2):
            if wait_i % 4 == 0 and bot and user_id:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
                if had_expiry:
                    _log(prefix, "نشست حین انتظار alert تایید تمدید شد")
                    await asyncio.sleep(1)

            # بررسی خطای ورود همزمان
            if await detect_concurrent_login_popup(page):
                result["error_type"] = "session"
                result["error"] = "خطای ورود همزمان حین انتظار alert تایید"
                _log(prefix, result["error"], 'error')
                await check_and_handle_expiry(page, bot, user_id)
                _log(prefix, "بعد از لاگین مجدد — تلاش مجدد برای تایید همه")
                break  # break inner loop, retry outer

            # شمارش alertهای تایید
            current_count = await _count_alerts(page, "پیوست مورد نظر با موفقیت تایید شد")

            if current_count > alerts_seen_cumulative:
                alerts_seen_cumulative = current_count

            if alerts_seen_cumulative > last_logged_count:
                _log(prefix, f"alert موفقیت تایید: {alerts_seen_cumulative}/{expected_count} دیده شد")
                last_logged_count = alerts_seen_cumulative
                no_progress_seconds = 0
            else:
                no_progress_seconds += 1

            if alerts_seen_cumulative >= expected_count:
                _log(prefix, f"✓ تمام {expected_count} alert موفقیت تایید دیده شد")
                break

            # بررسی viewModel.loading
            vm_loading = await _get_view_model_loading_state(page)
            if vm_loading is True:
                no_progress_seconds = 0
                no_progress_warning_logged = False
                snapshot_logged = False
            elif vm_loading is False and no_progress_seconds > 30:
                # ⭐ فقط یک بار لاگ کن — نه هر iteration
                if not no_progress_warning_logged:
                    _log(prefix, f"viewModel.loading === false و ۳۰ ثانیه بدون پیشرفت (alerts_seen={alerts_seen_cumulative}/{expected_count})", 'warning')
                    no_progress_warning_logged = True
                    if alerts_seen_cumulative > 0:
                        _log(prefix, f"ادامه با {alerts_seen_cumulative} alert دیده‌شده")
                        break
                    # اگر هیچ alertی دیده نشده و خطا هم نیست، شاید همه‌چیز تمام شده
                    # و alertها سریع محو شده‌اند
                    btn_apply_disabled = await page.evaluate('''() => {
                        const btn = document.querySelector('#btnApplyAll');
                        return btn ? btn.disabled : null;
                    }''')
                    _log(prefix, f"#btnApplyAll disabled={btn_apply_disabled}", 'info')
                    if btn_apply_disabled:
                        _log(prefix, "#btnApplyAll غیرفعال شده — ممکن است تایید تمام شده باشد", 'warning')
                        break
                    else:
                        # دکمه ApplyAll هنوز فعال است ولی alertها دیده نشدند
                        # یک snapshot بگیریم
                        if not snapshot_logged:
                            snap = await page_state_snapshot(page, prefix)
                            _log(prefix, f"وضعیت صفحه (snapshot): {snap}", 'warning')
                            snapshot_logged = True
                
                # ⭐ اگر ۶۰ ثانیه بدون پیشرفت بود — break کن
                if no_progress_seconds > 60:
                    _log(prefix, f"۶۰ ثانیه بدون پیشرفت — توقف انتظار برای alert تایید (alerts_seen={alerts_seen_cumulative}/{expected_count})", 'warning')
                    if not snapshot_logged:
                        snap = await page_state_snapshot(page, prefix)
                        _log(prefix, f"وضعیت نهایی صفحه: {snap}", 'warning')
                    break

            # بررسی خطای دیگر
            error_text = await get_and_close_error_popup_text(page)
            if error_text:
                error_type = detect_error_type(error_text)
                _log(prefix, f"خطا در تایید همه: {error_text} (نوع: {error_type})", 'error')
                if error_type == "session":
                    result["error_type"] = "session"
                    result["error"] = error_text
                    await check_and_handle_expiry(page, bot, user_id)
                    break
                else:
                    # خطای غیر از ورود همزمان — حذف نکن، فقط گزارش بده
                    result["error_type"] = error_type
                    result["error"] = error_text
                    result["alerts_seen"] = alerts_seen_cumulative
                    _log(prefix, f"خطای غیر از ورود همزمان — بدون حذف، گزارش خطا", 'warning')
                    return result

            await asyncio.sleep(0.5)
        else:
            # تایم‌اوت inner loop
            _log(prefix, f"تایم‌اوت انتظار alert تایید — دیده‌شده: {alerts_seen_cumulative}/{expected_count}", 'warning')
            if alerts_seen_cumulative >= max(1, expected_count // 2):
                _log(prefix, f"ادامه با {alerts_seen_cumulative} alert (بیش از نیمی از مورد انتظار)")
            else:
                snap = await page_state_snapshot(page, prefix)
                _log(prefix, f"وضعیت صفحه هنگام تایم‌اوت: {snap}", 'warning')
                result["error_type"] = "timeout"
                result["error"] = f"تایم‌اوت انتظار alert تایید — {alerts_seen_cumulative}/{expected_count}"
                result["alerts_seen"] = alerts_seen_cumulative
                # retry outer
                continue

        # اگر در inner loop خطای session داشتیم، retry outer
        if result["error_type"] == "session":
            await asyncio.sleep(3)
            continue

        result["alerts_seen"] = alerts_seen_cumulative

        # ─── ۷. انتظار برای محو شدن alertها ───
        _log(prefix, "انتظار برای محو شدن alertهای تایید...")
        for dismiss_i in range(ALERT_DISMISS_TIMEOUT * 2):
            current_alerts = await _count_alerts(page, "پیوست مورد نظر با موفقیت تایید شد")
            if current_alerts == 0:
                _log(prefix, "✓ تمام alertهای تایید محو شدند")
                break
            if dismiss_i % 10 == 0:
                _log(prefix, f"هنوز {current_alerts} alert تایید در صفحه", 'debug')
            await asyncio.sleep(0.5)

        # ─── ۸. تضمین نهایی: viewModel.loading === false ───
        await wait_for_angular_idle(page)
        for _final in range(15):
            vm_loading = await _get_view_model_loading_state(page)
            if vm_loading is False or vm_loading is None:
                break
            _log(prefix, "viewModel.loading === true — صبر نهایی", 'debug')
            await asyncio.sleep(1)

        # ─── ۹. موفقیت ───
        if alerts_seen_cumulative >= expected_count:
            _log(prefix, f"✓✓ تایید همه با موفقیت کامل شد (alerts_seen={alerts_seen_cumulative})")
            result["success"] = True
            return result
        elif alerts_seen_cumulative >= max(1, expected_count // 2):
            _log(prefix, f"تایید همه با موفقیت نسبی ({alerts_seen_cumulative}/{expected_count})", 'warning')
            result["success"] = True
            return result
        else:
            _log(prefix, f"تایید همه کامل نشد — فقط {alerts_seen_cumulative}/{expected_count} alert", 'warning')
            # بدون fallback به حذف — فقط retry
            await asyncio.sleep(3)

    # پایان همه‌ی retryها
    if not result["error"]:
        result["error_type"] = "exhausted"
        result["error"] = f"تایید همه بعد از {max_retries} تلاش ناموفق (alerts_seen={result['alerts_seen']})"
    return result


# =========================================================
# ۸. توابع قدیمی wait_for_upload_confirmation و wait_for_alerts_to_disappear
# (حفظ برای سازگاری با کدهای فراخوانی قدیمی)
# =========================================================

async def wait_for_upload_confirmation(
    page,
    expected_count: int,
    bot: Bot = None,
    user_id: int = None,
    timeout_sec: int = UPLOAD_CONFIRM_TIMEOUT,
    prefix: str = "UPLOAD") -> bool:
    """(منسوخ) — شمارش تجمعی در click_upload_all_with_retry انجام می‌شود."""
    # این تابع فقط برای سازگاری نگه داشته شده
    cumulative = 0
    for i in range(timeout_sec * 2):
        if i % 4 == 0 and bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                await asyncio.sleep(1)
        count = await _count_alerts(page, "پیوست مورد نظر با موفقیت ثبت گردید")
        if count > cumulative:
            cumulative = count
        if cumulative >= expected_count:
            return True
        await asyncio.sleep(0.5)
    return False


async def wait_for_alerts_to_disappear(
    page,
    bot: Bot = None,
    user_id: int = None,
    timeout_sec: int = ALERT_DISMISS_TIMEOUT,
    prefix: str = "UPLOAD") -> bool:
    """(منسوخ) — محو شدن alertها در click_upload_all_with_retry انجام می‌شود."""
    for i in range(timeout_sec * 2):
        if i % 8 == 0 and bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                await asyncio.sleep(1)
        count = await _count_alerts(page, "پیوست مورد نظر با موفقیت ثبت گردید")
        if count == 0:
            await asyncio.sleep(1)
            return True
        await asyncio.sleep(0.5)
    return False


# =========================================================
# ۹. تابع اصلی: آپلود مقاوم یک ردیف (بازنویسی‌شده)
# =========================================================

async def resilient_upload_attachment(
    page,
    doc_title: str,
    image_paths: List[str],
    bot: Bot,
    user_id: int,
    prefix: str = "LAVAYEH",
    form_fill_fn: Optional[Callable] = None,
    task_key: Optional[str] = None,
    incomplete_tasks: Optional[dict] = None) -> Dict[str, Any]:
    """
    آپلود مقاوم یک ردیف پیوست — بازنویسی‌شده بر اساس فایل توضیحات منضمات.

    مسیر دقیق:
      ۱. آماده‌سازی فایل‌ها (compress + JPEG)
      ۲. بررسی انقضای نشست
      ۳. پر کردن فرم (#attachmentType, #txtNo, #txtName, #txt001, #incAttach0)
      ۴. کلیک #btnSaveDoc + انتظار لودینگ + بستن پاپ‌آپ موفقیت
      ۵. کلیک editDocument روی ردیف + انتظار آپلودر
      ۶. انتخاب فایل‌ها با #files_multipleFileUploader
      ۷. 🆕 کلیک #btnUploadAll با click_upload_all_with_retry (کامل بازنویسی‌شده)
         - شامل انتظار کامل اتمام آپلود + شمارش تجمعی alertها
         - تشخیص خطای ورود همزمان → خروج با error_type='session'
      ۸. اگر خطای session:
         - حذف کامل ردیف (طبق فایل توضیحات)
         - continue به تلاش بعدی
      ۹. 🆕 کلیک #btnApplyAll با click_apply_all_with_retry (کامل بازنویسی‌شده)
         - شامل انتظار کامل تایید + شمارش تجمعی alertها
         - در خطای session: فقط retry بدون حذف
         - در خطای غیر session: خروج با error_type مشخص (بدون حذف)
      ۱۰. در صورت موفقیت: clear checkpoint و بازگشت

    ⭐ تغییر کلیدی: در خطای ApplyAll غیر از session، فایل‌ها حذف نمی‌شوند.
    قبلاً این کار باعث می‌شد پیوست‌ها پاک شوند و برگردد به آماده‌سازی.
    """
    result = {"success": False, "error": None, "error_type": None, "attempts": 0}

    # مرحله صفر: آماده‌سازی فایل‌ها
    prepared_paths, validation_errors = await prepare_files_for_upload(
        image_paths, bot, user_id, prefix, compress=True, convert_to_jpeg=True)

    if not prepared_paths:
        result["error"] = "هیچ فایل معتبری برای آپلود وجود ندارد"
        result["error_type"] = "validation"
        if validation_errors:
            result["error"] += ": " + "; ".join(e["error"] for e in validation_errors)
        return result

    if validation_errors:
        _log(prefix, f"{len(validation_errors)} فایل نامعتبر حذف شد، {len(prepared_paths)} فایل باقی‌مانده", 'warning')

    image_count = len(prepared_paths)

    for attempt in range(1, MAX_UPLOAD_ATTEMPTS + 1):
        result["attempts"] = attempt
        _log(prefix, f"━━━━━━━ آپلود [{doc_title}] - تلاش {attempt}/{MAX_UPLOAD_ATTEMPTS} ━━━━━━━")

        try:
            # ذخیره checkpoint
            if task_key and incomplete_tasks is not None:
                _save_checkpoint(incomplete_tasks, task_key,
                                f"آپلود [{doc_title}] (تلاش {attempt})",
                                {"doc_title": doc_title, "image_count": image_count, "attempt": attempt})

            # بررسی انقضای نشست
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, f"نشست قبل از آپلود [{doc_title}] تمدید شد")
                await asyncio.sleep(2)

            # ─── مرحله ۱: پر کردن فرم ───
            if form_fill_fn:
                form_ok = await form_fill_fn(page, doc_title, prepared_paths)
                if not form_ok:
                    _log(prefix, f"form_fill_fn برای [{doc_title}] ناموفق", 'warning')
                    await asyncio.sleep(3)
                    continue
            else:
                form_ok = await _default_fill_other_attachment_form(page, doc_title, image_count)
                if not form_ok:
                    _log(prefix, f"فرم پیش‌فرض [{doc_title}] ناموفق", 'warning')
                    await asyncio.sleep(3)
                    continue

            await asyncio.sleep(INTER_STEP_DELAY)

            # ─── مرحله ۲: ذخیره سند (#btnSaveDoc) + انتظار لودینگ ───
            save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix=prefix)
            if not save_ok:
                error_text = await get_and_close_error_popup_text(page)
                error_type = detect_error_type(error_text) if error_text else "save_failed"
                _log(prefix, f"ذخیره سند [{doc_title}] ناموفق: {error_text} (نوع: {error_type})", 'error')

                if error_type == "page_count":
                    for alt_count in [image_count + 1, image_count - 1, image_count + 2]:
                        if alt_count < 1:
                            continue
                        _log(prefix, f"تلاش با تعداد صفحات جایگزین: {alt_count}")
                        await close_any_popup(page)
                        await asyncio.sleep(1)
                        if form_fill_fn:
                            await form_fill_fn(page, doc_title, prepared_paths, force_page_count=alt_count)
                        else:
                            await _default_fill_other_attachment_form(page, doc_title, alt_count)
                        save_ok2 = await click_save_doc_with_retry(page, bot, user_id, prefix=prefix)
                        if save_ok2:
                            save_ok = True
                            break
                    if not save_ok:
                        await close_any_popup(page)
                        await asyncio.sleep(3)
                        continue
                elif error_type == "session":
                    # خطای ورود همزمان در ذخیره سند — تلاش مجدد
                    _log(prefix, "خطای ورود همزمان در ذخیره سند — تلاش مجدد")
                    await asyncio.sleep(3)
                    continue
                else:
                    await close_any_popup(page)
                    await asyncio.sleep(3)
                    continue

            await asyncio.sleep(INTER_STEP_DELAY)

            # ─── مرحله ۳: کلیک editDocument روی ردیف + انتظار آپلودر ───
            edit_ok = await click_edit_document_for_title(
                page, doc_title, bot, user_id, prefix=prefix)
            if not edit_ok:
                _log(prefix, f"editDocument یا آپلودر برای [{doc_title}] ناموفق", 'warning')
                await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                await asyncio.sleep(2)
                continue

            # ─── مرحله ۴: آپلود فایل‌ها با #files_multipleFileUploader ───
            try:
                file_input = page.locator('#files_multipleFileUploader')
                await file_input.set_input_files(prepared_paths)
                _log(prefix, f"{len(prepared_paths)} فایل با #files_multipleFileUploader انتخاب شدند")
            except Exception as e:
                _log(prefix, f"خطا در انتخاب فایل: {e}", 'error')
                await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(3)

            # ─── مرحله ۵: 🆕 کلیک آپلود همه با تابع جدید ───
            upload_all_result = await click_upload_all_with_retry(
                page,
                expected_file_count=image_count,
                bot=bot,
                user_id=user_id,
                doc_title=doc_title,
                prefix=prefix)

            if not upload_all_result["success"]:
                error_type = upload_all_result.get("error_type", "unknown")
                error_msg = upload_all_result.get("error", "نامشخص")
                _log(prefix, f"آپلود همه [{doc_title}] ناموفق: {error_msg} (نوع: {error_type})", 'error')

                if error_type == "session":
                    # طبق فایل توضیحات: خطای ورود همزمان → حذف کامل ردیف + شروع از اول
                    _log(prefix, "خطای ورود همزمان — حذف کامل ردیف و شروع مجدد")
                    await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                    await asyncio.sleep(2)
                    continue
                else:
                    # خطای غیر از session — حذف ردیف و تلاش مجدد
                    _log(prefix, f"خطای غیر از session در آپلود همه — حذف و تلاش مجدد")
                    await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                    await asyncio.sleep(2)
                    continue

            # موفقیت آپلود همه — حالا تایید همه

            # ─── مرحله ۶: 🆕 کلیک تایید همه با تابع جدید ───
            apply_all_result = await click_apply_all_with_retry(
                page,
                expected_count=image_count,
                bot=bot,
                user_id=user_id,
                doc_title=doc_title,
                prefix=prefix)

            if apply_all_result["success"]:
                await close_success_popup(page)
                await asyncio.sleep(1)
                await close_error_popup(page)
                await asyncio.sleep(0.5)
                await wait_for_angular_idle(page)
                await asyncio.sleep(INTER_STEP_DELAY)

                if task_key and incomplete_tasks is not None:
                    _clear_checkpoint(incomplete_tasks, task_key)

                _log(prefix, f"✓✓✓ آپلود [{doc_title}] موفق (تلاش {attempt})")
                result["success"] = True
                return result

            # تایید همه ناموفق
            error_type = apply_all_result.get("error_type", "unknown")
            error_msg = apply_all_result.get("error", "نامشخص")
            alerts_seen = apply_all_result.get("alerts_seen", 0)

            _log(prefix, f"تایید همه [{doc_title}] ناموفق: {error_msg} (نوع: {error_type}, alerts_seen={alerts_seen})", 'error')

            if error_type == "session":
                # طبق فایل توضیحات: فقط تلاش مجدد بدون حذف
                _log(prefix, "خطای ورود همزمان در تایید همه — تلاش مجدد بدون حذف")
                # اما در click_apply_all_with_retry خودش retry کرده — اگر اینجا رسیدیم یعنی واقعاً نشد
                # به تلاش بعدی resilient_upload_attachment می‌رویم
                # در این حالت هم نباید حذف کنیم
                await asyncio.sleep(3)
                # فقط در تلاش آخر حذف کنیم تا از نو شروع شود
                if attempt < MAX_UPLOAD_ATTEMPTS:
                    continue
                else:
                    # تلاش آخر — حذف و شروع مجدد کامل
                    _log(prefix, "تلاش آخر — حذف و خروج با خطا")
                    await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                    break
            else:
                # خطای غیر از session — ❌ حذف نکن، فقط گزارش بده
                # این تغییر کلیدی است که مشکل «پاک‌کردن پیوست‌ها و بازگشت به آماده‌سازی» را حل می‌کند
                _log(prefix, f"خطای غیر از session — حفظ پیوست‌ها، خروج با خطا", 'warning')
                result["error"] = f"تایید همه ناموفق: {error_msg}"
                result["error_type"] = error_type
                # ذخیره snapshot برای دیباگ
                snap = await page_state_snapshot(page, prefix)
                _log(prefix, f"وضعیت نهایی صفحه: {snap}", 'warning')
                # بدون حذف، خارج شو — کاربر/مدیر تصمیم می‌گیرد
                break

        except Exception as e:
            _log(prefix, f"استثنای آپلود [{doc_title}] (تلاش {attempt}): {e}", 'error')
            import traceback
            _log(prefix, traceback.format_exc(), 'error')
            try:
                await close_any_popup(page)
                await asyncio.sleep(2)
                # فقط در صورت استثنا حذف کن — این واقعاً یک وضعیت اضطراری است
                await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                await asyncio.sleep(2)
            except Exception as cleanup_err:
                _log(prefix, f"خطا در پاکسازی: {cleanup_err}", 'error')
            await asyncio.sleep(5)

    if not result["success"] and not result["error"]:
        result["error"] = f"آپلود [{doc_title}] پس از {MAX_UPLOAD_ATTEMPTS} تلاش ناموفق"
        result["error_type"] = "exhausted"

    if not result["success"] and task_key and incomplete_tasks is not None:
        _save_checkpoint(incomplete_tasks, task_key,
                        f"شکست نهایی آپلود [{doc_title}]",
                        {"doc_title": doc_title, "image_count": image_count,
                         "exhausted": True, "error": result["error"], "error_type": result["error_type"]})

    return result


# =========================================================
# ۱۰. فرم پیش‌فرض: سایر ضمائم
# =========================================================

async def _default_fill_other_attachment_form(page, doc_title: str, page_count: int) -> bool:
    """
    پر کردن فرم پیش‌فرض «سایر ضمائم».

    اگر page_count == 1 (تک‌برگ)، فیلد #txt001 و دکمه #incAttach0 اسکیپ می‌شوند.
    """
    # مرحله ۱: انتخاب «سایر ضمائم»
    await page.evaluate('''() => {
        const sel = document.querySelector('#attachmentType');
        if (sel) {
            const opts = Array.from(sel.options);
            const opt = opts.find(o => o.text.includes("ساير ضمائم") || o.text.includes("سایر ضمائم"));
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event("change"));
            }
        }
    }''')
    await asyncio.sleep(3)

    # مرحله ۲: شماره مدرک = ۰
    await page.evaluate('''() => {
        const inputs = Array.from(document.querySelectorAll('input#txtNo'));
        if (inputs.length > 0) {
            inputs[0].value = "0";
            inputs[0].dispatchEvent(new Event("input", { bubbles: true }));
        }
    }''')

    # مرحله ۳: عنوان مدرک
    escaped_title = doc_title.replace("`", "'").replace("\\", "").replace('"', '\\"')
    await page.evaluate(f'''() => {{
        const inputs = Array.from(document.querySelectorAll('input#txtName'));
        if (inputs.length > 0) {{
            inputs[0].value = "{escaped_title}";
            inputs[0].dispatchEvent(new Event("input", {{ bubbles: true }}));
        }}
    }}''')

    # مرحله ۴: تعداد صفحات و افزودن پیوست
    if page_count > 1:
        await page.evaluate(f'''() => {{
            const inp = document.querySelector('#txt001');
            if (inp) {{
                inp.value = "{page_count}";
                inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            }}
        }}''')

        await page.evaluate('''() => {
            const btn = document.querySelector('#incAttach0');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(3)
    else:
        _log("UPLOAD", f"حالت تک‌برگ ({page_count} فایل) — #txt001 و #incAttach0 اسکیپ شدند")

    return True


# =========================================================
# ۱۱. آپلود گروهی
# =========================================================

async def resilient_upload_attachment_groups(
    page,
    groups: List[Dict[str, Any]],
    bot: Bot,
    user_id: int,
    prefix: str = "LAVAYEH",
    form_fill_fn: Optional[Callable] = None,
    task_key: Optional[str] = None,
    incomplete_tasks: Optional[dict] = None) -> Dict[str, Any]:
    """
    آپلود مقاوم چندین گروه پیوست.
    بازگشت: {"success": bool, "failed_groups": [...], "successful_groups": [...]}
    """
    overall = {"success": True, "failed_groups": [], "successful_groups": []}
    completed = 0
    total = len(groups)

    for idx, group in enumerate(groups):
        title = group.get("title", "مستندات")
        paths = group.get("paths", [])

        if not paths:
            _log(prefix, f"گروه [{title}] فایلی ندارد، رد شدن")
            overall["successful_groups"].append(title)
            completed += 1
            continue

        # اگر این گروه دوم به بعد است، دکمه «پیوست جدید» را بزن
        if completed > 0:
            _log(prefix, f"کلیک «پیوست جدید» قبل از گروه {completed+1}/{total}: [{title}]")
            await asyncio.sleep(2)
            clicked = await page.evaluate('''() => {
                const btn = document.querySelector('#newAttachmentType');
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if not clicked:
                clicked = await soft_click_if_exists(page, "پیوست جدید")
            if clicked:
                await asyncio.sleep(3)
                await wait_for_angular_idle(page)
                await asyncio.sleep(1)
            else:
                _log(prefix, "دکمه «پیوست جدید» پیدا نشد — ادامه بدون کلیک", 'warning')

        _log(prefix, f"آپلود گروه {completed+1}/{total}: [{title}] ({len(paths)} فایل)")

        upload_result = await resilient_upload_attachment(
            page, title, paths, bot, user_id, prefix,
            form_fill_fn=form_fill_fn,
            task_key=task_key,
            incomplete_tasks=incomplete_tasks)

        if upload_result["success"]:
            overall["successful_groups"].append(title)
            completed += 1

            if task_key and incomplete_tasks is not None:
                save_upload_checkpoint(
                    incomplete_tasks, task_key,
                    completed_titles=overall["successful_groups"],
                    current_group=None,
                    total_groups=total)
        else:
            overall["success"] = False
            overall["failed_groups"].append({
                "title": title,
                "error": upload_result.get("error", "نامشخص"),
                "error_type": upload_result.get("error_type", "نامشخص"),
                "attempts": upload_result.get("attempts", 0),
            })
            # ادامه با گروه بعدی به‌جای break — تا کاربر ببیند کدام گروه‌ها ناموفق بودند
            _log(prefix, f"گروه [{title}] ناموفق — ادامه با گروه بعدی", 'warning')

    return overall


# =========================================================
# ۱۲. مدیریت نقاط بازیابی (checkpoint)
# =========================================================

def _save_checkpoint(incomplete_tasks: dict, task_key: str, step: str, extra_data: dict = None):
    if task_key in incomplete_tasks:
        incomplete_tasks[task_key]["last_completed_step"] = step
        incomplete_tasks[task_key]["upload_checkpoint"] = extra_data or {}
        incomplete_tasks[task_key]["updated_at"] = time.time()


def _clear_checkpoint(incomplete_tasks: dict, task_key: str):
    if task_key in incomplete_tasks:
        incomplete_tasks[task_key].pop("upload_checkpoint", None)


def save_upload_checkpoint(
    incomplete_tasks: dict,
    task_key: str,
    completed_titles: list,
    current_group: str = None,
    total_groups: int = 0):
    if task_key in incomplete_tasks:
        incomplete_tasks[task_key]["upload_checkpoint"] = {
            "completed_groups": completed_titles,
            "current_group": current_group,
            "total_groups": total_groups,
            "saved_at": time.time(),
        }
        incomplete_tasks[task_key]["updated_at"] = time.time()


def get_upload_checkpoint(incomplete_tasks: dict, task_key: str) -> Optional[dict]:
    if task_key in incomplete_tasks:
        checkpoint = incomplete_tasks[task_key].get("upload_checkpoint")
        if checkpoint:
            saved_at = checkpoint.get("saved_at", 0)
            age_hours = (time.time() - saved_at) / 3600
            if age_hours > CHECKPOINT_EXPIRY_HOURS:
                _log("UPLOAD", f"checkpoint منقضی ({age_hours:.1f} ساعت)", 'warning')
                return None
            return checkpoint
    return None


def build_incomplete_task_entry(
    bill_no: str,
    user_id: int,
    task_type: str,
    next_step: str,
    task_data: dict,
    last_completed_step: str,
    attachment_groups: list = None) -> dict:
    entry = {
        "bill_no": bill_no,
        "user_id": user_id,
        "type": task_type,
        "last_completed_step": last_completed_step,
        "next_step": next_step,
        "task_data": task_data,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    if attachment_groups is not None:
        entry["attachment_groups"] = attachment_groups
    return entry


# =========================================================
# ۱۳. توابع کمکی عمومی برای تشخیص خطای ورود همزمان در تمام بخش‌ها
# =========================================================

async def check_concurrent_login_all_sections(page, bot: Bot, user_id: int, prefix: str = "GLOBAL") -> bool:
    """
    🔔 طبق فایل توضیحات (خط آخر):
    «خطای ورود همزمان را به تمام بخش‌های لایحه و اعلام وکالت و اظهارنامه
     و استعلامات و زیرمجموعه‌های بخش‌های در ثبت اضافه کن»

    این تابع را می‌توان در هر نقطه از سناریوها فراخوانی کرد تا خطای
    ورود همزمان تشخیص داده شود و به مدیر اطلاع داده شود.

    بازگشت: True اگر خطای ورود همزمان تشخیص داده شد (و مدیریت شد).
    """
    if await detect_concurrent_login_popup(page):
        _log(prefix, "🚨 خطای ورود همزمان تشخیص داده شد — اطلاع به مدیر برای لاگین مجدد", 'error')
        await check_and_handle_expiry(page, bot, user_id)
        return True
    return False
