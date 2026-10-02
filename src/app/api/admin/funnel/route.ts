import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

// ⭐ v1.9 — قیف تبدیل (funnel.py)
//   POST { events: [{ baleUserId, flow, step, at }] }   ← ربات، دسته‌ای
//   GET  ?days=30 → { flows: [{ flow, entered, paid, steps: [{ step, users }] }] }

const MAX_EVENTS = 1000;
const NAME_RE = /^[A-Za-z0-9_]{1,80}$/;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const events = Array.isArray(body?.events) ? body.events.slice(0, MAX_EVENTS) : [];
    const data: { baleUserId: string; flow: string; step: string; createdAt: Date }[] = [];
    for (const e of events) {
      const baleUserId = String(e?.baleUserId || '');
      const flow = String(e?.flow || '');
      const step = String(e?.step || '');
      if (!/^\d+$/.test(baleUserId) || !NAME_RE.test(flow) || !NAME_RE.test(step)) continue;
      const at = e?.at ? new Date(e.at) : new Date();
      data.push({ baleUserId, flow, step, createdAt: isNaN(at.getTime()) ? new Date() : at });
    }
    if (data.length) await db.funnelEvent.createMany({ data });
    return NextResponse.json({ saved: data.length }, { status: 201 });
  } catch (error) {
    console.error('[funnel] POST error:', error);
    return NextResponse.json({ error: 'خطا در ثبت رویدادها' }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const days = Math.min(Math.max(parseInt(searchParams.get('days') || '30') || 30, 1), 90);
    const since = new Date(Date.now() - days * 86400_000);
    const rows = await db.funnelEvent.findMany({
      where: { createdAt: { gte: since } },
      select: { baleUserId: true, flow: true, step: true },
    });

    const byFlow = new Map<string, { users: Set<string>; steps: Map<string, Set<string>> }>();
    for (const r of rows) {
      let f = byFlow.get(r.flow);
      if (!f) {
        f = { users: new Set(), steps: new Map() };
        byFlow.set(r.flow, f);
      }
      f.users.add(r.baleUserId);
      let s = f.steps.get(r.step);
      if (!s) {
        s = new Set();
        f.steps.set(r.step, s);
      }
      s.add(r.baleUserId);
    }

    // ترتیب مراحل: بر اساس تعداد کاربرانی که به آن رسیده‌اند (نزولی)؛ PAID آخر
    const flows = [...byFlow.entries()].map(([flow, f]) => {
      const steps = [...f.steps.entries()]
        .filter(([step]) => step !== 'PAID')
        .map(([step, users]) => ({ step, users: users.size }))
        .sort((a, b) => b.users - a.users);
      return { flow, entered: f.users.size, paid: f.steps.get('PAID')?.size ?? 0, steps };
    }).sort((a, b) => b.entered - a.entered);

    return NextResponse.json({ days, flows });
  } catch (error) {
    console.error('[funnel] GET error:', error);
    return NextResponse.json({ error: 'خطا در محاسبهٔ قیف' }, { status: 500 });
  }
}
