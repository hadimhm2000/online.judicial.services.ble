'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Activity,
  RefreshCw,
  CheckCircle2,
  CircleDashed,
  Clock,
  Wrench,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ServiceStatus {
  key: string;
  label: string;
  kind: 'case' | 'message' | 'tool';
  status: 'active' | 'idle' | 'stale' | 'none' | 'tool';
  total: number;
  todayCount: number;
  lastSyncAt: string | null;
  note?: string;
}

interface HealthData {
  services: ServiceStatus[];
  summary: {
    totalSections: number;
    caseSections: number;
    withData: number;
    activeToday: number;
  };
  generatedAt: string;
}

const STATUS_META: Record<
  ServiceStatus['status'],
  { label: string; dot: string; text: string }
> = {
  active: { label: 'متصل — فعال', dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  idle: { label: 'متصل — کم‌کار', dot: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
  stale: { label: 'متصل — قدیمی', dot: 'bg-orange-500', text: 'text-orange-600 dark:text-orange-400' },
  none: { label: 'بدون داده', dot: 'bg-muted-foreground/40', text: 'text-muted-foreground' },
  tool: { label: 'ابزار — بدون پرونده', dot: 'bg-violet-400', text: 'text-violet-600 dark:text-violet-400' },
};

function formatNumber(n: number): string {
  return new Intl.NumberFormat('fa-IR').format(n);
}

function timeAgo(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'لحظاتی پیش';
  if (minutes < 60) return `${formatNumber(minutes)} دقیقه پیش`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${formatNumber(hours)} ساعت پیش`;
  const days = Math.floor(hours / 24);
  return `${formatNumber(days)} روز پیش`;
}

export function ConnectionHealthWidget() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const res = await fetch('/api/admin/connection-health', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: HealthData = await res.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در دریافت وضعیت اتصال');
    } finally {
      setLoading(false);
      if (isRefresh) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(() => fetchHealth(), 60_000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  return (
    <Card className="border-sky-200/60 dark:border-sky-800/40 shadow-sm">
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-sky-500/90 to-cyan-600/90 flex items-center justify-center shadow-sm">
              <Activity className="h-4 w-4 text-white" />
            </div>
            <div>
              <h3 className="text-sm font-bold">وضعیت اتصال بخش‌های ربات به پنل</h3>
              <p className="text-[11px] text-muted-foreground">
                {data
                  ? `${formatNumber(data.summary.withData)} بخش از ${formatNumber(data.summary.totalSections)} بخش داده ثبت‌شده دارند — ${formatNumber(data.summary.activeToday)} بخش در ۲۴ ساعت اخیر فعال بوده‌اند`
                  : 'آخرین سینک هر بخش ربات'}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 shrink-0"
            onClick={() => fetchHealth(true)}
            aria-label="به‌روزرسانی وضعیت اتصال"
            disabled={refreshing}
          >
            <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-xs text-red-600 dark:text-red-400 py-3 text-center">
            خطا در دریافت وضعیت اتصال: {error}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {data?.services.map((s) => {
              const meta = STATUS_META[s.status];
              const Icon = s.kind === 'tool' ? Wrench : s.status === 'active' ? CheckCircle2 : CircleDashed;
              return (
                <div
                  key={s.key}
                  className={cn(
                    'rounded-xl border p-2.5 transition-all hover:shadow-sm',
                    s.status === 'active'
                      ? 'border-emerald-200/70 dark:border-emerald-800/40 bg-emerald-50/50 dark:bg-emerald-950/20'
                      : 'border-border/60 bg-muted/30'
                  )}
                  title={s.note || undefined}
                >
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className={cn('h-2 w-2 rounded-full shrink-0', meta.dot)} />
                    <Icon className={cn('h-3 w-3 shrink-0', meta.text)} />
                    <span className="text-[11px] font-semibold truncate">{s.label}</span>
                  </div>
                  {s.kind === 'tool' ? (
                    <p className="text-[10px] text-muted-foreground leading-4" dir="rtl">
                      {s.note || 'ابزار بدون پرونده'}
                    </p>
                  ) : (
                    <>
                      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Clock className="h-2.5 w-2.5 shrink-0" />
                        <span>{timeAgo(s.lastSyncAt)}</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {formatNumber(s.total)} پرونده
                        {s.todayCount > 0 && (
                          <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                            {' '}({formatNumber(s.todayCount)} امروز)
                          </span>
                        )}
                      </div>
                      {s.note && (
                        <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5 leading-4" dir="rtl">
                          {s.note}
                        </p>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ConnectionHealthWidget;
