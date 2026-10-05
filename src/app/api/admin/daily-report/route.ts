import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ v1.9 — خلاصهٔ یک روز (به وقت تهران) برای گزارش شبانهٔ مدیر (daily_report.py)
//   GET ?date=YYYY-MM-DD

const TEHRAN_OFFSET = '+03:30';
const STUCK_HOURS = 3;

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const date = searchParams.get('date') || '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return NextResponse.json({ error: 'date باید YYYY-MM-DD باشد' }, { status: 400 });
    }
    const start = new Date(`${date}T00:00:00${TEHRAN_OFFSET}`);
    const end = new Date(start.getTime() + 86400_000);
    const range = { gte: start, lt: end };

    // ⭐ v1.10 — قبلاً فهرست گیرکرده‌ها با take: 20 بریده می‌شد و len همان فهرست
    // به‌عنوان «تعداد» گزارش می‌شد (همیشه حداکثر ۲۰، از همهٔ روزها). حالا تعداد
    // واقعی جدا شمرده می‌شود؛ پرونده‌های بالای ۲۴ ساعت را هم ربات خودکار لغو
    // می‌کند (expire-stale) و تعدادشان در autoExpired می‌آید.
    const stuckWhere = { status: 'PROCESSING', updatedAt: { lt: new Date(Date.now() - STUCK_HOURS * 3600_000) } };
    const [cases, paidCases, stuck, stuckCount, autoExpired, feedback] = await Promise.all([
      db.case.findMany({ where: { createdAt: range }, select: { serviceType: true, status: true } }),
      db.case.findMany({
        where: { feeStatus: { in: ['PAID', 'MANUAL_APPROVED'] }, updatedAt: range },
        select: { fee: true, prepayAmount: true },
      }),
      db.case.findMany({
        where: stuckWhere,
        select: { id: true, serviceType: true, trackingCode: true, baleUserId: true },
        orderBy: { updatedAt: 'asc' },
        take: 20,
      }),
      db.case.count({ where: stuckWhere }),
      db.activityLog.count({ where: { action: 'AUTO_EXPIRED', createdAt: range } }),
      db.feedback.findMany({ where: { createdAt: range }, select: { rating: true } }),
    ]);

    const byService: Record<string, number> = {};
    for (const c of cases) byService[c.serviceType] = (byService[c.serviceType] || 0) + 1;

    return NextResponse.json({
      date,
      totalCases: cases.length,
      byService,
      completed: cases.filter((c) => c.status === 'COMPLETED').length,
      failed: cases.filter((c) => c.status === 'FAILED').length,
      stuck,
      stuckCount,
      autoExpired,
      revenueToman: paidCases.reduce((s, c) => s + (c.fee || 0) + (c.prepayAmount || 0), 0),
      feedback: {
        count: feedback.length,
        average: feedback.length ? feedback.reduce((s, f) => s + f.rating, 0) / feedback.length : 0,
        low: feedback.filter((f) => f.rating <= 2).length,
      },
    });
  } catch (error) {
    console.error('[daily-report] GET error:', error);
    return NextResponse.json({ error: 'خطا در ساخت گزارش' }, { status: 500 });
  }
}
