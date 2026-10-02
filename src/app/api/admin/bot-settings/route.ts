import { db } from '@/lib/db';
import type { Prisma } from '@prisma/client';
import { NextRequest, NextResponse } from 'next/server';
import { BOT_SETTING_DEFS, validateBotSetting } from '@/lib/bot-settings';

// ⭐ v1.9 — تنظیمات ربات قابل ویرایش از پنل (bot_settings.py هر ۶۰ ثانیه می‌خواند)
//   GET → { settings: [{ key, value, updatedAt }] }
//   PUT { values: { [key]: string } } — مقدار خالی = حذف (بازگشت به پیش‌فرض ربات)

export async function GET() {
  try {
    const settings = await db.botSetting.findMany({ orderBy: { key: 'asc' } });
    return NextResponse.json({ settings });
  } catch (error) {
    console.error('[bot-settings] GET error:', error);
    return NextResponse.json({ error: 'خطا در خواندن تنظیمات' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const values = body?.values;
    if (!values || typeof values !== 'object') {
      return NextResponse.json({ error: 'values الزامی است' }, { status: 400 });
    }

    const errors: Record<string, string> = {};
    const ops: Prisma.PrismaPromise<unknown>[] = [];
    for (const [key, raw] of Object.entries(values)) {
      const def = BOT_SETTING_DEFS.find((d) => d.key === key);
      if (!def) {
        errors[key] = 'کلید ناشناخته';
        continue;
      }
      const value = String(raw ?? '').trim();
      const err = validateBotSetting(def, value);
      if (err) {
        errors[key] = err;
        continue;
      }
      ops.push(
        value === ''
          ? db.botSetting.deleteMany({ where: { key } })
          : db.botSetting.upsert({ where: { key }, create: { key, value }, update: { value } })
      );
    }
    if (Object.keys(errors).length > 0) {
      return NextResponse.json({ error: 'مقادیر نامعتبر', errors }, { status: 400 });
    }
    await db.$transaction(ops);
    await db.activityLog.create({
      data: { action: 'BOT_SETTINGS_UPDATED', details: Object.keys(values).join(', ') },
    });
    const settings = await db.botSetting.findMany({ orderBy: { key: 'asc' } });
    return NextResponse.json({ settings });
  } catch (error) {
    console.error('[bot-settings] PUT error:', error);
    return NextResponse.json({ error: 'خطا در ذخیرهٔ تنظیمات' }, { status: 500 });
  }
}
