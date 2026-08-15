import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const records = await db.exemptUser.findMany({
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json({ records, count: records.length });
  } catch (error) {
    console.error('Error fetching exempt users:', error);
    return NextResponse.json({ records: [], count: 0 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { baleUserId, fullName, reason } = body;

    if (!baleUserId || typeof baleUserId !== 'string' || baleUserId.trim().length === 0) {
      return NextResponse.json({ error: 'baleUserId is required' }, { status: 400 });
    }

    const existing = await db.exemptUser.findUnique({
      where: { baleUserId: baleUserId.trim() },
    });

    if (existing) {
      return NextResponse.json({ error: 'این شناسه بله قبلاً ثبت شده است' }, { status: 409 });
    }

    const record = await db.exemptUser.create({
      data: {
        baleUserId: baleUserId.trim(),
        fullName: fullName?.trim() || null,
        reason: reason?.trim() || null,
      },
    });

    return NextResponse.json({ record }, { status: 201 });
  } catch (error) {
    console.error('Error creating exempt user:', error);
    return NextResponse.json({ error: 'Failed to create exempt user' }, { status: 500 });
  }
}
