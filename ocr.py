"""
تایید خودکار فیش پرداخت با OCR چند لایه (Tesseract + OpenCV) + VLM فال‌بک
این ماژول از چندین تکنیک پیش‌پردازش تصویر برای افزایش دقت OCR استفاده می‌کند.
وقتی Tesseract نتواند تایید کند، از VLM (مدل بینایی) به عنوان فال‌بک استفاده می‌شود.
"""
import logging
import re
import os
import json
import subprocess
import shutil

# ================= کتابخانه‌های اختیاری OCR فیش پرداخت =================
HAS_OCR = False
HAS_OPENCV = False

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    HAS_OCR = True
    logging.info("✅ PIL و Pytesseract با موفقیت بارگذاری شد!")
except ImportError as e:
    logging.warning(f"⚠️ خطا در بارگذاری PIL/Pytesseract: {e}")

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
    logging.info("✅ OpenCV با موفقیت بارگذاری شد!")
except ImportError:
    logging.warning("⚠️ OpenCV یافت نشد. از پیش‌پردازش ساده استفاده می‌شود.")

# بررسی وجود z-ai CLI برای VLM فال‌بک
HAS_VLM = shutil.which('z-ai') is not None
if HAS_VLM:
    logging.info("✅ z-ai CLI یافت شد — VLM فال‌بک فعال است.")
else:
    logging.warning("⚠️ z-ai CLI یافت نشد — VLM فال‌بک غیرفعال است.")

# تلاش برای یافتن مسیر Tesseract در ویندوز
if os.name == 'nt':
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\Administrator\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = path
                logging.info(f"✅ Tesseract پیدا شد: {path}")
                break
            except:
                pass


