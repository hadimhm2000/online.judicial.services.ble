import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';
import { Prisma } from '@prisma/client';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get('page') || '1');
    const limit = parseInt(searchParams.get('limit') || '20');
    const status = searchParams.get('status') || '';
    const search = searchParams.get('search') || '';

    const where: Prisma.BotMessageWhereInput = {};
    if (status) where.status = status;
    if (search) {
      where.OR = [
        { fullName: { contains: search } },
        { baleUserId: { contains: search } },
        { messageText: { contains: search } },
      ];
    }

    const [messages, total] = await Promise.all([
      db.botMessage.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * limit,
        take: limit,
      }),
      db.botMessage.count({ where }),
    ]);

    return NextResponse.json({
      messages,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Bot messages list error:', error);
    return NextResponse.json({ error: 'خطا در دریافت پیام‌ها' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { baleUserId, fullName, messageText, fileUrl, fileName, costToman } = body;

    if (!baleUserId || !messageText) {
      return NextResponse.json(
        { error: 'شناسه بله و متن پیام الزامی است' },
        { status: 400 }
      );
    }

    // ⭐ هزینهٔ پیام — ورودی UI به «تومان» است؛ ذخیره به «ریال» (مطابق فیلد fee پرونده‌ها)
    let costAmountRial = 0;
    if (costToman !== undefined && costToman !== null && costToman !== '') {
      const toman = parseInt(String(costToman), 10);
      if (Number.isFinite(toman)) {
        if (toman < 0) {
          return NextResponse.json(
            { error: 'مبلغ هزینه نمی‌تواند منفی باشد' },
            { status: 400 }
          );
        }
        if (toman > 0) {
          costAmountRial = toman * 10;
        }
      }
    }

    const message = await db.botMessage.create({
      data: {
        baleUserId,
        fullName: fullName || '',
        messageText,
        fileUrl: fileUrl || null,
        fileName: fileName || null,
        status: 'PENDING',
        costAmount: costAmountRial,
        costStatus: costAmountRial > 0 ? 'AWAITING_PAYMENT' : 'NONE',
      },
    });

    await db.activityLog.create({
      data: {
        action: 'BOT_MESSAGE_CREATED',
        details:
          costAmountRial > 0
            ? `پیام جدید برای ${fullName || baleUserId} - با هزینه ${costAmountRial / 10} تومان - در انتظار ارسال`
            : `پیام جدید برای ${fullName || baleUserId} - در انتظار ارسال`,
      },
    });

    return NextResponse.json(message, { status: 201 });
  } catch (error) {
    console.error('Bot message create error:', error);
    return NextResponse.json({ error: 'خطا در ایجاد پیام' }, { status: 500 });
  }
}
