import { db } from '@/lib/db';
import { sendBaleMessage, sendBaleDocument } from '@/lib/bale';
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const message = await db.botMessage.findUnique({ where: { id } });
    if (!message) {
      return NextResponse.json({ error: 'پیام یافت نشد' }, { status: 404 });
    }

    if (!message.baleUserId) {
      return NextResponse.json(
        { error: 'شناسه بله برای این پیام ثبت نشده است' },
        { status: 400 }
      );
    }

    // ارسال پیام متنی
    await sendBaleMessage(message.baleUserId, message.messageText);

    // ارسال فایل پیوست اگر وجود داشته باشد
    if (message.fileUrl && message.fileName) {
      const filePath = path.join(process.cwd(), 'public', message.fileUrl);
      await sendBaleDocument(
        message.baleUserId,
        filePath,
        message.fileName
      );
    }

    const updated = await db.botMessage.update({
      where: { id },
      data: {
        status: 'SENT',
        sentAt: new Date(),
      },
    });

    await db.activityLog.create({
      data: {
        action: 'BOT_MESSAGE_SENT',
        details: message.fileUrl
          ? `پیام و فایل «${message.fileName}» ارسال شد برای ${message.fullName || message.baleUserId}`
          : `پیام ارسال شد برای ${message.fullName || message.baleUserId}`,
      },
    });

    return NextResponse.json(updated);
  } catch (error: unknown) {
    console.error('Bot message send error:', error);

    const errorMessage =
      error instanceof Error ? error.message : 'خطا در ارسال پیام';

    try {
      const { id } = await params;
      await db.botMessage.update({
        where: { id },
        data: {
          status: 'FAILED',
          errorDetails: errorMessage,
        },
      });
    } catch {
      // نادیده بگیر
    }

    return NextResponse.json({ error: errorMessage }, { status: 500 });
  }
}
