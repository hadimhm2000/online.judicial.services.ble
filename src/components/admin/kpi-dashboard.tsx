'use client';

import { useState, useEffect, useRef } from 'react';
import { Clock, Zap, CheckCircle, AlertTriangle, Users, ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface KpiData {
  avgProcessingTime: number;
  peakHour: number;
  peakHourCount: number;
  peakHourLabel: string;
  todayCompleted: number;
  todayFailed: number;
  successRateTrend: { trend: 'up' | 'down' | 'stable'; percentage: number };
  totalActiveUsers: number;
}

function AnimatedCounter({ target, duration = 1200, decimals = 0 }: { target: number; duration?: number; decimals?: number }) {
  const [value, setValue] = useState(target);
  const prevTarget = useRef(target);
  const raf = useRef<number>(0);
  const startValue = useRef(target);
  const startTime = useRef<number | null>(null);

  useEffect(() => {
    if (target === prevTarget.current) return;
    startValue.current = value;
    prevTarget.current = target;
    startTime.current = null;

    const animate = (timestamp: number) => {
      if (!startTime.current) startTime.current = timestamp;
      const progress = Math.min((timestamp - startTime.current) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = startValue.current + (target - startValue.current) * eased;
      setValue(next);
      if (progress < 1) {
        raf.current = requestAnimationFrame(animate);
      }
    };
    raf.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);

  const display = decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
  return <>{new Intl.NumberFormat('fa-IR').format(Number(display))}</>;
}

function SkeletonCard() {
  return (
    <div className="stat-card-v2 card-elevated rounded-2xl p-4 overflow-hidden relative">
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full animate-shimmer" />
      <div className="flex items-center gap-2 mb-3">
        <div className="h-8 w-8 rounded-lg bg-muted animate-pulse" />
        <div className="h-3 w-20 rounded bg-muted animate-pulse" />
      </div>
      <div className="h-7 w-16 rounded bg-muted animate-pulse" />
      <div className="h-3 w-24 rounded bg-muted animate-pulse mt-2" />
    </div>
  );
}

function TrendIcon({ trend }: { trend: 'up' | 'down' | 'stable' }) {
  if (trend === 'up') return <ArrowUp className="h-3 w-3 text-emerald-500" />;
  if (trend === 'down') return <ArrowDown className="h-3 w-3 text-rose-500" />;
  return <Minus className="h-3 w-3 text-muted-foreground" />;
}

interface KpiCardProps {
  label: string;
  numericValue?: number;
  textValue?: string;
  decimals?: number;
  unit?: string;
  subValue?: string;
  icon: React.ComponentType<{ className?: string }>;
  iconBg: string;
  iconColor: string;
  trend?: { trend: 'up' | 'down' | 'stable'; percentage: number };
  sonar?: boolean;
  idx: number;
  textGradient?: string;
}

function KpiCard({ label, numericValue, textValue, decimals, unit, subValue, icon: Icon, iconBg, iconColor, trend, sonar, idx, textGradient }: KpiCardProps) {
  return (
    <div
      className="stat-card-v2 hover-lift-md chart-card-shine card-elevated card-tilt rounded-2xl p-4 overflow-hidden relative animate-fade-in-up"
      style={{ animationDelay: `${idx * 80}ms` }}
    >
      <div className="flex items-center gap-2 mb-3">
        <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center', iconBg)}>
          <Icon className={cn('h-4 w-4', iconColor)} />
        </div>
        <span className="text-[11px] font-medium text-muted-foreground leading-tight">
          {label}
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={cn(
          'text-2xl font-bold tabular-nums nums-align',
          textValue && 'text-lg',
          textGradient,
        )}>
          {textValue ?? <AnimatedCounter target={numericValue ?? 0} decimals={decimals ?? 0} />}
        </span>
        {unit && (
          <span className="text-[10px] text-muted-foreground font-medium">{unit}</span>
        )}
      </div>
      {subValue && (
        <p className="text-[11px] text-muted-foreground mt-1">{subValue}</p>
      )}
      {trend && (
        <div className="flex items-center gap-1 mt-2">
          <TrendIcon trend={trend.trend} />
          <span className={cn(
            'text-[10px] font-medium',
            trend.trend === 'up' && 'text-emerald-600 dark:text-emerald-400',
            trend.trend === 'down' && 'text-rose-600 dark:text-rose-400',
            trend.trend === 'stable' && 'text-muted-foreground',
          )}>
            {trend.trend !== 'stable' && (
              <>{new Intl.NumberFormat('fa-IR').format(trend.percentage)}٪ {'نرخ موفقیت'}</>
            )}
            {trend.trend === 'stable' && 'بدون تغییر'}
          </span>
        </div>
      )}
      {sonar && (
        <div className="absolute top-3 left-3">
          <div className="relative h-3 w-3">
            <div className="absolute inset-0 rounded-full bg-rose-500 animate-sonar" />
            <div className="relative h-3 w-3 rounded-full bg-rose-500" />
          </div>
        </div>
      )}
    </div>
  );
}

export default function KpiDashboard() {
  const [kpi, setKpi] = useState<KpiData | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    const fetchKpi = async () => {
      try {
        const res = await fetch('/api/admin/kpi');
        if (res.ok && mounted.current) {
          setKpi(await res.json());
        }
      } catch {
      } finally {
        if (mounted.current) setLoading(false);
      }
    };
    fetchKpi();
    return () => { mounted.current = false; };
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (!kpi) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
      <KpiCard
        idx={0}
        label={'متوسط زمان پردازش'}
        numericValue={kpi.avgProcessingTime}
        decimals={1}
        unit={'ساعت'}
        icon={Clock}
        iconBg="bg-emerald-100 dark:bg-emerald-900/40"
        iconColor="text-emerald-600 dark:text-emerald-400"
        textGradient="text-gradient-emerald"
      />
      <KpiCard
        idx={1}
        label={'ساعت اول ثبت'}
        textValue={kpi.peakHourLabel}
        subValue={new Intl.NumberFormat('fa-IR').format(kpi.peakHourCount) + ' ' + 'پرونده'}
        icon={Zap}
        iconBg="bg-amber-100 dark:bg-amber-900/40"
        iconColor="text-amber-600 dark:text-amber-400"
        textGradient="text-gradient-amber"
      />
      <KpiCard
        idx={2}
        label={'تکمیل شده امروز'}
        numericValue={kpi.todayCompleted}
        icon={CheckCircle}
        iconBg="bg-sky-100 dark:bg-sky-900/40"
        iconColor="text-sky-600 dark:text-sky-400"
        textGradient="text-gradient-sky"
      />
      <KpiCard
        idx={3}
        label={'شکست خورده امروز'}
        numericValue={kpi.todayFailed}
        icon={AlertTriangle}
        iconBg="bg-rose-100 dark:bg-rose-900/40"
        iconColor="text-rose-600 dark:text-rose-400"
        sonar={kpi.todayFailed > 0}
        textGradient="text-gradient-rose"
      />
      <KpiCard
        idx={4}
        label={'کاربران فعال'}
        numericValue={kpi.totalActiveUsers}
        icon={Users}
        iconBg="bg-violet-100 dark:bg-violet-900/40"
        iconColor="text-violet-600 dark:text-violet-400"
        trend={kpi.successRateTrend}
        textGradient="text-gradient-violet"
      />
    </div>
  );
}
