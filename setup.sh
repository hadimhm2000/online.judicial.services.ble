#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# اسکریپت راه‌اندازی اتوماتیک بات خدمات قضایی
# ═══════════════════════════════════════════════════════════════

set -e  # خروج در صورت بروز خطا

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   🤖 راه‌اندازی بات اتوماسیون خدمات قضایی آنلاین       ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# بررسی نسخه Python
echo "📋 بررسی نسخه Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 نصب نیست. لطفاً ابتدا Python 3.8 یا بالاتر نصب کنید."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION یافت شد"

# ایجاد محیط مجازی
echo ""
echo "📦 ایجاد محیط مجازی Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ محیط مجازی ایجاد شد"
else
    echo "ℹ️  محیط مجازی از قبل وجود دارد"
fi

# فعال‌سازی محیط مجازی
echo ""
echo "🔄 فعال‌سازی محیط مجازی..."
source venv/bin/activate

# ارتقای pip
echo ""
echo "⬆️  ارتقای pip..."
pip install --upgrade pip -q

# نصب وابستگی‌ها
echo ""
echo "📥 نصب وابستگی‌های Python..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q
    echo "✅ وابستگی‌ها نصب شدند"
else
    echo "⚠️  فایل requirements.txt یافت نشد!"
fi

# نصب Playwright browsers
echo ""
echo "🌐 نصب مرورگر Chromium برای Playwright..."
playwright install chromium
echo "✅ مرورگر نصب شد"

# ایجاد فایل .env اگر وجود ندارد
echo ""
if [ ! -f ".env" ]; then
    echo "📝 فایل .env وجود ندارد. ایجاد از روی .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ فایل .env ایجاد شد"
        echo ""
        echo "⚠️  توجه: لطفاً فایل .env را ویرایش کرده و اطلاعات واقعی را وارد کنید:"
        echo "   - TELEGRAM_BOT_TOKEN"
        echo "   - SANA_USERNAME"
        echo "   - SANA_PASSWORD"
        echo "   - ADMIN_ID"
        echo "   - CARD_NUMBER"
        echo "   - ACCOUNT_NAME"
        echo ""
        read -p "فایل .env را الان ویرایش می‌کنید؟ (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        fi
    else
        echo "⚠️  فایل .env.example یافت نشد!"
    fi
else
    echo "ℹ️  فایل .env از قبل وجود دارد"
fi

# بررسی فایل google-credentials.json
echo ""
if [ ! -f "google-credentials.json" ]; then
    echo "⚠️  فایل google-credentials.json یافت نشد"
    echo "   اگر می‌خواهید از Google Sheets استفاده کنید، این فایل را از"
    echo "   Google Cloud Console دانلود کرده و در پوشه پروژه قرار دهید."
else
    echo "✅ فایل google-credentials.json موجود است"
fi

# تمام!
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                   ✅ نصب با موفقیت انجام شد!              ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 برای اجرای بات:"
echo "   source venv/bin/activate"
echo "   python bot.py"
echo ""
echo "📖 برای اطلاعات بیشتر، فایل README.md را مطالعه کنید"
echo ""
