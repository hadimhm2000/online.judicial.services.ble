import { NextRequest, NextResponse } from 'next/server';

// ⭐ احراز هویت پنل ادمین
//
// بدون این فایل، هر کسی که آدرس پنل را داشت می‌توانست همهٔ پرونده‌ها را
// بخواند، به کاربران پیام بفرستد، فایل آپلود کند یا با /api/admin/reset
// کل داده‌ها را پاک کند.
//
// دو راه ورود:
//   ۱) ربات پایتون (panel_sync.py و …): هدر X-Admin-Api-Key برابر ADMIN_API_SECRET
//      — فقط برای مسیرهای /api/admin/*
//   ۲) مرورگر مدیر: HTTP Basic Auth با ADMIN_PANEL_USER / ADMIN_PANEL_PASSWORD
//
// اگر هیچ‌کدام در .env تنظیم نشده باشد، پنل بسته می‌ماند (503) — نه باز.

const REALM = 'Admin Panel';

// مقایسهٔ زمان‌ثابت تا طول/محتوای کلید از روی زمان پاسخ لو نرود
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function hasValidApiKey(request: NextRequest, secret: string | undefined): boolean {
  if (!secret) return false;
  if (!request.nextUrl.pathname.startsWith('/api/admin')) return false;
  const provided = request.headers.get('x-admin-api-key');
  return !!provided && safeEqual(provided, secret);
}

function hasValidBasicAuth(request: NextRequest, user: string | undefined, pass: string | undefined): boolean {
  if (!user || !pass) return false;
  const header = request.headers.get('authorization');
  if (!header?.startsWith('Basic ')) return false;
  let decoded: string;
  try {
    decoded = new TextDecoder().decode(Uint8Array.from(atob(header.slice(6)), (c) => c.charCodeAt(0)));
  } catch {
    return false;
  }
  const sep = decoded.indexOf(':');
  if (sep < 0) return false;
  // هر دو مقایسه انجام می‌شود تا زمان پاسخ نشان ندهد کدام اشتباه بوده
  const userOk = safeEqual(decoded.slice(0, sep), user);
  const passOk = safeEqual(decoded.slice(sep + 1), pass);
  return userOk && passOk;
}

export function proxy(request: NextRequest) {
  const secret = process.env.ADMIN_API_SECRET;
  const user = process.env.ADMIN_PANEL_USER;
  const pass = process.env.ADMIN_PANEL_PASSWORD;

  if (!secret && !(user && pass)) {
    return NextResponse.json(
      { error: 'پنل ادمین پیکربندی نشده است: ADMIN_API_SECRET و ADMIN_PANEL_USER/ADMIN_PANEL_PASSWORD را در .env تنظیم کنید.' },
      { status: 503 }
    );
  }

  if (hasValidApiKey(request, secret) || hasValidBasicAuth(request, user, pass)) {
    return NextResponse.next();
  }

  return new NextResponse('Unauthorized', {
    status: 401,
    headers: { 'WWW-Authenticate': `Basic realm="${REALM}", charset="UTF-8"` },
  });
}

export const config = {
  // همه‌چیز به‌جز فایل‌های استاتیک خود Next.js — شامل صفحهٔ پنل، /api/* و /uploads/*
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
