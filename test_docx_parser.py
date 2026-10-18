"""تست حفظ قالب فایل ورد — اجرا: python -m pytest test_docx_parser.py"""
import os
import zipfile

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")

from docx_parser import docx_to_html, docx_to_plain_text

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {_W}>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:basedOn w:val="Normal"/>
    <w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:bCs/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="Strong"><w:rPr><w:b/></w:rPr></w:style>
</w:styles>"""

_BODY = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {_W} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>
  <w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>عنوان</w:t></w:r></w:p>
  <w:p>
    <w:r><w:t xml:space="preserve">عادی </w:t></w:r>
    <w:r><w:rPr><w:bCs/></w:rPr><w:t>بولد فارسی</w:t></w:r>
    <w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t xml:space="preserve"> نه‌بولد </w:t></w:r>
    <w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>زیرخط</w:t></w:r>
    <w:r><w:rPr><w:u w:val="none"/></w:rPr><w:t xml:space="preserve"> بی‌خط </w:t></w:r>
    <w:r><w:rPr><w:dstrike/></w:rPr><w:t>خط‌خورده</w:t></w:r>
    <w:r><w:rPr><w:rStyle w:val="Strong"/></w:rPr><w:t>استایل</w:t></w:r>
    <w:hyperlink r:id="rId1"><w:r><w:t>لینک</w:t></w:r></w:hyperlink>
    <w:del><w:r><w:delText>حذف‌شده</w:delText></w:r></w:del>
  </w:p>
  <w:p><w:r><w:t>خط اول</w:t><w:br/><w:t>خط دوم</w:t></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>سلول</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>"""


def _make_docx(tmp_path):
    path = tmp_path / "t.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", _BODY)
        z.writestr("word/styles.xml", _STYLES)
    return str(path)


def test_formatting_preserved(tmp_path):
    html = docx_to_html(_make_docx(tmp_path))
    assert '<p style="text-align: center;"><b>عنوان</b></p>' in html  # از استایل پاراگراف
    assert "<b>بولد فارسی</b>" in html          # w:bCs
    assert "<b> نه‌بولد" not in html and "نه‌بولد" in html  # w:b w:val=0
    assert "<u>زیرخط</u>" in html
    assert "<u> بی‌خط" not in html          # w:u none
    assert "<s>خط‌خورده</s>" in html             # w:dstrike
    assert "<b>استایل</b>" in html               # استایل کاراکتر
    assert "لینک" in html                         # متن داخل hyperlink
    assert "حذف‌شده" not in html                  # متن حذف‌شده (track changes)
    assert "خط اول<br>خط دوم" in html
    assert "سلول" in html                         # متن جدول


def test_plain_text(tmp_path):
    text = docx_to_plain_text(_make_docx(tmp_path))
    assert text.splitlines()[0] == "عنوان"
    assert "سلول" in text
