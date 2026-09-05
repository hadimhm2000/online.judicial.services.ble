/**
 * fix-stale-rial-fees.js — اصلاح ایمن پرونده‌های قدیمی که fee آن‌ها به‌صورت
 * «ریال خام» ثبت شده (قبل از دیپلوی fee=court_total//10 / fee=final_fee//10).
 *
 * ⚠️ چرا این اسکریپت جدا از scripts/migrate_fees_to_toman.js؟
 *   آن اسکریپت صرفاً بر اساس «بزرگیِ عدد fee» تشخیص می‌دهد که ریال است یا
 *   تومان. اگر همین الان دیتابیس شما ترکیبی از پرونده‌های قدیمی (باگ‌دار)
 *   و پرونده‌های جدید (که با کد اصلاح‌شده و به‌درستی تومان ثبت شده‌اند)
 *   باشد، آن اسکریپت ممکن است یک fee صحیحِ ۲۰۰,۰۰۰ تومانی را دوباره
 *   تقسیم بر ۱۰ کند و به اشتباه ۲۰,۰۰۰ کند.
 *
 *   این نسخه علاوه بر بزرگیِ fee، از «تاریخ ایجاد پرونده» هم به‌عنوان
 *   فیلتر امنیتی استفاده می‌کند: فقط پرونده‌هایی را دست می‌زند که
 *   *قبل* از زمانی ساخته شده‌اند که کد اصلاح‌شده را روی VPS دیپلوی کردید.
 *
 * نحوه استفاده:
 *   1) دیپلوی/ری‌استارت ربات را با کد اصلاح‌شده انجام دهید و دقیقاً زمانش را یادداشت کنید.
 *   2) اول DRY-RUN (بدون --apply) بزنید تا فقط لیست پرونده‌های مشکوک را ببینید:
 *        node scripts/fix-stale-rial-fees.js --before="2026-09-05T18:00:00"
 *   3) اگر لیست درست بود، با --apply واقعاً اعمال کنید:
 *        node scripts/fix-stale-rial-fees.js --before="2026-09-05T18:00:00" --apply
 *   4) یا اگر می‌خواهید فقط پرونده‌های یک کاربر خاص اصلاح شوند — عددی که
 *      در پنل کنار نام کاربر «ID: ...» نشان داده می‌شود همان baleUserId
 *      است (نه id داخلی دیتابیس)، پس با همین می‌توانید فیلتر کنید:
 *        node scripts/fix-stale-rial-fees.js --baleUserId=2044375688 --serviceType=LAVAYEH --apply
 *
 *   5) یا اگر id داخلی دیتابیس (cuid) را از طریق API/دیتابیس پیدا کرده‌اید:
 *        node scripts/fix-stale-rial-fees.js --ids=clx123,clx456 --apply
 *
 * ⚠️ قبل از --apply حتماً از فایل دیتابیس (SQLite) یک کپی بگیرید.
 */
const { PrismaClient } = require('@prisma/client');
const db = new PrismaClient();

// سرویس‌هایی که fee آن‌ها از اول «تومان» بوده و هرگز نباید دست بخورند
const TOMAN_SERVICES = new Set([
  'INQUIRY',
  'REGIONAL_VALUE',
  'STAMP_CALC',
  'SUBSCRIPTION',
  'UNKNOWN',
  'NONE',
  '',
]);

// کمترین فاکتور واقعی لایحه/اظهارنامه و... ≈ ۴۰,۰۰۰ تومان ⇒ معادل ریالی آن ۴۰۰,۰۰۰
const RIAL_THRESHOLD = 100_000;

function parseArgs() {
  const args = Object.fromEntries(
    process.argv.slice(2).map((a) => {
      const [k, ...rest] = a.replace(/^--/, '').split('=');
      return [k, rest.join('=') || true];
    })
  );
  return {
    apply: !!args.apply,
    before: args.before ? new Date(args.before) : null,
    ids: args.ids ? String(args.ids).split(',').map((s) => s.trim()).filter(Boolean) : null,
    // ⭐ توجه: عددی که در پنل کنار نام کاربر به‌صورت "ID: ۲۰۴۴۳۷۵۶۸۸" نشان
    // داده می‌شود، شناسه‌ی داخلی دیتابیس (id) نیست — همان baleUserId است.
    // برای همین این فیلتر جدا اضافه شد.
    baleUserId: args.baleUserId ? String(args.baleUserId) : null,
    serviceType: args.serviceType ? String(args.serviceType) : null,
  };
}

function looksLikeOldRial(serviceType, fee) {
  if (!fee || fee <= 0) return false;
  if (TOMAN_SERVICES.has(serviceType)) return false;
  return fee >= RIAL_THRESHOLD;
}

async function main() {
  const { apply, before, ids, baleUserId, serviceType } = parseArgs();

  if (!ids && !before && !baleUserId) {
    console.error('❌ باید یکی از --ids=... یا --baleUserId=... یا --before="ISO-DATETIME" را بدهید.');
    console.error('   مثال: node scripts/fix-stale-rial-fees.js --baleUserId=2044375688 --serviceType=LAVAYEH');
    process.exit(1);
  }

  const where = {};
  if (ids) {
    where.id = { in: ids };
  } else if (baleUserId) {
    where.baleUserId = String(baleUserId);
    if (serviceType) where.serviceType = serviceType;
  } else {
    where.createdAt = { lt: before };
  }

  const cases = await db.case.findMany({
    where,
    select: {
      id: true,
      baleUserId: true,
      fullName: true,
      serviceType: true,
      trackingCode: true,
      status: true,
      feeStatus: true,
      fee: true,
      createdAt: true,
    },
    orderBy: { createdAt: 'desc' },
  });

  const candidates = cases.filter((c) => ids ? true : looksLikeOldRial(c.serviceType, c.fee));

  console.log(`🔍 حالت: ${apply ? 'APPLY (اعمال واقعی)' : 'DRY-RUN (فقط نمایش)'}`);
  console.log(`📋 پرونده‌های بررسی‌شده: ${cases.length} | مشکوک/هدف: ${candidates.length}\n`);

  if (candidates.length === 0) {
    console.log('چیزی برای اصلاح پیدا نشد.');
    return;
  }

  console.log('ردیف | serviceType | trackingCode | status/feeStatus | fee فعلی → fee جدید');
  console.log('-----------------------------------------------------------------------------');

  let updated = 0;
  for (const c of candidates) {
    const newFee = Math.floor(c.fee / 10);
    console.log(
      `${c.id} | ${c.serviceType} | ${c.trackingCode || '-'} | ${c.status}/${c.feeStatus} | ` +
      `${c.fee.toLocaleString('fa-IR')} → ${newFee.toLocaleString('fa-IR')} تومان`
    );
    if (apply) {
      await db.case.update({ where: { id: c.id }, data: { fee: newFee } });
      updated++;
    }
  }

  console.log('\n---');
  if (apply) {
    console.log(`✅ ${updated} پرونده اصلاح شد.`);
  } else {
    console.log('ℹ️ این فقط پیش‌نمایش بود. برای اعمال واقعی، فلگ --apply را اضافه کن.');
  }
}

main()
  .catch((e) => {
    console.error('❌ خطا:', e);
    process.exit(1);
  })
  .finally(() => db.$disconnect());
