'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart3 } from 'lucide-react';
import { useTheme } from 'next-themes';

interface ServiceMetric {
  serviceType: string;
  count: number;
  completedCount: number;
  failedCount: number;
  avgProcessingTime: number;
  totalRevenue: number;
  successRate: number;
}

interface PerfResponse {
  services: ServiceMetric[];
}

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
  ADMIN_SEND: 'ارسال پیام مدیریت',
};

const BAR_COLORS: Record<string, { light: string; dark: string }> = {
  INQUIRY: { light: '#0ea5e9', dark: '#38bdf8' },
  LAVAYEH: { light: '#10b981', dark: '#34d399' },
  EZHHARNAMEH: { light: '#f59e0b', dark: '#fbbf24' },
  EALAM_VAKALAHT: { light: '#8b5cf6', dark: '#a78bfa' },
  STAMP_CALC: { light: '#f43f5e', dark: '#fb7185' },
};

const CHART_CARD = 'chart-card-shine border shadow-sm shadow-black/5 dark:shadow-black/20 hover:shadow-md dark:hover:shadow-black/30 transition-shadow duration-300 card-elevated';

export default function ServicePerfChart() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const [data, setData] = useState<ServiceMetric[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/service-perf');
      if (res.ok) {
        const json: PerfResponse = await res.json();
        setData(json.services);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const tooltipStyle = {
    fontFamily: 'Vazirmatn, sans-serif',
    fontSize: 12,
    direction: 'rtl' as const,
    backgroundColor: isDark ? '#1f2937' : '#ffffff',
    border: isDark ? '1px solid #374151' : '1px solid #e5e7eb',
    borderRadius: '8px',
    color: isDark ? '#f3f4f6' : '#111827',
  };

  const chartData = data.map((s) => ({
    ...s,
    label: SERVICE_LABELS[s.serviceType] || s.serviceType,
  }));

  return (
    <Card className={CHART_CARD}>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm font-bold flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center">
            <BarChart3 className="h-3.5 w-3.5 text-violet-600" />
          </div>
          {'عملکرد خدمات'}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="animate-shimmer h-full w-full rounded-lg bg-muted/40" />
          </div>
        ) : data.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-muted-foreground gap-2">
            <BarChart3 className="h-8 w-8 opacity-30" />
            <p className="text-xs">{'داده‌ای برای نمودار وجود ندارد'}</p>
          </div>
        ) : (
          <div className="h-64" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={isDark ? '#374151' : '#e5e7eb'}
                  vertical={false}
                />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fontFamily: 'Vazirmatn', fill: isDark ? '#9ca3af' : '#6b7280' }}
                  axisLine={{ stroke: isDark ? '#374151' : '#e5e7eb' }}
                  tickLine={false}
                  interval={0}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fontFamily: 'Vazirmatn', fill: isDark ? '#9ca3af' : '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                  width={35}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  cursor={{ fill: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' }}
                  formatter={(_value: number, _name: string, props: { payload: ServiceMetric }) => {
                    const p = props.payload;
                    return [
                      [
                        `${new Intl.NumberFormat('fa-IR').format(p.successRate)}%`,
                        `  ${'نرخ موفقیت'}`,
                      ],
                      [
                        `${new Intl.NumberFormat('fa-IR').format(p.count)}`,
                        `  ${'کل پرونده‌ها'}`,
                      ],
                      [
                        `${new Intl.NumberFormat('fa-IR').format(p.completedCount)}`,
                        `  ${'تکمیل شده'}`,
                      ],
                      [
                        `${new Intl.NumberFormat('fa-IR').format(p.failedCount)}`,
                        `  ${'شکست خورده'}`,
                      ],
                      [
                        `${new Intl.NumberFormat('fa-IR').format(p.avgProcessingTime)} ${'ساعت'}`,
                        `  ${'میانگین زمان'}`,
                      ],
                      [
                        `${new Intl.NumberFormat('fa-IR').format(p.totalRevenue)} ${'تومان'}`,
                        `  ${'درآمد'}`,
                      ],
                    ];
                  }}
                  labelFormatter={(_label: string, payload: { payload: ServiceMetric }[]) => {
                    const item = payload?.[0]?.payload;
                    return SERVICE_LABELS[item?.serviceType || ''] || '';
                  }}
                />
                <Bar dataKey="successRate" radius={[6, 6, 0, 0]} maxBarSize={48}>
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.serviceType}
                      fill={BAR_COLORS[entry.serviceType]
                        ? (isDark ? BAR_COLORS[entry.serviceType].dark : BAR_COLORS[entry.serviceType].light)
                        : (isDark ? '#6b7280' : '#9ca3af')
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
