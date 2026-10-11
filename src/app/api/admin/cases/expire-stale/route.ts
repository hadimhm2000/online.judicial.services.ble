import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ v1.10 — بستن خودکار درخواست‌های بی‌پیشرفت (stale_requests.py در ربات، هر ساعت)
//   POST { hours?: 24, notifyWindowHours?: 48, excludeUserIds?: string[] }
//
// پرونده‌هایی که در وضعیت PENDING_PAYMENT / INCOMPLETE / PROCESSING مانده‌اند و
// بیش از `hours` ساعت هیچ به‌روزرسانی نداشته‌اند «لغو شده» (CANCELLED) می‌شوند
// و یک ActivityLog با action=AUTO_EXPIRED برایشان ثبت می‌شود.
//   - updatedAt عمداً دست نمی‌خورد تا «دریافتی امروز» گزارش شبانه (که بر اساس
//     updatedAt پرونده‌های پرداخت‌شده است) با لغو پرونده‌های قدیمی باد نکند.
//   - excludeUserIds: کاربرانی که ربات هنوز فرآیند زنده‌ای برایشان دارد
//     (پنجرهٔ امضا/پرداخت/اصلاح تازه، صف خارج از ساعت کاری، رسید در بررسی مدیر).
//   - recent: پرونده‌هایی که تازه (در notifyWindowHours اخیر) از مرز عبور کرده‌اند؛
//     ربات فقط به همین‌ها پیام می‌دهد تا با اولین اجرا برای پرونده‌های ماه‌ها
//     پیش پیام نرود.
//   - keepPaidProcessing (۱۴۰۵/۰۷): پرونده‌های PROCESSING که پرداخت شده‌اند
//     منتظر اقدام «ما» (ثبت در سامانه) هستند، نه کاربر — لغو نمی‌شوند تا
//     درخواست‌های معوق (مثلاً پس از مسدود شدن IP یا انتقال سرور) گم نشوند.

const OPEN_STATUSES = ['PENDING_PAYMENT', 'INCOMPLETE', 'PROCESSING'];

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const hours = Math.max(1, Number(body?.hours) || 24);
    const notifyWindowHours = Math.max(hours, Number(body?.notifyWindowHours) || hours * 2);
    const exclude: string[] = Array.isArray(body?.excludeUserIds) ? body.excludeUserIds.map(String) : [];
    const keepPaidProcessing = body?.keepPaidProcessing === true;

    const now = Date.now();
    const cutoff = new Date(now - hours * 3600_000);
    const recentFrom = new Date(now - notifyWindowHours * 3600_000);

    const candidates = await db.case.findMany({
      where: {
        status: { in: OPEN_STATUSES },
        updatedAt: { lt: cutoff },
        ...(exclude.length ? { baleUserId: { notIn: exclude } } : {}),
      },
      select: {
        id: true, baleUserId: true, fullName: true, serviceType: true, status: true,
        trackingCode: true, fee: true, feeStatus: true, prepayAmount: true, updatedAt: true,
      },
      orderBy: { updatedAt: 'asc' },
    });
    const isPaid = (c: { fee: number | null; feeStatus: string; prepayAmount: number | null }) =>
      (c.prepayAmount || 0) > 0
      || ((c.fee || 0) > 0 && ['PAID', 'MANUAL_APPROVED'].includes(c.feeStatus));
    const stale = keepPaidProcessing
      ? candidates.filter((c) => !(c.status === 'PROCESSING' && isPaid(c)))
      : candidates;

    const recent: {
      id: string; baleUserId: string; fullName: string; serviceType: string;
      previousStatus: string; trackingCode: string | null; paid: boolean;
    }[] = [];
    for (const c of stale) {
      await db.$transaction([
        db.case.update({ where: { id: c.id }, data: { status: 'CANCELLED', updatedAt: c.updatedAt } }),
        db.activityLog.create({
          data: {
            caseId: c.id,
            action: 'AUTO_EXPIRED',
            details: `لغو خودکار: ${hours} ساعت بدون پیشرفت (وضعیت قبلی: ${c.status})`,
          },
        }),
      ]);
      if (c.updatedAt >= recentFrom) {
        const paid = isPaid(c);
        recent.push({
          id: c.id, baleUserId: c.baleUserId, fullName: c.fullName, serviceType: c.serviceType,
          previousStatus: c.status, trackingCode: c.trackingCode, paid,
        });
      }
    }

    return NextResponse.json({
      expired: stale.length,
      // همهٔ کاربرانی که پرونده‌شان بسته شد (برای پاک‌سازی حافظهٔ ربات)
      userIds: [...new Set(stale.map((c) => c.baleUserId))],
      recent,
    });
  } catch (error) {
    console.error('[expire-stale] POST error:', error);
    return NextResponse.json({ error: 'خطا در بستن پرونده‌های بی‌پیشرفت' }, { status: 500 });
  }
}
