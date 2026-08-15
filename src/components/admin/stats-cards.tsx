'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

interface StatsCardsProps {
  stats: {
    total: number;
    completed: number;
    incomplete: number;
    unpaid: number;
    readyToSend: number;
    failed: number;
    todayCases: number;
    totalRevenue: number;
    unpaidRevenue: number;
    createdAt?: string;
  };
}

interface StatCard {
  title: string;
  value: number | string;
  subtitle?: string;
  icon: LucideIcon;
  gradient: string;
  iconBg: string;
  iconColor: string;
  ringColor: string;
  pulse?: boolean;
  glowBorder?: 'rose' | 'sky' | 'orange';
  isRate?: boolean;
  patternId?: string;
  textGradient?: string;
  ambientGlow?: string;
}

import {
  FileCheck2,
  FileWarning,
  CreditCard,
  Send,
  AlertTriangle,
  TrendingUp,
  CalendarCheck,
  Wallet,
  Target,
} from 'lucide-react';

function formatNumber(n: number): string {
  return new Intl.NumberFormat('fa-IR').format(n);
}

function formatToman(n: number): string {
  return `${formatNumber(n)} تومان`;
}

function AnimatedCounter({ value, duration = 800 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);
  const prevValue = useRef(0);

  useEffect(() => {
    const start = prevValue.current;
    const diff = value - start;
    if (diff === 0) return;
    const startTime = performance.now();

    function step(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
    prevValue.current = value;
  }, [value, duration]);

  return <span>{formatNumber(display)}</span>;
}

function ProgressRing({
  percentage,
  size = 52,
  strokeWidth = 4,
}: {
  percentage: number;
  size?: number;
  strokeWidth?: number;
}) {
  const [offset, setOffset] = useState(0);
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;

  useEffect(() => {
    const timer = setTimeout(() => {
      setOffset(circumference - (percentage / 100) * circumference);
    }, 100);
    return () => clearTimeout(timer);
  }, [percentage, circumference]);

  const color =
    percentage >= 70
      ? 'stroke-emerald-500'
      : percentage >= 40
        ? 'stroke-amber-500'
        : 'stroke-rose-500';

  const trackColor =
    percentage >= 70
      ? 'stroke-emerald-500/15'
      : percentage >= 40
        ? 'stroke-amber-500/15'
        : 'stroke-rose-500/15';

  return (
    <svg width={size} height={size} className="transform -rotate-90 progress-ring-smooth" aria-hidden="true">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        strokeWidth={strokeWidth}
        className={trackColor}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        className={cn(color, 'transition-all duration-[1200ms] ease-[cubic-bezier(0.4,0,0.2,1)]')}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        className="fill-foreground text-[10px] font-bold"
        style={{ transform: 'rotate(90deg)', transformOrigin: 'center' }}
      >
        {percentage}%
      </text>
    </svg>
  );
}

function DecorativePattern({ id }: { id: string }) {
  const patterns: Record<string, React.ReactNode> = {
    wave: (
      <svg
        className="absolute bottom-0 right-0 w-full h-12 opacity-[0.04] dark:opacity-[0.06] pointer-events-none"
        viewBox="0 0 200 40"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          d="M0,20 C30,8 60,32 100,20 C140,8 170,32 200,20 L200,40 L0,40 Z"
          fill="currentColor"
        />
      </svg>
    ),
    circles: (
      <svg
        className="absolute -bottom-3 -left-3 w-20 h-20 opacity-[0.04] dark:opacity-[0.07] pointer-events-none"
        viewBox="0 0 80 80"
        aria-hidden="true"
      >
        <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="40" cy="40" r="24" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="40" cy="40" r="12" fill="currentColor" opacity="0.5" />
      </svg>
    ),
    dots: (
      <svg
        className="absolute top-0 left-0 w-full h-full opacity-[0.03] dark:opacity-[0.05] pointer-events-none"
        viewBox="0 0 80 80"
        aria-hidden="true"
      >
        <pattern id={`dots-${id}`} x="0" y="0" width="16" height="16" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" fill="currentColor" />
        </pattern>
        <rect width="80" height="80" fill={`url(#dots-${id})`} />
      </svg>
    ),
    diagonal: (
      <svg
        className="absolute bottom-0 right-0 w-16 h-16 opacity-[0.04] dark:opacity-[0.06] pointer-events-none"
        viewBox="0 0 60 60"
        aria-hidden="true"
      >
        <line x1="0" y1="60" x2="60" y2="0" stroke="currentColor" strokeWidth="1.5" />
        <line x1="15" y1="60" x2="60" y2="15" stroke="currentColor" strokeWidth="1" />
      </svg>
    ),
    hexagon: (
      <svg
        className="absolute -top-2 -left-2 w-16 h-16 opacity-[0.04] dark:opacity-[0.06] pointer-events-none"
        viewBox="0 0 60 60"
        aria-hidden="true"
      >
        <polygon
          points="30,2 55,17 55,43 30,58 5,43 5,17"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </svg>
    ),
  };

  return <>{patterns[id] || patterns.circles}</>;
}

function getTimeAgoText(createdAt: string | undefined): string {
  if (!createdAt) return '';
  const diff = Date.now() - new Date(createdAt).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'لحظای پیش';
  if (minutes < 60) return `${formatNumber(minutes)} دقیقه پیش`;
  const hours = Math.floor(minutes / 60);
  return `${formatNumber(hours)} ساعت پیش`;
}

function TimeAgo({ createdAt }: { createdAt?: string }) {
  const [text, setText] = useState(() => getTimeAgoText(createdAt));

  useEffect(() => {
    if (!createdAt) return;
    const id = setInterval(() => setText(getTimeAgoText(createdAt)), 30000);
    return () => clearInterval(id);
  }, [createdAt]);

  if (!createdAt) return null;

  return (
    <p className="text-[11px] text-muted-foreground/60 text-center mt-3 mb-1 flex items-center justify-center gap-1.5">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="opacity-50" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
      <span>{'آخرین بروزرسانی: '}{text}</span>
    </p>
  );
}

const StatsCardsMemo = React.memo(function StatsCards({ stats }: StatsCardsProps) {
  const [shimmering, setShimmering] = useState(true);
  const prevStatsRef = useRef(stats);
  const hasAnimated = useRef(false);

  useEffect(() => {
    if (!hasAnimated.current && stats.total > 0) {
      hasAnimated.current = true;
      const timer = setTimeout(() => setShimmering(false), 1200);
      return () => clearTimeout(timer);
    }
    if (prevStatsRef.current !== stats && shimmering) {
      const timer = setTimeout(() => setShimmering(false), 800);
      prevStatsRef.current = stats;
      return () => clearTimeout(timer);
    }
    prevStatsRef.current = stats;
  }, [stats, shimmering]);

  const successRate =
    stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;

  const cards: StatCard[] = [
    {
      title: 'کل پرونده‌ها',
      value: stats.total,
      subtitle: `${formatNumber(stats.todayCases)} مورد امروز`,
      icon: TrendingUp,
      gradient: 'from-slate-50 to-slate-100 dark:from-slate-900/60 dark:to-slate-800/40',
      iconBg: 'bg-gradient-to-br from-slate-600/90 to-slate-700/90',
      iconColor: 'text-white',
      ringColor: 'ring-slate-200 dark:ring-slate-700',
      patternId: 'dots',
      textGradient: 'text-gradient-sky',
    },
    {
      title: 'نرخ موفقیت',
      value: `${successRate}%`,
      subtitle: successRate >= 70 ? 'عالی' : successRate >= 40 ? 'متوسط' : 'نیاز به بهبود',
      icon: Target,
      gradient:
        successRate >= 70
          ? 'from-emerald-50 to-green-50 dark:from-emerald-950/30 dark:to-green-950/20'
          : successRate >= 40
            ? 'from-amber-50 to-yellow-50 dark:from-amber-950/30 dark:to-yellow-950/20'
            : 'from-red-50 to-rose-50 dark:from-red-950/30 dark:to-rose-950/20',
      iconBg:
        successRate >= 70
          ? 'bg-gradient-to-br from-emerald-500/90 to-green-600/90'
          : successRate >= 40
            ? 'bg-gradient-to-br from-amber-500/90 to-yellow-500/90'
            : 'bg-gradient-to-br from-red-500/90 to-rose-500/90',
      iconColor: 'text-white',
      ringColor:
        successRate >= 70
          ? 'ring-emerald-200 dark:ring-emerald-800'
          : successRate >= 40
            ? 'ring-amber-200 dark:ring-amber-800'
            : 'ring-red-200 dark:ring-red-800',
      isRate: true,
      patternId: 'circles',
      textGradient: successRate >= 70 ? 'text-gradient-emerald' : successRate >= 40 ? 'text-gradient-amber' : 'text-gradient-rose',
    },
    {
      title: 'کامل ثبت شده',
      value: stats.completed,
      subtitle: `${formatNumber(stats.readyToSend)} در انتظار ارسال`,
      icon: FileCheck2,
      gradient: 'from-teal-50 to-emerald-50 dark:from-teal-950/30 dark:to-emerald-950/20',
      iconBg: 'bg-gradient-to-br from-teal-500/90 to-emerald-600/90',
      iconColor: 'text-white',
      ringColor: 'ring-teal-200 dark:ring-teal-800',
      patternId: 'wave',
      textGradient: 'text-gradient-emerald',
      ambientGlow: 'glow-emerald-ambient',
    },
    {
      title: 'ناقص',
      value: stats.incomplete,
      subtitle: 'نیاز به تکمیل اطلاعات',
      icon: FileWarning,
      gradient: 'from-amber-50 to-yellow-50 dark:from-amber-950/30 dark:to-yellow-950/20',
      iconBg: 'bg-gradient-to-br from-amber-500/90 to-yellow-500/90',
      iconColor: 'text-white',
      ringColor: 'ring-amber-200 dark:ring-amber-800',
      pulse: stats.incomplete > 5,
      patternId: 'diagonal',
      textGradient: 'text-gradient-amber',
    },
    {
      title: 'پرداخت نشده',
      value: stats.unpaid,
      subtitle: formatToman(stats.unpaidRevenue),
      icon: CreditCard,
      gradient: 'from-rose-50 to-pink-50 dark:from-rose-950/30 dark:to-pink-950/20',
      iconBg: 'bg-gradient-to-br from-rose-500/90 to-pink-600/90',
      iconColor: 'text-white',
      ringColor: 'ring-rose-200 dark:ring-rose-800',
      pulse: stats.unpaid > 10,
      glowBorder: stats.unpaid > 0 ? 'rose' : undefined,
      patternId: 'hexagon',
      textGradient: 'text-gradient-rose',
    },
    {
      title: 'آماده ارسال',
      value: stats.readyToSend,
      subtitle: 'در انتظار تأیید نهایی',
      icon: Send,
      gradient: 'from-sky-50 to-cyan-50 dark:from-sky-950/30 dark:to-cyan-950/20',
      iconBg: 'bg-gradient-to-br from-sky-500/90 to-cyan-600/90',
      iconColor: 'text-white',
      ringColor: 'ring-sky-200 dark:ring-sky-800',
      pulse: stats.readyToSend > 0,
      glowBorder: stats.readyToSend > 0 ? 'sky' : undefined,
      patternId: 'wave',
      textGradient: 'text-gradient-sky',
    },
    {
      title: 'شکست خورده',
      value: stats.failed,
      subtitle: 'نیاز به مداخله ادمین',
      icon: AlertTriangle,
      gradient: 'from-orange-50 to-red-50 dark:from-orange-950/30 dark:to-red-950/20',
      iconBg: 'bg-gradient-to-br from-orange-500/90 to-red-600/90',
      iconColor: 'text-white',
      ringColor: 'ring-orange-200 dark:ring-orange-800',
      pulse: stats.failed > 3,
      glowBorder: stats.failed > 0 ? 'orange' : undefined,
      patternId: 'diagonal',
      textGradient: 'text-gradient-amber',
    },
    {
      title: 'درآمد کل',
      value: formatToman(stats.totalRevenue),
      subtitle: 'پرداخت شده',
      icon: Wallet,
      gradient: 'from-teal-50 to-emerald-50 dark:from-teal-950/30 dark:to-emerald-950/20',
      iconBg: 'bg-gradient-to-br from-teal-600/90 to-emerald-700/90',
      iconColor: 'text-white',
      ringColor: 'ring-teal-200 dark:ring-teal-800',
      patternId: 'circles',
      textGradient: 'text-gradient-emerald',
    },
    {
      title: 'امروز',
      value: stats.todayCases,
      subtitle: 'پرونده جدید',
      icon: CalendarCheck,
      gradient: 'from-violet-50 to-purple-50 dark:from-violet-950/30 dark:to-purple-950/20',
      iconBg: 'bg-gradient-to-br from-violet-500/90 to-purple-600/90',
      iconColor: 'text-white',
      ringColor: 'ring-violet-200 dark:ring-violet-800',
      patternId: 'dots',
      textGradient: 'text-gradient-violet',
    },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
        {cards.map((card) => (
          <Card
            key={card.title}
            className={cn(
              'stat-card-v2 hover-lift-md card-tilt group relative overflow-hidden border transition-all duration-300',
              'hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/5 dark:hover:shadow-black/20',
              'ring-1',
              card.ringColor,
              'bg-gradient-to-br',
              card.gradient,
              card.glowBorder && `card-glow-${card.glowBorder}`,
              card.ambientGlow,
            )}
          >
            {/* Shimmer loading overlay */}
            {shimmering && (
              <div
                className={cn(
                  'absolute inset-0 z-20 animate-shimmer pointer-events-none',
                  'transition-opacity duration-500',
                )}
              />
            )}

            {/* Decorative SVG pattern in background */}
            <DecorativePattern id={card.title} />

            {/* Large subtle background glow orb */}
            <div
              className={cn(
                'absolute -bottom-4 -left-4 h-20 w-20 rounded-full',
                'bg-gradient-to-br from-white/20 to-transparent',
                'dark:from-white/5 blur-xl',
                'group-hover:scale-150 transition-transform duration-500',
              )}
            />

            <CardContent className="p-3.5 sm:p-4 relative z-10 glass-v2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="text-[11px] sm:text-xs font-medium text-muted-foreground truncate">
                      {card.title}
                    </p>
                    {card.pulse && (
                      <span className="relative flex h-2 w-2 shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
                      </span>
                    )}
                  </div>
                  <p className={cn('text-xl sm:text-2xl font-extrabold mt-1.5 tabular-nums tracking-tight', card.textGradient)}>
                    {typeof card.value === 'number' ? (
                      <AnimatedCounter value={card.value} />
                    ) : card.isRate ? (
                      card.value
                    ) : (
                      card.value
                    )}
                  </p>
                  {card.subtitle && (
                    <p className="text-[10px] sm:text-xs text-muted-foreground/80 mt-1 truncate">
                      {card.subtitle}
                    </p>
                  )}
                </div>

                <div className="flex flex-col items-center gap-1.5">
                  {/* Glassmorphism icon container with dramatic hover glow */}
                  {card.isRate ? (
                    <div className="relative">
                      <div
                        className={cn(
                          'p-2 rounded-xl transition-all duration-300',
                          'backdrop-blur-md bg-white/30 dark:bg-white/10',
                          'border border-white/40 dark:border-white/15',
                          'shadow-lg shadow-black/10 dark:shadow-black/30',
                          'group-hover:scale-115 group-hover:shadow-xl group-hover:shadow-black/20',
                          'group-hover:-rotate-6',
                          'animate-shine-sweep',
                        )}
                      >
                        <card.icon
                          className={cn('h-4 w-4 sm:h-5 sm:w-5', card.iconColor)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div
                      className={cn(
                        'p-2.5 rounded-xl transition-all duration-300',
                        'backdrop-blur-md',
                        card.iconBg,
                        'border border-white/25 dark:border-white/10',
                        'shadow-lg shadow-black/10 dark:shadow-black/30',
                        'group-hover:scale-115 group-hover:-rotate-3',
                        'group-hover:shadow-[0_0_20px_rgba(255,255,255,0.15),0_8px_24px_rgba(0,0,0,0.15)]',
                        'dark:group-hover:shadow-[0_0_24px_rgba(255,255,255,0.08),0_8px_24px_rgba(0,0,0,0.4)]',
                        'animate-shine-sweep',
                      )}
                    >
                      <card.icon
                        className={cn('h-4 w-4 sm:h-5 sm:w-5', card.iconColor)}
                      />
                    </div>
                  )}

                  {/* Progress ring for success rate card */}
                  {card.isRate && (
                    <ProgressRing percentage={successRate} size={44} strokeWidth={3.5} />
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Last updated timestamp */}
      <TimeAgo createdAt={stats.createdAt} />
    </div>
  );
});
StatsCardsMemo.displayName = 'StatsCards';

export default StatsCardsMemo;
