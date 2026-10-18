import { db } from '@/lib/db';
import type { Prisma } from '@prisma/client';
import { NextResponse } from 'next/server';

// ⭐ پرونده‌های در انتظار امضا و پرداخت — همان فهرستی که کاربر در ربات می‌بیند
// (pending_cases.py). قواعد هم‌راستا با ربات:
//   - فقط پرونده‌های ثبت‌شده در سامانه (کد رهگیری دارند) و بدون امضا
//   - لایحه و اعلام وکالت ۴ روز، سایر موارد (اظهارنامه، دعاوی اعتراضی، چک) ۳۰ روز
//   - وضعیت «لغو شده»ِ پاک‌سازی خودکار ۲۴ ساعته نادیده گرفته می‌شود؛ پرونده تا
//     پایان مهلتش در ربات قابل ادامه است، پس اینجا هم نمایش داده می‌شود.
//   GET → { cases, summary }

const DAY_MS = 24 * 60 * 60 * 1000;
const SHORT_DAYS = 4;
const LONG_DAYS = 30;
const SHORT_SERVICES = ['LAVAYEH', 'EALAM_VAKALAHT'];
const LONG_SERVICES = ['EZHHARNAMEH', 'TAJDID_NAZAR', 'CHECK'];
const PAID = new Set(['PAID', 'MANUAL_APPROVED']);

export async function GET() {
  try {
    const now = Date.now();
    const base: Prisma.CaseWhereInput = { hasSignature: false, trackingCode: { not: null }, status: { not: 'FAILED' } };
    const cases = await db.case.findMany({
      where: {
        OR: [
          { ...base, serviceType: { in: SHORT_SERVICES }, createdAt: { gte: new Date(now - SHORT_DAYS * DAY_MS) } },
          { ...base, serviceType: { in: LONG_SERVICES }, createdAt: { gte: new Date(now - LONG_DAYS * DAY_MS) } },
        ],
      },
      orderBy: { createdAt: 'desc' },
      take: 300,
      select: {
        id: true,
        baleUserId: true,
        fullName: true,
        serviceType: true,
        status: true,
        trackingCode: true,
        title: true,
        documentCategory: true,
        fee: true,
        feeStatus: true,
        createdAt: true,
      },
    });

    const rows = cases.map((c) => {
      const days = SHORT_SERVICES.includes(c.serviceType) ? SHORT_DAYS : LONG_DAYS;
      return {
        ...c,
        paid: PAID.has(c.feeStatus),
        expiresAt: new Date(c.createdAt.getTime() + days * DAY_MS).toISOString(),
      };
    });
    const paidCount = rows.filter((r) => r.paid).length;
    return NextResponse.json({
      cases: rows,
      summary: {
        total: rows.length,
        paidCount,
        unpaidCount: rows.length - paidCount,
        unpaidAmount: rows.filter((r) => !r.paid).reduce((sum, r) => sum + (r.fee || 0), 0),
      },
    });
  } catch (error) {
    console.error('[pending-signatures] GET error:', error);
    return NextResponse.json({ error: 'خطا در دریافت پرونده‌های در انتظار امضا' }, { status: 500 });
  }
}
