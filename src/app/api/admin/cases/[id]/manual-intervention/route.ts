import { db } from '@/lib/db';
import { sendBaleMessage, sendBaleDocument } from '@/lib/bale';
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';

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
    const uploadedFileUrls: string[] = body.uploadedFileUrls || [];
    const shouldSendViaBot = actionType === 'SEND_TO_USER' && Boolean(body.sentViaBot);

    // If sending to the user, actually deliver via the Bale bot BEFORE
    // touching the database, so a failed send never gets recorded as success.
    if (shouldSendViaBot) {
      if (!existing.baleUserId) {
        return NextResponse.json(
          { error: 'شناسه بله این کاربر موجود نیست' },
          { status: 400 }
        );
      }

      const messageText =
        adminNote?.trim() || 'نتیجه پرونده شما بررسی و تکمیل شد.';

      try {
        await sendBaleMessage(existing.baleUserId, messageText);

        for (const url of uploadedFileUrls) {
          const filePath = path.join(process.cwd(), 'public', url);
          const displayName = path
            .basename(url)
            .replace(/^[0-9a-f-]{36}-/i, ''); // remove the random-id prefix added on upload
          await sendBaleDocument(existing.baleUserId, filePath, displayName);
        }
      } catch (sendError) {
        console.error('Bale send error:', sendError);
        return NextResponse.json(
          {
            error:
              sendError instanceof Error
                ? sendError.message
                : 'ارسال پیام به کاربر از طریق ربات ناموفق بود',
          },
          { status: 502 }
        );
      }
    }

    // Create admin action record
    const adminAction = await db.adminAction.create({
      data: {
        caseId: id,
        actionType: actionType || 'MANUAL_INTERVENTION',
        adminNote,
        uploadedFileUrls: uploadedFileUrls.length ? JSON.stringify(uploadedFileUrls) : null,
        sentViaBot: shouldSendViaBot,
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
      updateData.sentViaBot = shouldSendViaBot;
      updateData.status = 'COMPLETED';
      updateData.isInReadyToSend = false;
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
