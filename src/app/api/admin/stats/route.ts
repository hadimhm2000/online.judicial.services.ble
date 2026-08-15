import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const [
      total,
      completed,
      incomplete,
      unpaid,
      readyToSend,
      failed,
      cancelled,
      processing,
      todayCases,
      totalRevenue,
      unpaidRevenue,
    ] = await Promise.all([
      db.case.count(),
      db.case.count({ where: { status: 'COMPLETED', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'INCOMPLETE', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { feeStatus: 'UNPAID', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { isInReadyToSend: true, serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'FAILED', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'CANCELLED', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({ where: { status: 'PROCESSING', serviceType: { not: 'INQUIRY' } } }),
      db.case.count({
        where: {
          createdAt: {
            gte: new Date(new Date().setHours(0, 0, 0, 0)),
          },
        },
      }),
      db.case.aggregate({
        _sum: { fee: true },
        where: { feeStatus: { in: ['PAID', 'MANUAL_APPROVED'] } },
      }),
      db.case.aggregate({
        _sum: { fee: true },
        where: { feeStatus: 'UNPAID' },
      }),
    ]);

    const serviceBreakdown = await db.case.groupBy({
      by: ['serviceType'],
      _count: { id: true },
    });

    const sevenDaysAgo = new Date(Date.now() - 7 * 86400000);
    const dailyCases = await db.case.groupBy({
      by: ['createdAt'],
      where: { createdAt: { gte: sevenDaysAgo } },
      _count: { id: true },
    });

    return NextResponse.json({
      total,
      completed,
      incomplete,
      unpaid,
      readyToSend,
      failed,
      cancelled,
      processing,
      todayCases,
      totalRevenue: totalRevenue._sum.fee || 0,
      unpaidRevenue: unpaidRevenue._sum.fee || 0,
      serviceBreakdown,
      createdAt: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Stats error:', error);
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 });
  }
}
