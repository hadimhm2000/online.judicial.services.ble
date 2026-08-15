import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const period = (searchParams.get('period') || 'daily') as 'daily' | 'weekly' | 'monthly';

    const allCases = await db.case.findMany({
      select: {
        createdAt: true,
        status: true,
        fee: true,
        feeStatus: true,
      },
      orderBy: { createdAt: 'asc' },
    });

    const grouped: Record<string, {
      total: number;
      completed: number;
      failed: number;
      revenue: number;
    }> = {};

    for (const c of allCases) {
      let key: string;
      const d = new Date(c.createdAt);

      if (period === 'daily') {
        key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      } else if (period === 'weekly') {
        const weekStart = new Date(d);
        weekStart.setDate(d.getDate() - d.getDay());
        key = `${weekStart.getFullYear()}-${String(weekStart.getMonth() + 1).padStart(2, '0')}-${String(weekStart.getDate()).padStart(2, '0')}`;
      } else {
        key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      }

      if (!grouped[key]) {
        grouped[key] = { total: 0, completed: 0, failed: 0, revenue: 0 };
      }
      grouped[key].total += 1;
      if (c.status === 'COMPLETED') grouped[key].completed += 1;
      if (c.status === 'FAILED') grouped[key].failed += 1;
      if (c.feeStatus === 'PAID' || c.feeStatus === 'MANUAL_APPROVED') {
        grouped[key].revenue += c.fee;
      }
    }

    const sortedKeys = Object.keys(grouped).sort();
    let data: { label: string; total: number; completed: number; failed: number; revenue: number }[];

    if (period === 'daily') {
      const maxDays = 30;
      const cutoff = sortedKeys.length > maxDays ? sortedKeys[sortedKeys.length - maxDays] : sortedKeys[0];
      data = sortedKeys
        .filter((k) => k >= cutoff)
        .map((k) => ({
          label: k.slice(5),
          total: grouped[k].total,
          completed: grouped[k].completed,
          failed: grouped[k].failed,
          revenue: grouped[k].revenue,
        }));
    } else if (period === 'weekly') {
      data = sortedKeys.map((k) => ({
        label: k.slice(5),
        total: grouped[k].total,
        completed: grouped[k].completed,
        failed: grouped[k].failed,
        revenue: grouped[k].revenue,
      }));
    } else {
      data = sortedKeys.map((k) => {
        const [y, m] = k.split('-');
        const monthNames = [
          'ژانویه', 'فوریه', 'مارس', 'آوریل', 'مه', 'ژوئن',
          'ژوئیه', 'اوت', 'سپتامبر', 'اکتبر', 'نوامبر', 'دسامبر',
        ];
        const monthIndex = parseInt(m, 10) - 1;
        return {
          label: monthNames[monthIndex] || m,
          total: grouped[k].total,
          completed: grouped[k].completed,
          failed: grouped[k].failed,
          revenue: grouped[k].revenue,
        };
      });
    }

    return NextResponse.json({ period, data });
  } catch (error) {
    console.error('Trends error:', error);
    return NextResponse.json({ error: 'Failed to fetch trends' }, { status: 500 });
  }
}
