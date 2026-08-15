import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

const STATUS_ORDER = [
  'PENDING_PAYMENT',
  'PROCESSING',
  'INCOMPLETE',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
  'READY_TO_SEND',
] as const;

const STEP_VALUES = ['PAYMENT', 'DOCUMENT', 'PROCESSING', 'RESULT', 'READY', 'SENT', null] as const;

export async function GET() {
  try {
    const allCases = await db.case.findMany({
      select: {
        status: true,
        lastCompletedStep: true,
      },
    });

    const total = allCases.length;

    // Build statuses map: status -> { count, breakdown: { step -> count } }
    const statuses: Record<string, { count: number; breakdown: Record<string, number> }> = {};
    for (const s of STATUS_ORDER) {
      statuses[s] = { count: 0, breakdown: {} };
    }

    // Count cases per status
    for (const c of allCases) {
      if (!statuses[c.status]) {
        statuses[c.status] = { count: 0, breakdown: {} };
      }
      statuses[c.status].count++;
      const step = c.lastCompletedStep || 'null';
      statuses[c.status].breakdown[step] = (statuses[c.status].breakdown[step] || 0) + 1;
    }

    // Build transitions: status -> lastCompletedStep implies a flow from step to status
    // We map transitions as: if status is X and lastCompletedStep is Y, it shows Y -> X flow
    const transitionMap: Record<string, number> = {};
    for (const c of allCases) {
      const from = c.lastCompletedStep || 'NONE';
      const to = c.status;
      const key = `${from}->${to}`;
      transitionMap[key] = (transitionMap[key] || 0) + 1;
    }

    // Convert transition map to sorted array, only include transitions with count > 0
    const transitions = Object.entries(transitionMap)
      .filter(([, count]) => count > 0)
      .map(([key, count]) => {
        const [from, to] = key.split('->');
        return { from, to, count };
      })
      .sort((a, b) => b.count - a.count);

    // Ensure all statuses are present even with 0 count
    for (const s of STATUS_ORDER) {
      if (!statuses[s]) {
        statuses[s] = { count: 0, breakdown: {} };
      }
    }

    return NextResponse.json({ statuses, transitions, total });
  } catch (error) {
    console.error('Pipeline error:', error);
    return NextResponse.json({ error: 'Failed to fetch pipeline data' }, { status: 500 });
  }
}
