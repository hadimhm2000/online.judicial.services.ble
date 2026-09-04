'use client';

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { PieChart as PieChartIcon, BarChart3, TrendingUp, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useTheme } from 'next-themes';

interface PieData {
  name: string;
  value: number;
  color: string;
}

const PIE_COLORS = [
  '#059669', '#d97706', '#dc2626', '#0284c7', '#7c3aed', '#ea580c', '#db2777', '#65a30d',
];

interface ServiceChartProps {
  data: { _count: { id: number }; serviceType: string }[];
}

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
  ADMIN_SEND: 'ارسال پیام مدیریت',
};

const CHART_CARD = 'chart-card-shine border shadow-sm shadow-black/5 dark:shadow-black/20 hover:shadow-md dark:hover:shadow-black/30 transition-shadow duration-300 card-elevated';

export function ServicePieChart({ data }: ServiceChartProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const pieData: PieData[] = data.map((d, i) => ({
    name: SERVICE_LABELS[d.serviceType] || d.serviceType,
    value: d._count.id,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }));

  const total = pieData.reduce((s, d) => s + d.value, 0);

  return (
    <Card className={CHART_CARD}>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm font-bold flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
            <PieChartIcon className="h-3.5 w-3.5 text-purple-600" />
          </div>
توزیع خدمات
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div className="flex items-center gap-4">
          <div className="w-32 h-32 sm:w-40 sm:h-40 relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={35}
                  outerRadius={60}
                  paddingAngle={3}
                  dataKey="value"
                  strokeWidth={0}
                >
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    fontFamily: 'Vazirmatn, sans-serif',
                    fontSize: 12,
                    direction: 'rtl',
                    backgroundColor: isDark ? '#1f2937' : '#ffffff',
                    border: isDark ? '1px solid #374151' : '1px solid #e5e7eb',
                    borderRadius: '8px',
                    color: isDark ? '#f3f4f6' : '#111827',
                  }}
                  formatter={(v: number) => [
                    `${new Intl.NumberFormat('fa-IR').format(v)} مورد`,
                    '',
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <span className="text-xs font-bold text-muted-foreground">
                {new Intl.NumberFormat('fa-IR').format(total)}
              </span>
            </div>
          </div>
          <div className="flex-1 space-y-2.5">
            {pieData.map((d) => {
              const pct = total > 0 ? Math.round((d.value / total) * 100) : 0;
              return (
                <div key={d.name} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
                      <span className="text-muted-foreground">{d.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold tabular-nums">
                        {new Intl.NumberFormat('fa-IR').format(d.value)}
                      </span>
                      <span className="text-[10px] text-muted-foreground/60 w-8 text-left">{pct}%</span>
                    </div>
                  </div>
                  <div className="h-1 bg-muted rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, backgroundColor: d.color }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface StatusOverviewProps {
  stats: {
    completed: number;
    incomplete: number;
    unpaid: number;
    failed: number;
    cancelled: number;
  };
}

export function StatusOverviewChart({ stats }: StatusOverviewProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const barData = [
    { name: 'تکمیل', value: stats.completed, fill: '#059669' },
    { name: 'ناقص', value: stats.incomplete, fill: '#d97706' },
    { name: 'پرداخت نشده', value: stats.unpaid, fill: '#dc2626' },
    { name: 'شکست خورده', value: stats.failed, fill: '#ea580c' },
    { name: 'لغو', value: stats.cancelled, fill: '#7c3aed' },
  ];

  return (
    <Card className={CHART_CARD}>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm font-bold flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
            <BarChart3 className="h-3.5 w-3.5 text-amber-600" />
          </div>
نمای کلی وضعیت‌ها
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} layout="vertical" margin={{ right: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={isDark ? '#374151' : '#e5e7eb'} />
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 11, fontFamily: 'Vazirmatn', fill: isDark ? '#9ca3af' : '#6b7280' }}
                width={85}
              />
              <Tooltip
                contentStyle={{
                  fontFamily: 'Vazirmatn, sans-serif',
                  fontSize: 12,
                  direction: 'rtl',
                  backgroundColor: isDark ? '#1f2937' : '#ffffff',
                  border: isDark ? '1px solid #374151' : '1px solid #e5e7eb',
                  borderRadius: '8px',
                  color: isDark ? '#f3f4f6' : '#111827',
                }}
                formatter={(v: number) => [
                  `${new Intl.NumberFormat('fa-IR').format(v)} مورد`,
                  '',
                ]}
              />
              <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={24}>
                {barData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

interface RevenueChartProps {
  stats: {
    totalRevenue: number;
    unpaidRevenue: number;
  };
}

export function RevenueChart({ stats }: RevenueChartProps) {
  const paid = stats.totalRevenue - stats.unpaidRevenue;
  const maxVal = Math.max(paid, stats.unpaidRevenue);
  const paidPct = maxVal > 0 ? Math.round((paid / maxVal) * 100) : 0;
  const unpaidPct = maxVal > 0 ? Math.round((stats.unpaidRevenue / maxVal) * 100) : 0;

  return (
    <Card className={CHART_CARD}>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm font-bold flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
          </div>
وضعیت درآمد
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div className="space-y-5">
          <div className="flex items-center gap-4">
            <div className="flex-1 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowUpRight className="h-3.5 w-3.5 text-emerald-500" />
                  <p className="text-[11px] text-muted-foreground">وصول شده</p>
                </div>
                <span className="text-[10px] text-emerald-600 font-bold">{paidPct}%</span>
              </div>
              <p className="text-lg font-extrabold text-emerald-600 tabular-nums">
                {new Intl.NumberFormat('fa-IR').format(paid)} <span className="text-xs font-normal text-muted-foreground">تومان</span>
              </p>
              <div className="h-2.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-l from-emerald-500 to-teal-400 rounded-full transition-all duration-1000"
                  style={{ width: `${paidPct}%` }}
                />
              </div>
            </div>
            <div className="w-px h-16 bg-border" />
            <div className="flex-1 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowDownRight className="h-3.5 w-3.5 text-red-500" />
                  <p className="text-[11px] text-muted-foreground">پرداخت نشده</p>
                </div>
                <span className="text-[10px] text-red-600 font-bold">{unpaidPct}%</span>
              </div>
              <p className="text-lg font-extrabold text-red-600 tabular-nums">
                {new Intl.NumberFormat('fa-IR').format(stats.unpaidRevenue)} <span className="text-xs font-normal text-muted-foreground">تومان</span>
              </p>
              <div className="h-2.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-l from-red-500 to-rose-400 rounded-full transition-all duration-1000"
                  style={{ width: `${unpaidPct}%` }}
                />
              </div>
            </div>
          </div>
          <div className="bg-muted/40 rounded-lg p-3 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">مجموع درآمد</span>
            <span className="text-sm font-extrabold tabular-nums">
              {new Intl.NumberFormat('fa-IR').format(stats.totalRevenue)} <span className="text-[10px] font-normal text-muted-foreground">تومان</span>
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
