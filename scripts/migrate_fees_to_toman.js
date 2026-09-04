/**
 * migrate_fees_to_toman.js — مهاجرت یک‌بارهٔ داده‌های قدیمی پنل به «تومان»
 *
 * ⭐ چرا لازم است؟
 *   قبل از نسخهٔ v1.4، ربات برای بعضی سرویس‌ها fee را به «ریال» در پنل
 *   ثبت می‌کرد و برای بعضی (استعلام‌ها) به «تومان». پنل همه‌جا fee را
 *   «تومان» نمایش می‌داد؛ برای همین پرونده‌های لایحه/چک/تجدیدنظر و ...
 *   ۱۰ برابر دیده می‌شدند.
 *   از v1.4 همهٔ feeها و systemCostها به «تومان» ثبت می‌شوند.
 *   این اسکریپت داده‌های قدیمی (ریال) را یکبار به تومان تبدیل می‌کند.
 *
 * ⚠️ فقط یکبار اجرا شود:
 *     node scripts/migrate_fees_to_toman.js
 *
 * سرویس‌هایی که fee قدیمی‌شان «ریال» بود (قبل از v1.4):
 *   LAVAYEH, EZHHARNAMEH, CHECK, TAJDID_NAZAR, EALAM_VAKALAHT, ADMIN_SEND
 *   (+ هر svc ثبت‌شده از /fee مدیر — در صورت وجود serviceType دیگری،
 *    پیش‌فرض ریال در نظر گرفته می‌شود مگر در لیست سفید تومان)
 *
 * سرویس‌هایی که از اول «تومان» بودند (دست نمی‌خورند):
 *   INQUIRY, REGIONAL_VALUE, STAMP_CALC, UNKNOWN, NONE
 *
 * systemCost: قبل از v1.4 همیشه «ریال» ثبت می‌شد → برای همهٔ پرونده‌های
 * دارای systemCost تقسیم بر ۱۰ می‌شود (اگر قبلاً تومان شده باشد، مقدار
 * کوچک است و دوباره تقسیم نمی‌شود — آستانه به‌عنوان سنجه).
 *
 * قبل از اجرا بکاپ دیتابیس بگیرید!
 */
const { PrismaClient } = require('@prisma/client');
const db = new PrismaClient();

// سرویس‌هایی که fee آن‌ها از اول «تومان» بوده — دست نمی‌خورند
const TOMAN_SERVICES = new Set([
  'INQUIRY',
  'REGIONAL_VALUE',
  'STAMP_CALC',
  'SUBSCRIPTION',
  'UNKNOWN',
  'NONE',
  '',
]);

// سنجهٔ تشخیص ریال بودن: مقادیر ریالِ این سرویس‌ها همیشه بزرگ‌اند
// (کمترین فاکتور واقعی لایحه ≈ ۴۰,۰۰۰ تومان = ۴۰۰,۰۰۰ ریال)
const RIAL_THRESHOLD = 50_000;

function isOldRial(serviceType, fee) {
  if (!fee || fee <= 0) return false;
  if (TOMAN_SERVICES.has(serviceType)) return false;
  // feeهای ریال این سرویس‌ها عملاً همیشه ≥ ۱۰۰,۰۰۰ (۱۰,۰۰۰ تومان) هستند
  return fee >= RIAL_THRESHOLD * 2;
}

async function main() {
  console.log('🔄 شروع مهاجرت feeها به تومان...');

  const cases = await db.case.findMany({
    select: { id: true, serviceType: true, fee: true, systemCost: true },
  });
  console.log(` تعداد کل پرونده‌ها: ${cases.length}`);

  let feeUpdated = 0;
  let costUpdated = 0;
  const skipped = [];

  for (const c of cases) {
    const updates = {};

    // ── fee: ریال → تومان (فقط سرویس‌های ریالی با مقادیر بزرگ) ──
    if (isOldRial(c.serviceType, c.fee)) {
      const toman = Math.floor(c.fee / 10);
      if (toman > 0) {
        updates.fee = toman;
        feeUpdated++;
      }
    } else if (c.fee > 0 && !TOMAN_SERVICES.has(c.serviceType) && c.fee < RIAL_THRESHOLD * 2) {
      skipped.push(`${c.id}:${c.serviceType}:fee=${c.fee}`);
    }

    // ── systemCost: ریال → تومان ──
    if (c.systemCost !== null && c.systemCost !== undefined && c.systemCost > 0) {
      // systemCostهای ریال عملاً ≥ ۱۰۰,۰۰۰ هستند؛ مقادیر کوچک‌تر از قبل
      // تومان بوده‌اند (پس از v1.4) — دوباره تقسیم نمی‌شوند.
      if (c.systemCost >= RIAL_THRESHOLD * 2) {
        updates.systemCost = Math.floor(c.systemCost / 10);
        costUpdated++;
      }
    }

    if (Object.keys(updates).length > 0) {
      await db.case.update({ where: { id: c.id }, data: updates });
    }
  }

  console.log(`\n✅ پایان مهاجرت:`);
  console.log(`   • fee تبدیل‌شده به تومان: ${feeUpdated}`);
  console.log(`   • systemCost تبدیل‌شده به تومان: ${costUpdated}`);
  if (skipped.length > 0) {
    console.log(`   • موارد مشکوک (احتمالاً از قبل تومان — بررسی دستی): ${skipped.length}`);
    skipped.slice(0, 20).forEach((s) => console.log(`       - ${s}`));
  }
  console.log('\n💡 در صورت خطا، بکاپ دیتابیس را بازیابی کنید و دوباره تلاش کنید.');
}

main()
  .catch((e) => {
    console.error('❌ خطا در مهاجرت:', e);
    process.exit(1);
  })
  .finally(() => db.$disconnect());
