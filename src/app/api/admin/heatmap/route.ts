import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET() {
  try {
    const cases = await db.case.findMany({
      select: { createdAt: true },
    });

    const grid: Record<string, number> = {};
    const byHour = new Array(24).fill(0);
    const byDay = new Array(7).fill(0);

    for (const c of cases) {
      const d = new Date(c.createdAt);
      const jsDay = d.getDay();
      const persianDay = jsDay === 6 ? 0 : jsDay + 1;
      const hour = d.getHours();
      const key = `${hour}-${persianDay}`;
      grid[key] = (grid[key] || 0) + 1;
      byHour[hour]++;
      byDay[persianDay]++;
    }

    const data: { hour: number; day: number; count: number }[] = [];
    for (let h = 0; h < 24; h++) {
      for (let d = 0; d < 7; d++) {
        const count = grid[`${h}-${d}`] || 0;
        if (count > 0) {
          data.push({ hour: h, day: d, count });
        }
      }
    }

    return NextResponse.json({ data, totals: { byHour, byDay } });
  } catch (error) {
    console.error('Heatmap error:', error);
    return NextResponse.json({ data: [], totals: { byHour: new Array(24).fill(0), byDay: new Array(7).fill(0) } });
  }
}
