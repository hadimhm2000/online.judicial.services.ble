'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { LineChart as LineChartIcon } from 'lucide-react';
import { useTheme } from 'next-themes';

export interface TrendDataPoint {
  label: string;
  total: number;
  completed: number;
  failed: number;
  revenue: number;
}

interface TrendResponse {
  period: string;
  data: TrendDataPoint[];
}

type Period = 'daily' | 'weekly' | 'monthly';

const PERIOD_OPTIONS: { key: Period; label: string }[] = [
  { key: 'daily', label: 'روزانه' },
  { key: 'weekly', label: 'هفتگی' },
  { key: 'monthly', label: 'ماهانه' },
];

const CHART_CARD = 'chart-card-shine border shadow-sm shadow-black/5 dark:shadow-black/20 hover:shadow-md dark:hover:shadow-black/30 transition-shadow duration-300 card-elevated';

export default function TrendLineChart() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const [period, setPeriod] = useState<Period>('daily');
  const [data, setData] = useState<TrendDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRevenue, setShowRevenue] = useState(false);

  const fetchTrends = useCallback(async (p: Period) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/trends?period=${p}`);
      if (res.ok) {
        const json: TrendResponse = await res.json();
        setData(json.data);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrends(period);
  }, [period, fetchTrends]);

  const maxTotal = data.length > 0 ? Math.max(...data.map((d) => d.total)) : 10;
  const yMax = Math.ceil(maxTotal * 1.15) || 10;

  const tooltipStyle = {
    fontFamily: 'Vazirmatn, sans-serif',
    fontSize: 12,
    direction: 'rtl' as const,
    backgroundColor: isDark ? '#1f2937' : '#ffffff',
    border: isDark ? '1px solid #374151' : '1px solid #e5e7eb',
    borderRadius: '8px',
    color: isDark ? '#f3f4f6' : '#111827',
  };

  return (
    <Card className={CHART_CARD}>
      <CardHeader className="p-4 pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-bold flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center">
              <LineChartIcon className="h-3.5 w-3.5 text-sky-600" />
            </div>
            روند پرونده‌ها
          </CardTitle>
          <div className="flex items-center gap-1">
            {PERIOD_OPTIONS.map((opt) => (
              <Button
                key={opt.key}
                variant={period === opt.key ? 'default' : 'ghost'}
                size="sm"
                className="h-7 text-[10px] px-2"
                onClick={() => setPeriod(opt.key)}
              >
                {opt.label}
              </Button>
            ))}
            <div className="w-px h-4 bg-border mx-1" />
            <Button
              variant={showRevenue ? 'default' : 'ghost'}
              size="sm"
              className="h-7 text-[10px] px-2"
              onClick={() => setShowRevenue(!showRevenue)}
            >
              درآمد
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {loading ? (
          <div className="h-52 flex items-center justify-center">
            <div className="animate-shimmer h-full w-full rounded-lg bg-muted/40" />
          </div>
        ) : data.length === 0 ? (
          <div className="h-52 flex flex-col items-center justify-center text-muted-foreground gap-2">
            <LineChartIcon className="h-8 w-8 opacity-30" />
            <p className="text-xs">داده‌ای برای نمودار وجود ندارد</p>
          </div>
        ) : (
          <div className="h-52" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
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
                  interval={data.length > 15 ? Math.ceil(data.length / 10) : 0}
                />
                <YAxis
                  domain={[0, yMax]}
                  tick={{ fontSize: 10, fontFamily: 'Vazirmatn', fill: isDark ? '#9ca3af' : '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                  width={30}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number, name: string) => {
                    const labels: Record<string, string> = {
                      total: `کل پرونده‌ها`,
                      completed: `تکمیل شده`,
                      failed: `شکست خورده`,
                      revenue: `درآمد (تومان)`,
                    };
                    return [
                      `${new Intl.NumberFormat('fa-IR').format(value)} ${name === 'revenue' ? 'تومان' : 'مورد'}`,
                      labels[name] || name,
                    ];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={20}
                  iconType="circle"
                  iconSize={6}
                  wrapperStyle={{
                    fontSize: 11,
                    fontFamily: 'Vazirmatn, sans-serif',
                    direction: 'rtl',
                    paddingBottom: 4,
                  }}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      total: `کل`,
                      completed: `تکمیل`,
                      failed: `شکست`,
                      revenue: `درآمد`,
                    };
                    return labels[value] || value;
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="total"
                  name="total"
                  stroke={isDark ? '#60a5fa' : '#0284c7'}
                  strokeWidth={2}
                  dot={data.length <= 20}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
                <Line
                  type="monotone"
                  dataKey="completed"
                  name="completed"
                  stroke={isDark ? '#34d399' : '#059669'}
                  strokeWidth={2}
                  dot={data.length <= 20}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
                <Line
                  type="monotone"
                  dataKey="failed"
                  name="failed"
                  stroke={isDark ? '#f87171' : '#dc2626'}
                  strokeWidth={2}
                  dot={data.length <= 20}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
                {showRevenue && (
                  <Line
                    type="monotone"
                    dataKey="revenue"
                    name="revenue"
                    stroke={isDark ? '#a78bfa' : '#7c3aed'}
                    strokeWidth={2}
                    strokeDasharray="6 3"
                    dot={false}
                    yAxisId={0}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
