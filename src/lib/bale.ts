import fs from 'fs';

const BOT_TOKEN = process.env.BOT_TOKEN;

// آدرس API بله — مستقیم یا از طریق واسطه
const BALE_API_BASE = process.env.BALE_API_BASE || 'https://tapi.bale.ai';

function apiUrl(method: string) {
  if (!BOT_TOKEN) {
    throw new Error('BOT_TOKEN در فایل .env تنظیم نشده است');
  }
  return `${BALE_API_BASE}/bot${BOT_TOKEN}/${method}`;
}

/**
 * ارسال پیام متنی به کاربر از طریق ربات بله.
 * از parse_mode=None استفاده می‌شود تا بله محتوای خام را ارسال کند.
 */
export async function sendBaleMessage(chatId: string, text: string) {
  if (!chatId?.trim()) {
    throw new Error('شناسه بله کاربر خالی است');
  }

  const res = await fetch(apiUrl('sendMessage'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: String(chatId).trim(), text }),
  });

  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.description || 'ارسال پیام بله ناموفق بود');
  }
  return data;
}

/**
 * ارسال یک فایل (سند/تصویر) به کاربر از طریق ربات بله.
 * filePath باید مسیر مطلق فایل روی دیسک سرور باشد.
 */
export async function sendBaleDocument(
  chatId: string,
  filePath: string,
  fileName: string,
  caption?: string
) {
  if (!chatId?.trim()) {
    throw new Error('شناسه بله کاربر خالی است');
  }

  if (!fs.existsSync(filePath)) {
    throw new Error(`فایل روی سرور پیدا نشد: ${fileName}`);
  }

  const buffer = fs.readFileSync(filePath);
  const form = new FormData();
  form.append('chat_id', String(chatId).trim());
  if (caption) form.append('caption', caption);
  form.append('document', new Blob([buffer]), fileName);

  const res = await fetch(apiUrl('sendDocument'), {
    method: 'POST',
    body: form,
  });

  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.description || `ارسال فایل «${fileName}» ناموفق بود`);
  }
  return data;
}

/**
 * ارسال فاکتور کیف پول بله به کاربر (برای هزینهٔ پیام مدیر و ...).
 * پس از پرداخت موفق، خود بله پیام successful_payment را برای ربات می‌فرستد
 * و ربات فلوی «پرداخت → ارسال پیام» را ادامه می‌دهد.
 *
 * amount به «ریال» و currency=IRR است — مطابق الگوی فاکتور در admin_relay.py
 */
export async function sendBaleInvoice(
  chatId: string,
  title: string,
  description: string,
  payload: object,
  amount: number
) {
  if (!chatId?.trim()) {
    throw new Error('شناسه بله کاربر خالی است');
  }
  const walletToken = process.env.BALE_WALLET_TOKEN;
  if (!walletToken) {
    throw new Error('BALE_WALLET_TOKEN در فایل .env پنل تنظیم نشده است');
  }
  if (!amount || amount <= 0) {
    throw new Error('مبلغ فاکتور باید بزرگ‌تر از صفر باشد');
  }

  const res = await fetch(apiUrl('sendInvoice'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: String(chatId).trim(),
      title,
      description,
      payload: JSON.stringify(payload),
      provider_token: walletToken,
      currency: 'IRR',
      prices: [{ label: title, amount }],
    }),
  });

  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.description || 'ارسال فاکتور بله ناموفق بود');
  }
  return data;
}
