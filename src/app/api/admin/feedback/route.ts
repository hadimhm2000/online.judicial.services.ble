import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ v1.9 — نظرسنجی پس از تحویل (feedback.py)
//   POST { baleUserId, fullName?, rating (1..5), context? }   ← ربات
//   GET  ?days=30  → { summary: { count, average, distribution }, items: [...] }

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const baleUserId = String(body?.baleUserId || '').trim();
    const rating = Number(body?.rating);
    if (!/^\d+$/.test(baleUserId) || !Number.isInteger(rating) || rating < 1 || rating > 5) {
      return NextResponse.json({ error: 'داده نامعتبر' }, { status: 400 });
    }
    const item = await db.feedback.create({
      data: {
        baleUserId,
        rating,
        fullName: body?.fullName ? String(body.fullName).slice(0, 120) : null,
        context: body?.context ? String(body.context).slice(0, 200) : null,
      },
    });
    return NextResponse.json({ item }, { status: 201 });
  } catch (error) {
    console.error('[feedback] POST error:', error);
    return NextResponse.json({ error: 'خطا در ثبت نظر' }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const days = Math.min(Math.max(parseInt(searchParams.get('days') || '30') || 30, 1), 365);
    const since = new Date(Date.now() - days * 86400_000);
    const items = await db.feedback.findMany({
      where: { createdAt: { gte: since } },
      orderBy: { createdAt: 'desc' },
      take: 500,
    });
    const distribution = [1, 2, 3, 4, 5].map((r) => items.filter((i) => i.rating === r).length);
    const average = items.length ? items.reduce((s, i) => s + i.rating, 0) / items.length : 0;
    return NextResponse.json({
      summary: { count: items.length, average, distribution },
      items: items.slice(0, 100),
    });
  } catch (error) {
    console.error('[feedback] GET error:', error);
    return NextResponse.json({ error: 'خطا در خواندن نظرات' }, { status: 500 });
  }
}
