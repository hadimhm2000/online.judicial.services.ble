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

    if (!existing.isInReadyToSend) {
      return NextResponse.json(
        { error: 'Case is not in ready-to-send section' },
        { status: 400 }
      );
    }

    const updated = await db.case.update({
      where: { id },
      data: {
        isInReadyToSend: false,
        sentToUserAt: new Date(),
        sentViaBot: true,
        status: 'COMPLETED',
        readyToSendAt: null,
      },
    });

    await db.adminAction.create({
      data: {
        caseId: id,
        actionType: 'SEND_TO_USER',
        adminNote: 'تأیید و ارسال از بخش آماده ارسال',
        sentViaBot: true,
      },
    });

    await db.activityLog.create({
      data: {
        caseId: id,
        action: 'CONFIRM_SEND',
        details: 'تأیید ارسال به کاربر - حذف از بخش آماده ارسال',
      },
    });

    // Auto-sync to Google Sheets
    import('@/lib/google-sheets').then(m => m.appendNewCase(id)).catch(() => {});

    return NextResponse.json(updated);
  } catch (error) {
    console.error('Confirm send error:', error);
    return NextResponse.json({ error: 'Failed to confirm send' }, { status: 500 });
  }
}
