/**
 * ⭐ v1.3 — اصلاح یک‌بارهٔ داده‌های تاریخی استعلام‌ها
 *
 * ریشهٔ مشکل: تا قبل از v1.3، استعلام‌ها «بعد از پرداخت موفق کیف پول بله»
 * در پنل ثبت می‌شدند ولی با feeStatus=UNPAID. برای همین:
 *   - استعلام‌های پرداخت‌شده در «درآمد» شمرده نمی‌شدند؛
 *   - در کارت «پرداخت نشده» انباشته می‌شدند؛
 *   - طبق قاعدهٔ جدید سود («هر مبلغ استعلام مستقیم سود است») جا می‌ماندند.
 *
 * این اسکریپت همهٔ استعلام‌هایی را که مبلغی دارند و هنوز UNPAID علامت
 * خورده‌اند، به PAID تبدیل می‌کند. فقط یک‌بار اجرا شود:
 *
 *   node fix_inquiry_paid.js
 *
 * (در همان پوشه‌ای که package.json و prisma/ هستند)
 */
const { PrismaClient } = require('@prisma/client');

const db = new PrismaClient();

async function main() {
  const affected = await db.case.findMany({
    where: { serviceType: 'INQUIRY', fee: { gt: 0 }, feeStatus: 'UNPAID' },
    select: { id: true },
  });

  if (affected.length === 0) {
    console.log('✅ هیچ استعلام پرداخت‌نشدهٔ قدیمی وجود ندارد — نیازی به اصلاح نیست.');
    return;
  }

  const res = await db.case.updateMany({
    where: { serviceType: 'INQUIRY', fee: { gt: 0 }, feeStatus: 'UNPAID' },
    data: { feeStatus: 'PAID' },
  });

  console.log(`✅ ${res.count} استعلام پرداخت‌شده به وضعیت «پرداخت شده» تغییر یافت.`);
  console.log('   از این پس در «درآمد کل» و «سود» لحاظ می‌شوند.');
}

main()
  .catch((e) => {
    console.error('❌ خطا:', e);
    process.exitCode = 1;
  })
  .finally(() => db.$disconnect());
