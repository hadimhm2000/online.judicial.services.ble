import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const baleUserId = searchParams.get('baleUserId');
    const search = searchParams.get('search');

    // حالت جستجو/پیشنهاد کاربر (برای مثال در ارسال پیام از پنل ادمین):
    // با نام یا شناسهٔ بله جستجو می‌کند و لیست کاربران یکتا برمی‌گرداند.
    if (search) {
      const query = search.trim();
      if (query.length < 2) {
        return NextResponse.json({ users: [] });
      }

      const cases = await db.case.findMany({
        where: {
          OR: [
            { fullName: { contains: query } },
            { baleUserId: { contains: query } },
          ],
        },
        select: { baleUserId: true, fullName: true },
        orderBy: { createdAt: 'desc' },
        take: 200,
      });

      const seen = new Set<string>();
      const users: { baleUserId: string; fullName: string }[] = [];
      for (const c of cases) {
        if (seen.has(c.baleUserId)) continue;
        seen.add(c.baleUserId);
        users.push({ baleUserId: c.baleUserId, fullName: c.fullName || c.baleUserId });
        if (users.length >= 10) break;
      }

      return NextResponse.json({ users });
    }

    if (!baleUserId) {
      return NextResponse.json({ error: 'baleUserId is required' }, { status: 400 });
    }

    // Get all cases for this user
    const cases = await db.case.findMany({
      where: { baleUserId },
      orderBy: { createdAt: 'desc' },
      take: 100,
    });

    // Compute summary
    const summary = {
      total: cases.length,
      completed: cases.filter((c) => c.status === 'COMPLETED').length,
      failed: cases.filter((c) => c.status === 'FAILED').length,
      unpaid: cases.filter((c) => c.feeStatus === 'UNPAID').length,
      totalSpent: cases.reduce((s, c) => s + (c.feeStatus === 'PAID' || c.feeStatus === 'MANUAL_APPROVED' ? c.fee : 0), 0),
      serviceTypes: [...new Set(cases.map((c) => c.serviceType))],
      lastActivity: cases[0]?.createdAt || null,
    };

    return NextResponse.json({ baleUserId, fullName: cases[0]?.fullName || baleUserId, summary, cases });
  } catch (error) {
    console.error('User history error:', error);
    return NextResponse.json({ error: 'Failed to fetch user history' }, { status: 500 });
  }
}
