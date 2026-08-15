import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const existing = await db.case.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json({ error: 'Case not found' }, { status: 404 });
    }

    if (existing.status !== 'COMPLETED') {
      return NextResponse.json(
        { error: 'Only completed cases can be moved to ready-to-send' },
        { status: 400 }
      );
    }

    const updated = await db.case.update({
      where: { id },
      data: {
        isInReadyToSend: true,
        readyToSendAt: new Date(),
        status: 'READY_TO_SEND',
      },
    });

    await db.activityLog.create({
      data: {
        caseId: id,
        action: 'MOVE_TO_READY',
        details: 'انتقال به بخش آماده ارسال',
      },
    });

    return NextResponse.json(updated);
  } catch (error) {
    console.error('Ready error:', error);
    return NextResponse.json({ error: 'Failed to move case' }, { status: 500 });
  }
}
