r"""
api_direct.py — استعلام سریع تعداد پیوست‌ها بدون صف‌بندی

این ماژول استعلام PRE_CHECK (شمارش منضمات) را خارج از job_queue و
بدون مسدودسازی مرورگر اصلی انجام می‌دهد.

استراتژی:
  ۱) صفحه اختصاصی مرورگر (همان session) → بدون انتظار در صف
  ۲) کش نقاط انتهایی API برای درخواست‌های بعدی (Phase 2)
  ۳) فال‌بک خودکار به job_queue در صورت هرگونه خطا
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Optional
from urllib.parse import unquote

import aiohttp
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from browser_helpers import force_click_by_text, is_login_redirect_url
from config import FEES

logger = logging.getLogger(__name__)

BASE_URL = "https://sakha2.adliran.ir"
SAFE_URL = BASE_URL + "/Offices/Index"
ENDPOINTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discovered_endpoints.json")

_semaphore = asyncio.Semaphore(2)
_last_request_time = 0.0
MIN_REQUEST_INTERVAL = 1.0


class FastCheckError(Exception):
    pass


class SessionExpiredError(FastCheckError):
    pass


class PetitionNotFoundError(FastCheckError):
    pass


class InvalidTrackingCodeError(FastCheckError):
    pass


class EndpointsNotDiscovered(FastCheckError):
    pass


class APIError(FastCheckError):
    pass


async def fast_pre_check(
    tracking_code: str,
    category: str,
    subcategory: Optional[str] = None,
    user_id: int = None,
    bot=None
) -> int:
    async with _semaphore:
        await _rate_limit()
        try:
            count = await _try_api_direct(tracking_code, category, subcategory)
            logger.info(f"[FAST-CHECK] API Direct: {tracking_code} -> {count}")
            return count
        except (EndpointsNotDiscovered, APIError) as e:
            logger.info(f"[FAST-CHECK] API Direct failed ({e}) -> trying page")
        except SessionExpiredError:
            raise
        try:
            count = await _do_page_check(tracking_code, category, subcategory, user_id, bot)
            logger.info(f"[FAST-CHECK] Page: {tracking_code} -> {count}")
            return count
        except SessionExpiredError:
            raise
        except PetitionNotFoundError:
            raise
        except InvalidTrackingCodeError:
            raise
        except Exception as e:
            logger.error(f"[FAST-CHECK] Page failed: {e}")
            raise FastCheckError(str(e))


def _load_endpoints() -> dict:
    try:
        if os.path.exists(ENDPOINTS_FILE):
            with open(ENDPOINTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"[FAST-CHECK] Error loading endpoints: {e}")
    return {}


def _save_endpoints(endpoints: dict):
    try:
        with open(ENDPOINTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(endpoints, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[FAST-CHECK] Error saving endpoints: {e}")


def _get_category_key(category: str, subcategory: Optional[str] = None) -> str:
    return f"{category}/{subcategory}" if subcategory else category


async def _get_cookies() -> dict:
    if not runtime_state.browser_context:
        raise FastCheckError("مرورگر هنوز راه‌اندازی نشده")
    cookies = await runtime_state.browser_context.cookies()
    return {c['name']: c['value'] for c in cookies}


async def _try_api_direct(tracking_code: str, category: str, subcategory: Optional[str]) -> int:
    endpoints = _load_endpoints()
    key = _get_category_key(category, subcategory)
    if key not in endpoints:
        raise EndpointsNotDiscovered(f"endpoints for '{key}' not cached")
    ep = endpoints[key]
    cookies = await _get_cookies()
    headers = {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
    }
    async with aiohttp.ClientSession() as session:
        search_url = ep['search_url']
        if not search_url.startswith('http'):
            search_url = BASE_URL + search_url
        search_body = _prepare_body(ep.get('search_body_template', {}), tracking_code)
        try:
            async with session.post(search_url, cookies=cookies, headers=headers, data=search_body, timeout=aiohttp.ClientTimeout(total=15), ssl=False) as resp:
                if resp.status in (401, 403):
                    raise SessionExpiredError("Session expired")
                if resp.status != 200:
                    raise APIError(f"Search failed: HTTP {resp.status}")
                ct = resp.headers.get('Content-Type', '')
                if 'json' in ct:
                    search_data = await resp.json()
                else:
                    html = await resp.text()
                    if 'یافت نشد' in html:
                        raise PetitionNotFoundError(f"No petition: {tracking_code}")
                    search_data = html
            attach_url = ep['attachments_url']
            if not attach_url.startswith('http'):
                attach_url = BASE_URL + attach_url
            attach_body = _prepare_attach_body(ep.get('attachments_body_template', {}), tracking_code, search_data)
            async with session.post(attach_url, cookies=cookies, headers=headers, data=attach_body, timeout=aiohttp.ClientTimeout(total=15), ssl=False) as resp:
                if resp.status in (401, 403):
                    raise SessionExpiredError("Session expired")
                if resp.status != 200:
                    raise APIError(f"Attachments failed: HTTP {resp.status}")
                ct = resp.headers.get('Content-Type', '')
                if 'json' in ct:
                    return _count_from_json(await resp.json())
                else:
                    return _count_from_html(await resp.text())
        except aiohttp.ClientError as e:
            raise APIError(f"Network error: {e}")


def _prepare_body(template, tracking_code: str) -> str:
    if isinstance(template, dict):
        return json.dumps(template).replace('{{TRACKING_CODE}}', tracking_code)
    return json.dumps({})


def _prepare_attach_body(template, tracking_code: str, search_data) -> str:
    if isinstance(template, dict):
        body = json.dumps(template).replace('{{TRACKING_CODE}}', tracking_code)
        if isinstance(search_data, dict):
            pid = search_data.get('id', search_data.get('petitionId', ''))
            if pid:
                body = body.replace('{{PETITION_ID}}', str(pid))
        return body
    return json.dumps({})


def _count_from_json(data) -> int:
    rows = data if isinstance(data, list) else data.get('data', data.get('rows', data.get('items', [])))
    if not isinstance(rows, list):
        return 0
    count = 0
    start = 0
    for i, item in enumerate(rows):
        title = str(item.get('title', '') or item.get('name', '') or item.get('documentTitle', ''))
        title_clean = title.replace('\u200c', ' ')
        if 'قرارداد الکترونیک' in title_clean and ('وکالت نامه' in title_clean or 'وکالتنامه' in title_clean):
            continue
        if i == 0 and start == 0 and ('امضا' in title_clean or 'امضاء' in title_clean):
            start = 1
            continue
        item_count = item.get('count', item.get('pageCount', item.get('page', 0)))
        count += int(item_count or 0)
    return count


def _count_from_html(html: str) -> int:
    tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', html, re.DOTALL)
    if not tbody_match:
        return 0
    tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_match.group(1), re.DOTALL)
    rows = []
    for tr in tr_matches:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(tds) >= 6:
            title = re.sub(r'<[^>]+>', '', tds[2]).strip()
            count_text = re.sub(r'<[^>]+>', '', tds[5]).strip()
            rows.append({'title': title, 'count': int(count_text) if count_text.isdigit() else 0})
    def is_ignored(t):
        t = t.replace('\u200c', ' ')
        return 'قرارداد الکترونیک' in t and ('وکالت نامه' in t or 'وکالتنامه' in t)
    filtered = [r for r in rows if not is_ignored(r['title'])]
    if filtered and ('امضا' in filtered[0]['title'] or 'امضاء' in filtered[0]['title']):
        filtered = filtered[1:]
    return sum(r['count'] for r in filtered)


async def _do_page_check(tracking_code, category, subcategory, user_id, bot) -> int:
    if not runtime_state.browser_context:
        raise FastCheckError("مرورگر هنوز راه‌اندازی نشده")
    page = await runtime_state.browser_context.new_page()
    discovery = _EndpointDiscovery(category, subcategory)
    discovery.attach(page)
    try:
        await page.goto(SAFE_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        is_login = await page.query_selector('#txtUsername')
        if is_login or is_login_redirect_url(page.url):
            raise SessionExpiredError("نشست منقضی")

        # ── ناوبری به بخش مورد نظر ──────────────────────────────
        nav_map = {
            "لایحه": ["ارایه و پیگیری لایحه"],
            "اظهارنامه": ["ارایه و پیگیری اظهارنامه"],
            "شکواییه": ["ارایه و پیگیری شکواییه"],
            "دادخواست بدوی": ["ارایه و پیگیری دادخواست", "دادخواست بدوی"],
            "دعاوی دادگاههای صلح": ["دعاوی دادگاههای صلح", "دعاوی حقوقی"],
            "دعاوی اعتراضی": ["دعاوی اعتراضی", subcategory],
            "دعاوی طاری": ["ارایه و پیگیری دعاوی طاری", subcategory],
            "دیوان عدالت اداری": ["دیوان عدالت اداری", subcategory],
            "شورای حل اختلاف": ["شورای حل اختلاف (صلح و سازش)", subcategory],
        }
        steps = nav_map.get(category, [])
        if not steps:
            raise FastCheckError(f"دسته نامشخص: {category}")

        for i, step in enumerate(steps):
            if not step:
                continue
            await force_click_by_text(page, step)
            await asyncio.sleep(2 if i < len(steps) - 1 else 5)

        # لایحه: انتخاب رادیو #rdbGetPetition (value=2) و ورود کد رهگیری
        if category == "لایحه" or (
            category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
        ):
            # کلیک روی رادیوباتن استعلام لایحه (#rdbGetPetition)
            radio_clicked = await page.evaluate('''() => {
                const radio = document.querySelector('#rdbGetPetition');
                if (radio) { radio.click(); return true; }
                return false;
            }''')
            if not radio_clicked:
                # فال‌بک: تلاش با انتخاب متن
                await force_click_by_text(page, "جستجوی لایحه")
            await asyncio.sleep(4)

        # ── وارد کردن کد رهگیری ────────────────────────────────
        try:
            await page.wait_for_selector('#txtPetitionNo, #billNo', timeout=15000)
        except PlaywrightTimeoutError:
            raise FastCheckError("صفحه کارتابل لود نشد")

        # لایحه: فیلد ورودی کدرهگیری #billNo
        if (category == "لایحه" or (
            category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
        )):
            await page.fill('#billNo', tracking_code)
        else:
            await page.fill('#txtPetitionNo, #billNo', tracking_code)
        await asyncio.sleep(1.5)

        # ── کلیک جستجو (بدون fallback خطرناک) ───────────────────
        # لایحه: دکمه #btnGetJSSBill  |  سایر: #btnGetJSSPetition
        if (category == "لایحه" or (
            category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
        )):
            await page.evaluate('''() => {
                const btn = document.querySelector('#btnGetJSSBill');
                if (btn) { btn.click(); return; }
            }''')
        else:
            await page.evaluate('''() => {
                const exactBtn = document.querySelector('#btnGetJSSPetition');
                if (exactBtn) { exactBtn.click(); return; }
                const exactBtn2 = document.querySelector('#btnGetJSSBill');
                if (exactBtn2) { exactBtn2.click(); return; }
            }''')
        await asyncio.sleep(3)
        await _wait_for_loading(page, timeout=45)
        await _dismiss_error_and_retry(page)

        # ── بررسی خطای «کد رهگیری معتبر نیست» ────────────────────
        invalid_code_popup = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (popup) {
                const t = popup.innerText || "";
                if (t.includes("معتبر نیست")) return true;
            }
            return false;
        }''')
        if invalid_code_popup:
            try:
                await page.locator('.sweet-alert.showSweetAlert button.confirm').click(timeout=5000)
            except Exception:
                pass
            raise InvalidTrackingCodeError("کد رهگیری یا نوع خدمت نامعتبر است")

        # ── بررسی یافتن پرونده ───────────────────────────────────
        not_found = await page.evaluate('''() => {
            const alert = document.querySelector('.alert-danger');
            if (alert) return true;
            const text = document.body ? document.body.innerText : '';
            return text.includes('یافت نشد');
        }''')
        if not_found:
            raise PetitionNotFoundError(f"پرونده‌ای با کد {tracking_code} یافت نشد")

        is_login = await page.query_selector('#txtUsername')
        if is_login or is_login_redirect_url(page.url):
            raise SessionExpiredError("نشست منقضی")

        # ── کلیک منضمات و شمارش ─────────────────────────────────
        # بررسی وجود تب «منضمات» قبل از کلیک
        mozamatat_exists = await page.evaluate('''() => {
            const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div', 'td'];
            for (let tag of tags) {
                const elements = Array.from(document.querySelectorAll(tag));
                const target = elements.find(el => el.innerText && el.innerText.trim().includes("منضمات"));
                if (target) {
                    const rect = target.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) return true;
                }
            }
            return false;
        }''')
        if not mozamatat_exists:
            logger.info("[FAST-CHECK] تب منضمات یافت نشد — تعداد پیوست: 0")
            discovery.analyze_and_save()
            return 0

        await force_click_by_text(page, "منضمات")
        await asyncio.sleep(4)
        count = await page.evaluate('''() => {
            const tbody = document.querySelector('tbody');
            if (!tbody) return 0;
            const trs = Array.from(tbody.querySelectorAll('tr'));
            const isIgnored = (title) => {
                const t = title.replace(/\\u200c/g, ' ');
                return t.includes("قرارداد الکترونیک") &&
                       (t.includes("وکالت نامه") || t.includes("وکالتنامه"));
            };
            const rows_data = trs.map((tr, index) => {
                const tds = tr.querySelectorAll('td');
                if (tds.length >= 6) {
                    const title = tds[2].innerText.trim();
                    const countText = tds[5].innerText.trim();
                    const count = parseInt(countText) || 0;
                    return { index, title, count };
                }
                return null;
            }).filter(r => r !== null && !isIgnored(r.title));
            const has_sig = rows_data.length > 0 &&
                (rows_data[0].title.includes("امضا") || rows_data[0].title.includes("امضاء"));
            const start = has_sig ? 1 : 0;
            let sum = 0;
            for (let i = start; i < rows_data.length; i++) { sum += rows_data[i].count; }
            return sum;
        }''')
        discovery.analyze_and_save()
        return count
    finally:
        discovery.detach(page)
        try:
            await page.close()
        except Exception:
            pass


async def _navigate_to_section(page, category, subcategory):
    nav_map = {
        "لایحه": ["ارایه و پیگیری لایحه"],
        "اظهارنامه": ["ارایه و پیگیری اظهارنامه"],
        "شکواییه": ["ارایه و پیگیری شکواییه"],
        "دادخواست بدوی": ["ارایه و پیگیری دادخواست", "دادخواست بدوی"],
        "دعاوی دادگاههای صلح": ["دعاوی دادگاههای صلح", "دعاوی حقوقی"],
        "دعاوی اعتراضی": ["دعاوی اعتراضی"],
        "دعاوی طاری": ["ارایه و پیگیری دعاوی طاری"],
        "دیوان عدالت اداری": ["دیوان عدالت اداری"],
        "شورای حل اختلاف": ["شورای حل اختلاف (صلح و سازش)"],
    }
    steps = nav_map.get(category, [])
    if subcategory and category in ("دعاوی اعتراضی", "دعاوی طاری", "دیوان عدالت اداری", "شورای حل اختلاف"):
        steps.append(subcategory)
    for i, step in enumerate(steps):
        try:
            await force_click_by_text(page, step)
            await asyncio.sleep(2 if i < len(steps) - 1 else 4)
        except Exception as e:
            raise FastCheckError(f"خطا در ناوبری به «{step}»: {e}")


async def _wait_for_loading(page, timeout=45):
    try:
        await page.evaluate('''(timeout) => {
            return new Promise((resolve) => {
                let checks = 0;
                const maxChecks = timeout * 2;
                const interval = setInterval(() => {
                    checks++;
                    if (checks >= maxChecks) { clearInterval(interval); resolve(false); return; }
                    const loaders = document.querySelectorAll('.blockUI, .blockOverlay, .loading-mask, .ajax-loader, .spinner, .loading, #loading, .progress-bar, .nprogress, .bar-loading, [ng-show*="loading"]');
                    let anyVisible = false;
                    for (const loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== "none") { anyVisible = true; break; }
                    }
                    if (!anyVisible) { clearInterval(interval); resolve(false); }
                }, 500);
            });
        }''', timeout)
    except Exception as e:
        logger.warning(f"[FAST-CHECK] loading wait error: {e}")
    await asyncio.sleep(1)


async def _dismiss_error_and_retry(page):
    has_error = await page.evaluate('''() => {
        const body = document.body ? document.body.innerText : '';
        return body.includes('لطفا اطلاعات خواسته شده را به درستی وارد نمایید');
    }''')
    if has_error:
        try:
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const closeBtn = btns.find(b => (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm"));
                if (closeBtn) closeBtn.click();
            }''')
            await asyncio.sleep(2)
            await page.evaluate('''() => {
                const exactBtn = document.querySelector('#btnGetJSSPetition');
                if (exactBtn) { exactBtn.click(); return; }
                const exactBtn2 = document.querySelector('#btnGetJSSBill');
                if (exactBtn2) { exactBtn2.click(); return; }
            }''')
            await asyncio.sleep(3)
            await _wait_for_loading(page, timeout=45)
        except Exception:
            pass


async def _click_if_exists(page, text):
    try:
        exists = await page.evaluate('''(txt) => {
            const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
            for (let tag of tags) {
                const elements = Array.from(document.querySelectorAll(tag));
                const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
                if (target) { const rect = target.getBoundingClientRect(); if (rect.width > 0 && rect.height > 0) return true; }
            }
            return false;
        }''', text)
        if exists:
            await force_click_by_text(page, text)
            return True
    except Exception:
        pass
    return False


class _EndpointDiscovery:
    def __init__(self, category, subcategory=None):
        self.category = category
        self.subcategory = subcategory
        self.key = _get_category_key(category, subcategory)
        self.captured = []

    def attach(self, page):
        page.on('response', self._on_response)

    def detach(self, page):
        try:
            page.remove_listener('response', self._on_response)
        except Exception:
            pass

    def _on_response(self, response):
        req = response.request
        if req.resource_type not in ('xhr', 'fetch'):
            return
        url = response.url
        if any(ext in url.lower() for ext in ['.js', '.css', '.png', '.jpg', '.ico', '.woff', '.svg']):
            return
        self.captured.append({
            'url': url, 'method': req.method, 'status': response.status,
            'post_data': req.post_data, 'content_type': response.headers.get('Content-Type', ''),
        })

    def analyze_and_save(self):
        if len(self.captured) < 2:
            self._save_debug()
            return
        search_ep = None
        attach_ep = None
        for req in self.captured:
            pd = req.get('post_data', '') or ''
            if not search_ep and pd and any(k in pd for k in ('petitionNo', 'billNo', 'txtPetitionNo')):
                search_ep = req
                continue
            if search_ep and not attach_ep and req['url'] != search_ep['url']:
                attach_ep = req
                continue
        if not attach_ep and len(self.captured) >= 2 and search_ep:
            for req in self.captured:
                if req['url'] != search_ep['url']:
                    attach_ep = req
                    break
        if search_ep and attach_ep:
            endpoints = _load_endpoints()
            endpoints[self.key] = {
                'search_url': search_ep['url'].replace(BASE_URL, ''),
                'attachments_url': attach_ep['url'].replace(BASE_URL, ''),
                'search_body_template': self._make_template(search_ep.get('post_data', '')),
                'attachments_body_template': self._make_template(attach_ep.get('post_data', '')),
                'discovered_at': time.time(),
            }
            _save_endpoints(endpoints)
            logger.info(f"[DISCOVERY] endpoints saved for {self.key}")
        else:
            self._save_debug()

    def _save_debug(self):
        if not self.captured:
            return
        debug_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"discovery_debug_{self.key.replace('/', '_')}.json")
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(self.captured, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _make_template(self, post_data):
        if not post_data:
            return {}
        params = {}
        for pair in post_data.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                k, v = unquote(k), unquote(v)
                if v.isdigit() and len(v) >= 10:
                    params[k] = '{{TRACKING_CODE}}'
                elif v.isdigit() and len(v) < 10:
                    params[k] = '{{PETITION_ID}}'
                else:
                    params[k] = v
        return params


async def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()