def preprocess_image_opencv(image_path):
    if not HAS_OPENCV:
        return None
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.array([[-1, -1, -1], [-1,  9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(binary, -1, kernel)
        temp_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
        cv2.imwrite(temp_path, sharpened)
        return temp_path
    except Exception as e:
        logging.error(f"❌ خطا در پیش‌پردازش OpenCV: {e}")
        return None


def preprocess_image_pil(image_path):
    try:
        img = Image.open(image_path)
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)
        temp_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
        img.save(temp_path)
        return temp_path
    except Exception as e:
        logging.error(f"❌ خطا در پیش‌پردازش PIL: {e}")
        return image_path


def normalize_persian_text(text):
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    english_digits = '0123456789'
    translation_table = str.maketrans(
        persian_digits + arabic_digits,
        english_digits + english_digits
    )
    normalized = text.translate(translation_table)
    normalized = normalized.replace(" ", "").replace(",", "").replace("/", "")
    normalized = normalized.replace("\n", " ").replace("\r", "").replace("\t", " ")
    normalized = normalized.replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")
    normalized = normalized.replace("_", "").replace("-", "").replace(".", "")
    return normalized


def extract_numbers(text):
    normalized = normalize_persian_text(text)
    numbers = re.findall(r'\d+', normalized)
    return [int(n) for n in numbers if len(n) >= 3]


def _verify_with_vlm(photo_path, expected_amount, card_number):
    """
    بررسی فیش پرداخت با مدل بینایی (VLM) به عنوان فال‌بک.
    از z-ai CLI استفاده می‌کند.
    
    Returns:
        (bool, str): وضعیت تایید و پیام توضیحات
    """
    if not HAS_VLM:
        return None, ""

    last_4 = card_number[-4:] if card_number else ""
    json_tmpl = '{"valid": true/false, "reason": "brief explanation"}'
    prompt = (
        "This is a Persian bank payment receipt. "
        "Check if this receipt is a valid successful payment receipt. "
        f"The expected amount is {expected_amount:,} Toman (or {expected_amount * 10:,} Rial). "
        f"The destination card last 4 digits should be {last_4}. "
        f"Answer ONLY with JSON: {json_tmpl}"
    )

    try:
        result = subprocess.run(
            ['z-ai', 'vision', '-p', prompt, '-i', photo_path, '-o', '/tmp/vlm_result.json'],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            logging.warning(f"VLM CLI failed: {result.stderr[:200]}")
            return None, ""

        with open('/tmp/vlm_result.json', 'r') as f:
            vlm_data = json.load(f)

        content = vlm_data.get('choices', [{}])[0].get('message', {}).get('content', '')
        logging.info(f"🔍 VLM response: {content[:300]}")

        # استخراج JSON از پاسخ
        json_match = re.search(r'\{[^}]+\}', content)
        if not json_match:
            logging.warning("VLM: no JSON found in response")
            return None, ""

        parsed = json.loads(json_match.group())
        is_valid = parsed.get('valid', False)
        reason = parsed.get('reason', '')

        if is_valid:
            logging.info(f"✅ VLM receipt verified: {reason}")
            return True, f"✅ رسید تایید شد (بررسی هوشمند)\n{reason}"
        else:
            logging.info(f"❌ VLM receipt rejected: {reason}")
            return False, f"VLM: {reason}"

    except subprocess.TimeoutExpired:
        logging.warning("VLM: timeout")
        return None, ""
    except Exception as e:
        logging.error(f"VLM error: {e}")
        return None, ""


def verify_payment_receipt(photo_path, expected_amount, card_number):
    """
    بررسی هوشمند و چند لایه تصویر فیش واریزی.
    ابتدا Tesseract، سپس VLM به عنوان فال‌بک.

    Args:
        photo_path: مسیر فایل تصویر
        expected_amount: مبلغ مورد انتظار به تومان
        card_number: شماره کارت مقصد

    Returns:
        (bool, str): وضعیت تایید و پیام توضیحات
    """
    # ── مرحله ۱: تلاش با Tesseract OCR ──
    tesseract_result = _verify_with_tesseract(photo_path, expected_amount, card_number)
    if tesseract_result[0]:
        return tesseract_result

    logging.info("⏭ Tesseract نتوانست تایید کند، تلاش با VLM...")

    # ── مرحله ۲: فال‌بک VLM ──
    vlm_valid, vlm_msg = _verify_with_vlm(photo_path, expected_amount, card_number)
    if vlm_valid is True:
        return True, vlm_msg
    if vlm_valid is False:
        # VLM هم رد کرد → نتیجه نهایی رد
        return False, f"❌ رسید تایید نشد\n\nتحلیل هوشمند: {vlm_msg}\n\nلطفاً تصویر رسید معتبر مجدداً ارسال فرمایید."

    # ── مرحله ۳: هر دو ناموفق بودند → نیاز به تایید دستی مدیر ──
    return False, "NEEDS_MANUAL_REVIEW"


def _verify_with_tesseract(photo_path, expected_amount, card_number):
    """
    بررسی فیش با Tesseract OCR (منطق قبلی، بدون تغییر)
    """
    if not HAS_OCR:
        return False, "OCR disabled"

    try:
        processed_path = None
        if HAS_OPENCV:
            processed_path = preprocess_image_opencv(photo_path)
        if not processed_path:
            processed_path = preprocess_image_pil(photo_path)

        texts = []
        try:
            img = Image.open(processed_path or photo_path)
            text_fas_eng = pytesseract.image_to_string(img, lang='fas+eng')
            texts.append(text_fas_eng)
        except Exception:
            pass

        try:
            img = Image.open(processed_path or photo_path)
            text_fas = pytesseract.image_to_string(img, lang='fas')
            texts.append(text_fas)
        except Exception:
            pass

        try:
            img = Image.open(processed_path or photo_path)
            text_eng = pytesseract.image_to_string(img, lang='eng')
            texts.append(text_eng)
        except Exception:
            pass

        if not texts:
            return False, ""

        combined_text = " ".join(texts)
        normalized_text = normalize_persian_text(combined_text).lower()

        all_numbers = extract_numbers(combined_text)

        expected_toman = expected_amount
        expected_rial = expected_amount * 10

        has_amount = False
        found_amount = None

        for num in all_numbers:
            if num == expected_toman or num == expected_rial:
                has_amount = True
                found_amount = num
                break
            if expected_toman > 0:
                diff_pct_t = abs(num - expected_toman) / expected_toman * 100
                diff_pct_r = abs(num - expected_rial) / expected_rial * 100
                if diff_pct_t <= 5 or diff_pct_r <= 5:
                    has_amount = True
                    found_amount = num
                    break

        if not has_amount:
            clean_text = re.sub(r'[^\d]', '', normalized_text)
            if str(expected_toman) in clean_text or str(expected_rial) in clean_text:
                has_amount = True
                found_amount = expected_toman

        has_card = False
        last_4_card = card_number[-4:] if card_number else ""
        last_6_card = card_number[-6:] if card_number and len(card_number) >= 6 else ""

        if last_4_card and (last_4_card in normalized_text or last_4_card in str(all_numbers)):
            has_card = True
        elif last_6_card and last_6_card in normalized_text:
            has_card = True

        keywords_payment = [
            "رسید", "انتقال", "موفق", "پیگیری", "ارجاع", "شناسه",
            "عملیات", "بانک", "واریز", "کارت", "شماره", "سند",
            "پایا", "ساتنا", "مبلغ", "تراکنش", "پرداخت", "successful"
        ]
        keyword_matches = [kw for kw in keywords_payment if kw in normalized_text or kw in combined_text.lower()]
        keyword_count = len(keyword_matches)

        score = 0
        reasons = []

        if has_amount:
            score += 60
            reasons.append(f"✓ مبلغ ({found_amount})")
        if has_card:
            score += 25
            reasons.append("✓ شماره کارت")
        if keyword_count >= 3:
            score += 15
            reasons.append(f"✓ {keyword_count} کلیدواژه")
        elif keyword_count >= 1:
            score += 10
            reasons.append(f"✓ {keyword_count} کلیدواژه")

        if score >= 70:
            return True, f"✅ رسید تایید شد! (امتیاز: {score})"
        if has_amount and score >= 60:
            return True, f"✅ رسید تایید شد (مبلغ صحیح، امتیاز: {score})"

        # تسرسکت نتوانست → برمی‌گردد False تا VLM تلاش کند
        return False, ""

    except Exception as e:
        logging.error(f"Tesseract error: {e}")
        return False, ""
