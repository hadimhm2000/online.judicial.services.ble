import path from 'path';

// مسیر فایل‌های آپلودی پنل — همه‌چیز باید داخل همین پوشه باشد
export const UPLOAD_DIR = path.join(process.cwd(), 'public', 'uploads');

/**
 * تبدیل آدرس فایل آپلودی (مثل /uploads/<uuid>-name.pdf) به مسیر روی دیسک.
 * اگر آدرس به بیرون از public/uploads اشاره کند (مثلاً ../.env)، null برمی‌گردد
 * تا هیچ فایل دیگری از سرور برای کاربر ارسال نشود.
 */
export function resolveUploadPath(fileUrl: string | null | undefined): string | null {
  if (!fileUrl || typeof fileUrl !== 'string') return null;
  const resolved = path.resolve(path.join(process.cwd(), 'public', fileUrl));
  if (!resolved.startsWith(UPLOAD_DIR + path.sep)) return null;
  return resolved;
}
