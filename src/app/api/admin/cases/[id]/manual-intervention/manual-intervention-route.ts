import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { adminNote, actionType, newStatus } = body;

    const existing = await db.case.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json({ error: 'Case not found' }, { status: 404 });
    }

    // Handle file uploads if present
    const uploadedFileUrls = body.uploadedFileUrls || null;

    // Create admin action record
    const adminAction = await db.adminAction.create({
      data: {
        caseId: id,
        actionType: actionType || 'MANUAL_INTERVENTION',
        adminNote,
        uploadedFileUrls: uploadedFileUrls ? JSON.stringify(uploadedFileUrls) : null,
        sentViaBot: body.sentViaBot || false,
      },
    });

    // Update case status if provided
    const updateData: Record<string, unknown> = {
      updatedAt: new Date(),
    };

    if (newStatus) {
      updateData.status = newStatus;
    }

    // If this is a "send to user" action
    if (actionType === 'SEND_TO_USER') {
      updateData.sentToUserAt = new Date();
      updateData.sentViaBot = true;
      updateData.status = 'COMPLETED';
      updateData.isInReadyToSend = false;

      // In a real scenario, here we would call the Bale bot API
      // to send the result to the user via bot
      // bot.sendMessage(baleUserId, message, files)
    }

    // If admin resolves a failed case
    if (newStatus === 'COMPLETED' && existing.status === 'FAILED') {
      updateData.errorDetails = null;
      updateData.errorStep = null;
    }

    if (Object.keys(updateData).length > 1) {
      await db.case.update({
        where: { id },
        data: updateData as never,
      });
    }

    // Auto-sync to Google Sheets
    if (newStatus) {
      import('@/lib/google-sheets').then(m => m.appendNewCase(id)).catch(() => {});
    }

    // Create activity log
    await db.activityLog.create({
      data: {
        caseId: id,
        action: actionType || 'MANUAL_INTERVENTION',
        details: adminNote || 'مداخله دستی ادمین',
      },
    });

    return NextResponse.json({
      success: true,
      adminAction,
      message: actionType === 'SEND_TO_USER'
        ? `نتیجه با موفقیت از طریق ربات برای کاربر ${existing.fullName} ارسال شد`
        : 'مداخله دستی با موفقیت ثبت شد',
    });
  } catch (error) {
    console.error('Manual intervention error:', error);
    return NextResponse.json({ error: 'Failed to process intervention' }, { status: 500 });
  }
}
