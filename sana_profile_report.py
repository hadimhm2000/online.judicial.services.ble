"""
استخراج تمیز اطلاعات پروفایل ثنا (RealPersonPrint.aspx) و ساخت یک PDF مستقل
شامل فقط «عکس پرسنلی» + «اطلاعات شخص»، بدون لوگو، بدون نکات امنیتی/فوتر
و بدون وابستگی به مارک‌آپ متغیر و ناپایدار خودِ صفحه.

روش کار:
    1) در صفحه‌ی چاپ (که از قبل باز شده) فقط داده خام استخراج می‌شود
       (extract_sana_profile).
    2) یک صفحه‌ی مرورگر کاملاً جدید و خالی باز می‌شود و HTML تمیزِ
       ازپیش‌طراحی‌شده در آن ست می‌شود (render_sana_profile_html).
    3) از همان صفحه‌ی جدید PDF گرفته می‌شود (build_sana_profile_pdf).

این یعنی خروجی چاپ، مستقل از هر گونه المان اضافه‌ی صفحه‌ی اصلی
(لوگو، نکات امنیتی، فوتر، افزونه‌های مرورگر و ...) همیشه دقیقاً
همان چیزی است که طراحی شده.
"""
import asyncio
import html as html_lib
import logging
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────
# ۱) استخراج داده خام از صفحه‌ی چاپ ثنا
# ──────────────────────────────────────────────────────────────────────────
_EXTRACT_JS = r"""
() => {
    const norm = (s) => (s || "").replace(/\u200c/g, " ").replace(/\s+/g, " ").trim();

    const result = { photo: null, sections: [] };

    // ── عکس پرسنلی: داخل #tblHeader، همیشه «آخرین» تصویر است.
    //    (تصویر اول همیشه لوگوی قوه‌قضاییه است و باید کنار گذاشته شود.)
    const headerEl = document.getElementById('tblHeader');
    if (headerEl) {
        const imgs = Array.from(headerEl.querySelectorAll('img'))
            .filter(img => (img.naturalWidth || img.width || 0) > 20);
        if (imgs.length > 0) {
            result.photo = imgs[imgs.length - 1].getAttribute('src');
        }
    }

    // ── بخش‌های اطلاعاتی: عنوان خاکستری (background) + جدولِ ردیف‌های label:value
    const bodyEl = document.getElementById('tblBody');
    if (bodyEl) {
        const mainTable = bodyEl.querySelector('table');
        if (mainTable) {
            const topRows = Array.from(mainTable.children[0]
                ? mainTable.children[0].children
                : mainTable.querySelectorAll('tr'));

            let current = null;
            topRows.forEach(tr => {
                const cells = Array.from(tr.children);
                if (cells.length !== 1 || !cells[0].hasAttribute('colspan')) return;

                const td = cells[0];
                const innerTable = td.querySelector('table');

                if (!innerTable) {
                    // ردیف عنوان بخش (فقط متن/strong، بدون جدول تو در تو)
                    const title = norm(td.textContent);
                    if (!title) return;
                    if (title.startsWith('نکات امنیتی') || title.startsWith('نكات امنيتي') ||
                        title.includes('چاپ شده توسط')) {
                        current = null; // بخش‌های نامرتبط را نادیده بگیر
                        return;
                    }
                    current = { title: title, fields: [] };
                    result.sections.push(current);
                    return;
                }

                // ردیف داده: شامل جدولِ تو در توی فیلدهاست
                if (!current) return;
                const rowsToScan = Array.from(innerTable.querySelectorAll('tr'));
                rowsToScan.forEach(innerTr => {
                    const innerCells = Array.from(innerTr.children);
                    for (let i = 0; i + 1 < innerCells.length; i += 2) {
                        let label = norm(innerCells[i].textContent).replace(/:\s*$/, '');
                        let value = norm(innerCells[i + 1].textContent);
                        if (label) {
                            current.fields.push({ label: label, value: value });
                        }
                    }
                });
            });
        }
    }

    return result;
}
"""


async def extract_sana_profile(page) -> Optional[dict]:
    """
    از صفحه‌ی RealPersonPrint.aspx که از قبل لود شده، فقط داده‌ی خام
    (عکس + بخش‌های اطلاعاتی) را استخراج می‌کند. اگر چیزی پیدا نشود None برمی‌گرداند.
    """
    try:
        data = await page.evaluate(_EXTRACT_JS)
    except Exception as e:
        logging.error(f"[SANA_PROFILE] خطا در استخراج داده: {e}")
        return None

    if not data or (not data.get("photo") and not data.get("sections")):
        return None
    return data


