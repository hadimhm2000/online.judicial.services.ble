import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ «سوابق و فاکتورهای من» در ربات — آخرین پرونده‌های یک کاربر بله
//   GET ?baleUserId=123&limit=10
// فقط فیلدهای لازم برای نمایش به خود کاربر برگردانده می‌شود (نه یادداشت‌ها،
// خطاها یا هزینهٔ سامانه).

const MAX_LIMIT = 30;

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const baleUserId = (searchParams.get('baleUserId') || '').trim();
    if (!/^\d+$/.test(baleUserId)) {
      return NextResponse.json({ error: 'baleUserId نامعتبر است' }, { status: 400 });
    }
    const limit = Math.min(Math.max(parseInt(searchParams.get('limit') || '10') || 10, 1), MAX_LIMIT);

    const cases = await db.case.findMany({
      where: { baleUserId },
      orderBy: { createdAt: 'desc' },
      take: limit,
      select: {
        id: true,
        serviceType: true,
        status: true,
        trackingCode: true,
        title: true,
        documentCategory: true,
        subCategory: true,
        fee: true,
        feeStatus: true,
        prepayAmount: true,
        paymentMethod: true,
        createdAt: true,
        sentToUserAt: true,
      },
    });

    return NextResponse.json({ cases });
  } catch (error) {
    console.error('[user-cases] GET error:', error);
    return NextResponse.json({ error: 'خطا در دریافت سوابق کاربر' }, { status: 500 });
  }
}
