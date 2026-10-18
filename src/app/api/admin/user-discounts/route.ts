import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const records = await db.userDiscount.findMany({
      orderBy: { updatedAt: 'desc' },
    });
    return NextResponse.json({ records, count: records.length });
  } catch (error) {
    console.error('Error fetching user discounts:', error);
    return NextResponse.json({ records: [], count: 0 });
  }
}

// ثبت یا به‌روزرسانی تخفیف — شناسهٔ تکراری، درصد قبلی را جایگزین می‌کند
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { baleUserId, fullName, reason } = body;
    const percent = Number(body.percent);

    if (!baleUserId || typeof baleUserId !== 'string' || baleUserId.trim().length === 0) {
      return NextResponse.json({ error: 'شناسه بله الزامی است' }, { status: 400 });
    }
    if (!Number.isInteger(percent) || percent < 1 || percent > 100) {
      return NextResponse.json({ error: 'درصد تخفیف باید عددی صحیح بین ۱ تا ۱۰۰ باشد' }, { status: 400 });
    }

    const data = {
      fullName: fullName?.trim() || null,
      percent,
      reason: reason?.trim() || null,
    };
    const record = await db.userDiscount.upsert({
      where: { baleUserId: baleUserId.trim() },
      create: { baleUserId: baleUserId.trim(), ...data },
      update: data,
    });

    return NextResponse.json({ record }, { status: 201 });
  } catch (error) {
    console.error('Error saving user discount:', error);
    return NextResponse.json({ error: 'Failed to save user discount' }, { status: 500 });
  }
}