# ──────────────────────────────────────────────────────────────────────────
# ۲) ساخت HTML تمیز و مستقل از روی داده‌ی استخراج‌شده
# ──────────────────────────────────────────────────────────────────────────
def render_sana_profile_html(data: dict, national_id: str = "") -> str:
    photo_src = data.get("photo") or ""
    sections = data.get("sections") or []

    def esc(s):
        return html_lib.escape(s or "", quote=True)

    sections_html = ""
    for sec in sections:
        title = esc(sec.get("title", ""))
        fields = sec.get("fields", [])

        rows_html = ""
        i = 0
        while i < len(fields):
            f1 = fields[i]
            f2 = fields[i + 1] if i + 1 < len(fields) else None
            if f2 is not None:
                rows_html += (
                    "<tr>"
                    f"<td class='label'>{esc(f1['label'])}</td>"
                    f"<td class='value'>{esc(f1['value'])}</td>"
                    f"<td class='label'>{esc(f2['label'])}</td>"
                    f"<td class='value'>{esc(f2['value'])}</td>"
                    "</tr>"
                )
                i += 2
            else:
                rows_html += (
                    "<tr>"
                    f"<td class='label'>{esc(f1['label'])}</td>"
                    f"<td class='value' colspan='3'>{esc(f1['value'])}</td>"
                    "</tr>"
                )
                i += 1

        sections_html += (
            f"<div class='section-title'>{title}</div>"
            f"<table class='fields'><tbody>{rows_html}</tbody></table>"
        )

    photo_html = (
        f"<img src='{esc(photo_src)}' alt='عکس پرسنلی'>"
        if photo_src else ""
    )

    return f"""<!doctype html>
<html dir="rtl" lang="fa">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    background: #ffffff;
  }}
  body {{
    font-family: Tahoma, "B Nazanin", Arial, sans-serif;
    color: #000;
    padding: 24px;
  }}
  .card {{
    max-width: 700px;
    margin: 0 auto;
    border: 1px solid #999;
    border-radius: 6px;
    padding: 16px 18px;
  }}
  .card-header {{
    text-align: center;
    font-size: 15px;
    font-weight: 700;
    padding-bottom: 12px;
    border-bottom: 1px solid #ddd;
    margin-bottom: 14px;
  }}
  .photo-wrap {{
    display: flex;
    justify-content: flex-start;
    margin-bottom: 16px;
  }}
  .photo-wrap img {{
    width: 92px;
    height: 112px;
    object-fit: cover;
    border: 1px solid #aaa;
    border-radius: 4px;
  }}
  .section-title {{
    background: #e6e6e6;
    font-weight: 700;
    font-size: 13.5px;
    padding: 6px 10px;
    border: 1px solid #a7a1a1;
    border-bottom: none;
  }}
  table.fields {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 14px;
  }}
  table.fields td {{
    border: 1px solid #a7a1a1;
    padding: 7px 10px;
    font-size: 12.5px;
    vertical-align: top;
  }}
  table.fields td.label {{
    width: 18%;
    font-weight: 700;
    background: #fafafa;
    white-space: nowrap;
  }}
  table.fields td.value {{
    width: 32%;
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="photo-wrap">{photo_html}</div>
    {sections_html}
  </div>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────
# ۳) ساخت PDF از HTML تمیز، در یک صفحه‌ی کاملاً جدید (مستقل از صفحه‌ی اصلی)
# ──────────────────────────────────────────────────────────────────────────
async def build_sana_profile_pdf(
    browser_context, data: dict, out_path: str, national_id: str = ""
) -> bool:
    """
    یک صفحه‌ی جدید و خالی باز می‌کند، HTML تمیزِ ساخته‌شده از داده‌ها را در آن
    ست می‌کند، منتظر لود شدنِ عکس می‌ماند و از همان صفحه PDF می‌گیرد.
    صفحه‌ی جدید در پایان بسته می‌شود. صفحه‌ی اصلیِ sana_page اصلاً دست‌کاری نمی‌شود.
    """
    html_content = render_sana_profile_html(data, national_id=national_id)

    new_page = await browser_context.new_page()
    try:
        await new_page.set_content(html_content, wait_until="load")

        # اطمینان از لود کامل عکس (base64 data-uri معمولاً بلافاصله لود می‌شود،
        # اما برای اطمینان کمی صبر می‌کنیم)
        try:
            await new_page.evaluate(
                """() => {
                    return new Promise((resolve) => {
                        const imgs = Array.from(document.querySelectorAll('img'));
                        const pending = imgs.filter(img => !img.complete);
                        if (pending.length === 0) return resolve();
                        let done = 0;
                        const check = () => { done++; if (done >= pending.length) resolve(); };
                        pending.forEach(img => {
                            img.addEventListener('load', check);
                            img.addEventListener('error', check);
                        });
                        setTimeout(resolve, 4000);
                    });
                }"""
            )
        except Exception:
            pass

        await asyncio.sleep(0.3)
        await new_page.pdf(path=out_path, format="A4")
        return True
    except Exception as e:
        logging.error(f"[SANA_PROFILE] خطا در ساخت PDF: {e}")
        return False
    finally:
        try:
            await new_page.close()
        except Exception:
            pass
