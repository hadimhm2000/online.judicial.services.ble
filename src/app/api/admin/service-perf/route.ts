import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

const SERVICE_TYPES = ['INQUIRY', 'LAVAYEH', 'EZHHARNAMEH', 'EALAM_VAKALAHT', 'STAMP_CALC'] as const;

export async function GET() {
  try {
    const allCases = await db.case.findMany({
      select: {
        serviceType: true,
        status: true,
        fee: true,
        createdAt: true,
        updatedAt: true,
      },
    });

    const grouped: Record<string, typeof allCases> = {};
    for (const st of SERVICE_TYPES) {
      grouped[st] = [];
    }

    for (const c of allCases) {
      if (grouped[c.serviceType]) {
        grouped[c.serviceType].push(c);
      }
    }

    const services = SERVICE_TYPES.map((serviceType) => {
      const cases = grouped[serviceType];
      const count = cases.length;
      const completedCases = cases.filter((c) => c.status === 'COMPLETED');
      const completedCount = completedCases.length;
      const failedCount = cases.filter((c) => c.status === 'FAILED').length;

      let avgProcessingTime = 0;
      if (completedCount > 0) {
        const totalMs = completedCases.reduce((sum, c) => {
          const created = new Date(c.createdAt).getTime();
          const updated = new Date(c.updatedAt).getTime();
          return sum + (updated - created);
        }, 0);
        avgProcessingTime = Math.round((totalMs / completedCount) / (1000 * 60 * 60) * 10) / 10;
      }

      const totalRevenue = completedCases.reduce((sum, c) => sum + c.fee, 0);
      const successRate = count > 0 ? Math.round((completedCount / count) * 1000) / 10 : 0;

      return {
        serviceType,
        count,
        completedCount,
        failedCount,
        avgProcessingTime,
        totalRevenue,
        successRate,
      };
    });

    return NextResponse.json({ services });
  } catch (error) {
    console.error('Service perf error:', error);
    return NextResponse.json({ services: [] });
  }
}
