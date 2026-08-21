#!/usr/bin/env python3
"""
اسکریپت خودکار اعمال تغییرات ماژول ارزش منطقه‌ای روی پروژه.
فایل‌های جدید را کپی و فایل‌های موجود را اصلاح می‌کند.

طریقه استفاده:
    python apply_patch.py /path/to/bot/project
"""
import os
import sys
import shutil
import re


def apply_patch(project_dir: str):
    """اعمال تمام تغییرات روی پروژه."""
    patch_dir = os.path.dirname(os.path.abspath(__file__))

    if not os.path.isdir(project_dir):
        print(f"❌ مسیر پروژه یافت نشد: {project_dir}")
        sys.exit(1)

    # ═══ کپی فایل‌های جدید ═══
    new_files = [
        "tax_geolocation_query.py",
        "geocode_and_query.py",
        "regional_value_pdf.py",
        "regional_value_handlers.py",
        "admin_rv_check.py",  # چک سلامت ادمین
        "tax_header.jpg",  # عکس هدر PDF (سازمان امور مالیاتی)
    ]
    print("📦 کپی فایل‌های جدید...")
    for fname in new_files:
        src = os.path.join(patch_dir, fname)
        dst = os.path.join(project_dir, fname)
        shutil.copy2(src, dst)
        print(f"   ✅ {fname}")

    # ═══ ۱. states.py ═══
    print("\n📝 اصلاح states.py...")
    states_path = os.path.join(project_dir, "states.py")
    with open(states_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "rv_waiting_province" not in content:
        rv_states = """

    # =========================================================
    # State های بخش استعلام ارزش منطقه‌ای
    # =========================================================
    rv_waiting_province = State()       # انتخاب استان
    rv_waiting_address = State()        # ورود آدرس
    rv_waiting_area = State()           # ورود متراژ
    rv_waiting_land_use = State()       # انتخاب کاربری زمین
    rv_waiting_payment = State()        # انتظار پرداخت
"""
        content = content.rstrip() + rv_states
        with open(states_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("   ✅ حالت‌های جدید اضافه شد")
    else:
        print("   ⏭️ حالت‌ها از قبل وجود دارند")

    # ═══ ۲. keyboards.py ═══
    print("\n📝 اصلاح keyboards.py...")
    kb_path = os.path.join(project_dir, "keyboards.py")
    with open(kb_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "ارزش منطقه" not in content:
        # جایگزینی ردیف اول منو
        old_row = '[KeyboardButton(text="🔍 استعلام"), KeyboardButton(text="📦 استعلام (چند مورد همزمان)")],'
        new_row = '[KeyboardButton(text="🔍 استعلام"), KeyboardButton(text="📦 استعلام (چند مورد همزمان)"), KeyboardButton(text="🗺️ ارزش منطقه‌ای")],'
        content = content.replace(old_row, new_row, 1)
        with open(kb_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("   ✅ دکمه منو اضافه شد")
    else:
        print("   ⏭️ دکمه از قبل وجود دارد")

    # ═══ ۳. config.py ═══
    print("\n📝 اصلاح config.py...")
    cfg_path = os.path.join(project_dir, "config.py")
    with open(cfg_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "REGIONAL_VALUE_FEE" not in content:
        patch_cfg = '''

# کلید API سرویس نشان (تبدیل آدرس به مختصات)
# از پنل platform.neshan.org بگیرید — حتماً از متغیر محیطی بخوانید، نه هاردکد
NESHAN_API_KEY = os.environ.get("NESHAN_API_KEY", "")

# هزینه استعلام ارزش منطقه‌ای (تومان)
REGIONAL_VALUE_FEE = 200000
'''
        # بعد از DEBUG_LOG_REQUESTS اضافه کن
        content = content.replace(
            "DEBUG_LOG_REQUESTS = False",
            "DEBUG_LOG_REQUESTS = False" + patch_cfg
        )
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("   ✅ تنظیمات جدید اضافه شد")
    else:
        print("   ⏭️ تنظیمات از قبل وجود دارند")

    # ═══ ۴. handlers.py ═══
    print("\n📝 اصلاح handlers.py...")
    h_path = os.path.join(project_dir, "handlers.py")
    with open(h_path, "r", encoding="utf-8") as f:
        content = f.read()

    applied = False

    # ۴-الف: ایمپورت
    if "regional_value_handlers" not in content:
        content = content.replace(
            "from check_handlers import check_router",
            "from check_handlers import check_router\nfrom regional_value_handlers import regional_value_router, regional_value_successful_payment\nfrom admin_rv_check import admin_rv_check_router"
        )
        applied = True
        print("   ✅ ایمپورت اضافه شد")
    else:
        print("   ⏭️ ایمپورت از قبل وجود دارد")

    # ۴-ب: روتر
    if "regional_value_router" not in content or "router.include_router(regional_value_router)" not in content:
        content = content.replace(
            "router.include_router(check_router)",
            "router.include_router(check_router)\nrouter.include_router(regional_value_router)\nrouter.include_router(admin_rv_check_router)"
        )
        applied = True
        print("   ✅ روتر اضافه شد")
    else:
        print("   ⏭️ روتر از قبل وجود دارد")

    # ۴-ج: مسیریابی در process_flow_type
    if '"ارزش منطقه" in message.text' not in content:
        content = content.replace(
            '    elif "ابزار فایل" in message.text:\n        await file_tools_entry(message, state)',
            '    elif "ابزار فایل" in message.text:\n        await file_tools_entry(message, state)\n    elif "ارزش منطقه" in message.text:\n        from regional_value_handlers import regional_value_entry\n        await regional_value_entry(message, state)'
        )
        applied = True
        print("   ✅ مسیریابی منو اضافه شد")
    else:
        print("   ⏭️ مسیریابی از قبل وجود دارد")

    # ۴-د: پرداخت موفق در global_successful_payment_handler
    if "rv_waiting_payment" not in content:
        content = content.replace(
            '                         Form.stamp_calc_waiting_payment):\n        return',
            '                         Form.stamp_calc_waiting_payment):\n        return\n\n    # ── پرداخت ارزش منطقه‌ای ──\n    if current_state == Form.rv_waiting_payment:\n        await regional_value_successful_payment(message, state, bot)\n        return'
        )
        applied = True
        print("   ✅ هندلر پرداخت اضافه شد")
    else:
        print("   ⏭️ هندلر پرداخت از قبل وجود دارد")

    if applied:
        with open(h_path, "w", encoding="utf-8") as f:
            f.write(content)

    # ═══ ۵. env.example ═══
    print("\n📝 اصلاح env.example...")
    env_path = os.path.join(project_dir, "env.example")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "NESHAN_API_KEY" not in content:
            content += "\n# ================= سرویس نشان (تبدیل آدرس به مختصات) =================\nNESHAN_API_KEY=your_neshan_api_key_here\n"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("   ✅ NESHAN_API_KEY اضافه شد")
        else:
            print("   ⏭️ از قبل وجود دارد")
    else:
        print("   ⏭️ فایل env.example یافت نشد")

    # ═══ ۶. requirements.txt ═══
    print("\n📝 بررسی requirements.txt...")
    req_path = os.path.join(project_dir, "requirements.txt")
    if os.path.exists(req_path):
        with open(req_path, "r", encoding="utf-8") as f:
            content = f.read()
        needed = []
        if "beautifulsoup4" not in content:
            needed.append("beautifulsoup4")
        if "reportlab" not in content:
            needed.append("reportlab")
        if "arabic_reshaper" not in content:
            needed.append("arabic_reshaper")
        if "python-bidi" not in content:
            needed.append("python-bidi")
        if needed:
            content += "\n" + "\n".join(needed) + "\n"
            with open(req_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"   ✅ اضافه شد: {', '.join(needed)}")
        else:
            print("   ⏭️ وابستگی‌ها از قبل وجود دارند")

    print("\n" + "="*50)
    print("✅ تمام تغییرات با موفقیت اعمال شد!")
    print("="*50)
    print("\n⚠️  اقدامات باقی‌مانده دستی:")
    print("   ۱. کلید NESHAN_API_KEY را در فایل .env خود تنظیم کنید")
    print("   ۲. مطمئن شوید وابستگی‌های PDF نصب هستند:")
    print("      pip install reportlab arabic_reshaper python-bidi beautifulsoup4")
    print("   ۳. ربات را ری‌استارت کنید")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("طریقه استفاده: python apply_patch.py /path/to/bot/project")
        sys.exit(1)
    apply_patch(sys.argv[1])
