import { NextRequest, NextResponse } from 'next/server';
import { writeFile, mkdir } from 'fs/promises';
import path from 'path';
import { randomUUID } from 'crypto';

// حداکثر حجم هر فایل: 20 مگابایت (محدودیت بله برای ارسال فایل توسط بات)
const MAX_FILE_BYTES = 20 * 1024 * 1024;

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const files = formData.getAll('files').filter((f): f is File => f instanceof File);

    if (!files.length) {
      return NextResponse.json({ error: 'فایلی ارسال نشده است' }, { status: 400 });
    }

    for (const file of files) {
      if (file.size > MAX_FILE_BYTES) {
        return NextResponse.json(
          { error: `فایل «${file.name}» بیشتر از حد مجاز (۲۰ مگابایت) است` },
          { status: 400 }
        );
      }
    }

    const uploadDir = path.join(process.cwd(), 'public', 'uploads');
    await mkdir(uploadDir, { recursive: true });

    const results: { url: string; name: string }[] = [];

    for (const file of files) {
      const buffer = Buffer.from(await file.arrayBuffer());
      const safeName = file.name.replace(/[^a-zA-Z0-9.\-_\u0600-\u06FF]/g, '_');
      const storedName = `${randomUUID()}-${safeName}`;
      await writeFile(path.join(uploadDir, storedName), buffer);
      results.push({ url: `/uploads/${storedName}`, name: file.name });
    }

    return NextResponse.json({ success: true, files: results });
  } catch (error) {
    console.error('Upload error:', error);
    return NextResponse.json({ error: 'خطا در آپلود فایل' }, { status: 500 });
  }
}
