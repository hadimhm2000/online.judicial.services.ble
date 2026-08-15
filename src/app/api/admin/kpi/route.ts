import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const [completedCases, peakHourData, todayCompleted, todayFailed, allBaleUserIds, thisWeekCases, lastWeekCases] = await Promise.all([
      db.case.findMany({
        where: { status: 'COMPLETED' },
        select: { createdAt: true, updatedAt: true },
      }),
      db.case.findMany({
        select: { createdAt: true },
      }),
      db.case.count({
        where: {
          status: 'COMPLETED',
          updatedAt: { gte: todayStart },
        },
      }),
      db.case.count({
        where: {
          status: 'FAILED',
          updatedAt: { gte: todayStart },
        },
      }),
      db.case.findMany({
        select: { baleUserId: true },
        distinct: ['baleUserId'],
      }),
      db.case.findMany({
        where: {
          createdAt: { gte: getStartOfThisWeek(now) },
        },
        select: { status: true },
      }),
      db.case.findMany({
        where: {
          createdAt: { gte: getStartOfLastWeek(now), lt: getStartOfThisWeek(now) },
        },
        select: { status: true },
      }),
    ]);

    // 1. avgProcessingTime
    let avgProcessingTime = 0;
    if (completedCases.length > 0) {
      const totalMs = completedCases.reduce((sum, c) => {
        return sum + (c.updatedAt.getTime() - c.createdAt.getTime());
      }, 0);
      avgProcessingTime = Math.round((totalMs / completedCases.length / (1000 * 60 * 60)) * 100) / 100;
    }

    // 2. peakHour
    const hourCounts: number[] = new Array(24).fill(0);
    for (const c of peakHourData) {
      hourCounts[c.createdAt.getHours()]++;
    }
    let peakHour = 0;
    let peakHourCount = 0;
    for (let i = 0; i < 24; i++) {
      if (hourCounts[i] > peakHourCount) {
        peakHourCount = hourCounts[i];
        peakHour = i;
      }
    }
    const peakHourLabel = getPersianHourLabel(peakHour);

    // 3. todayCompleted - already fetched
    // 4. todayFailed - already fetched

    // 5. successRateTrend
    const thisWeekTotal = thisWeekCases.length;
    const thisWeekCompleted = thisWeekCases.filter((c) => c.status === 'COMPLETED').length;
    const lastWeekTotal = lastWeekCases.length;
    const lastWeekCompleted = lastWeekCases.filter((c) => c.status === 'COMPLETED').length;

    const thisWeekRate = thisWeekTotal > 0 ? thisWeekCompleted / thisWeekTotal : 0;
    const lastWeekRate = lastWeekTotal > 0 ? lastWeekCompleted / lastWeekTotal : 0;
    const diff = thisWeekRate - lastWeekRate;
    let trend: 'up' | 'down' | 'stable' = 'stable';
    if (diff > 0.01) trend = 'up';
    else if (diff < -0.01) trend = 'down';
    const percentage = Math.round(Math.abs(diff) * 10000) / 100;

    // 6. totalActiveUsers
    const totalActiveUsers = allBaleUserIds.length;

    return NextResponse.json({
      avgProcessingTime,
      peakHour,
      peakHourCount,
      peakHourLabel,
      todayCompleted,
      todayFailed,
      successRateTrend: { trend, percentage },
      totalActiveUsers,
    });
  } catch (error) {
    console.error('KPI fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch KPIs' }, { status: 500 });
  }
}

function getStartOfThisWeek(now: Date): Date {
  const d = new Date(now);
  const day = d.getDay();
  const diff = day === 0 ? 6 : day - 1;
  d.setDate(d.getDate() - diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function getStartOfLastWeek(now: Date): Date {
  const thisWeek = getStartOfThisWeek(now);
  const d = new Date(thisWeek);
  d.setDate(d.getDate() - 7);
  return d;
}

function getPersianHourLabel(hour: number): string {
  const persianDigits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹', '۱۰', '۱۱', '۱۲', '۱۳', '۱۴', '۱۵', '۱۶', '۱۷', '۱۸', '۱۹', '۲۰', '۲۱', '۲۲', '۲۳'];
  const persianNum = persianDigits[hour] || String(hour);
  if (hour === 0) return `${persianNum} شب`;
  if (hour < 6) return `${persianNum} صبح`;
  if (hour < 12) return `${persianNum} صبح`;
  if (hour === 12) return `${persianNum} ظهر`;
  if (hour < 17) return `${persianNum} بعد از ظهر`;
  if (hour < 21) return `${persianNum} عصر`;
  return `${persianNum} شب`;
}
