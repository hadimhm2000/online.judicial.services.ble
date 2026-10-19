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
// (حلقه همیشه به طول رشتهٔ بلندتر اجرا می‌شود؛ اختلاف طول هم در نتیجه لحاظ می‌شود)
function safeEqual(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

// ⭐ محدودیت تلاش ناموفق ورود (حدس رمز): پس از MAX_FAILURES تلاش ناموفق در
// FAILURE_WINDOW_MS از یک IP، آن IP تا LOCK_MS قفل می‌شود. اگر IP مشخص نباشد،
// قفل اعمال نمی‌شود (تا مهاجم نتواند مدیر را بیرون نگه دارد) و فقط پاسخ کند می‌شود.
const MAX_FAILURES = 20;
const FAILURE_WINDOW_MS = 15 * 60 * 1000;
const LOCK_MS = 15 * 60 * 1000;
const failures = new Map<string, { count: number; first: number; lockedUntil: number }>();

function clientIp(request: NextRequest): string | null {
  const fwd = request.headers.get('x-forwarded-for');
  if (fwd) return fwd.split(',')[0].trim() || null;
  return request.headers.get('x-real-ip');
}

function isLocked(ip: string | null): boolean {
  if (!ip) return false;
  const rec = failures.get(ip);
  return !!rec && rec.lockedUntil > Date.now();
}

function noteFailure(ip: string | null): void {
  if (!ip) return;
  const now = Date.now();
  const rec = failures.get(ip);
  if (!rec || now - rec.first > FAILURE_WINDOW_MS) {
    failures.set(ip, { count: 1, first: now, lockedUntil: 0 });
  } else {
    rec.count += 1;
    if (rec.count >= MAX_FAILURES) rec.lockedUntil = now + LOCK_MS;
  }
  if (failures.size > 10_000) failures.clear();
}

// ⭐ CSRF: مرورگر رمز Basic Auth را برای درخواست‌هایی که از سایت‌های دیگر شروع
// شده‌اند هم خودکار می‌فرستد. درخواست‌های تغییردهنده (POST/PUT/PATCH/DELETE) که
// مرورگر آن‌ها را «از سایت دیگر» علامت زده رد می‌شوند. درخواست‌های خود پنل
// (same-origin) و ربات (کلید API، بدون مرورگر) تغییری نمی‌کنند.
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

function isCrossSiteWrite(request: NextRequest): boolean {
  if (SAFE_METHODS.has(request.method.toUpperCase())) return false;
  const site = request.headers.get('sec-fetch-site');
  if (site) return site === 'cross-site' || site === 'same-site';
  // مرورگرهای قدیمی بدون Sec-Fetch-Site: مقایسهٔ Origin با Host
  const origin = request.headers.get('origin');
  if (!origin || origin === 'null') return origin === 'null';
  let originHost: string;
  try {
    originHost = new URL(origin).host;
  } catch {
    return true;
  }
  const hosts = [request.headers.get('host'), request.headers.get('x-forwarded-host')];
  return !hosts.some((h) => h && h.split(',')[0].trim() === originHost);
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

export async function proxy(request: NextRequest) {
  const secret = process.env.ADMIN_API_SECRET;
  const user = process.env.ADMIN_PANEL_USER;
  const pass = process.env.ADMIN_PANEL_PASSWORD;

  if (!secret && !(user && pass)) {
    return NextResponse.json(
      { error: 'پنل ادمین پیکربندی نشده است: ADMIN_API_SECRET و ADMIN_PANEL_USER/ADMIN_PANEL_PASSWORD را در .env تنظیم کنید.' },
      { status: 503 }
    );
  }

  if (hasValidApiKey(request, secret)) {
    return NextResponse.next();
  }

  const ip = clientIp(request);
  if (isLocked(ip)) {
    return new NextResponse('Too many failed login attempts. Try again later.', { status: 429 });
  }

  if (hasValidBasicAuth(request, user, pass)) {
    if (isCrossSiteWrite(request)) {
      return NextResponse.json({ error: 'درخواست از سایت دیگر پذیرفته نمی‌شود' }, { status: 403 });
    }
    return NextResponse.next();
  }

  // فقط تلاش واقعی با رمز اشتباه شمرده می‌شود (نه درخواست اول مرورگر بدون رمز)
  if (request.headers.get('authorization')) {
    noteFailure(ip);
    if (!ip) await new Promise((r) => setTimeout(r, 1000));
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
