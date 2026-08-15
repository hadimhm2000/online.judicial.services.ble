import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

interface WorkingHourItem {
  dayOfWeek: number;
  startHour: number;
  startMin: number;
  endHour: number;
  endMin: number;
  enabled: boolean;
}

const DEFAULT_SCHEDULE: WorkingHourItem[] = [
  { dayOfWeek: 0, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 1, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 2, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 3, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 4, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 5, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 6, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
];

export async function GET() {
  try {
    const rows = await db.workingHour.findMany({
      orderBy: { dayOfWeek: 'asc' },
    });

    if (rows.length === 0) {
      return NextResponse.json({ schedule: DEFAULT_SCHEDULE });
    }

    const schedule: WorkingHourItem[] = rows.map((r) => ({
      dayOfWeek: r.dayOfWeek,
      startHour: r.startHour,
      startMin: r.startMin,
      endHour: r.endHour,
      endMin: r.endMin,
      enabled: r.enabled,
    }));

    return NextResponse.json({ schedule });
  } catch {
    return NextResponse.json({ schedule: DEFAULT_SCHEDULE });
  }
}

export async function PUT(req: Request) {
  try {
    const body = await req.json();
    const schedule: WorkingHourItem[] = body.schedule;

    if (!Array.isArray(schedule)) {
      return NextResponse.json({ error: 'schedule must be an array' }, { status: 400 });
    }

    for (const item of schedule) {
      if (typeof item.dayOfWeek !== 'number' || item.dayOfWeek < 0 || item.dayOfWeek > 6) {
        return NextResponse.json({ error: 'Invalid dayOfWeek' }, { status: 400 });
      }
      if (typeof item.startHour !== 'number' || item.startHour < 0 || item.startHour > 23) {
        return NextResponse.json({ error: 'Invalid startHour' }, { status: 400 });
      }
      if (typeof item.startMin !== 'number' || item.startMin < 0 || item.startMin > 59) {
        return NextResponse.json({ error: 'Invalid startMin' }, { status: 400 });
      }
      if (typeof item.endHour !== 'number' || item.endHour < 0 || item.endHour > 23) {
        return NextResponse.json({ error: 'Invalid endHour' }, { status: 400 });
      }
      if (typeof item.endMin !== 'number' || item.endMin < 0 || item.endMin > 59) {
        return NextResponse.json({ error: 'Invalid endMin' }, { status: 400 });
      }
    }

    await db.workingHour.deleteMany();

    await db.workingHour.createMany({
      data: schedule.map((item) => ({
        dayOfWeek: item.dayOfWeek,
        startHour: item.startHour,
        startMin: item.startMin,
        endHour: item.endHour,
        endMin: item.endMin,
        enabled: item.enabled,
      })),
    });

    return NextResponse.json({ message: 'Schedule updated successfully', schedule });
  } catch (error) {
    console.error('Error updating working hours:', error);
    return NextResponse.json({ error: 'Failed to update schedule' }, { status: 500 });
  }
}
