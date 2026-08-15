'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTheme } from 'next-themes';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface HeatmapPoint { hour: number; day: number; count: number; }
interface HeatmapResp { data: HeatmapPoint[]; totals: { byHour: number[]; byDay: number[] }; }

const DAY_LABELS = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];
const PERSIAN_NUMS = ['۰','۱','۲','۳','۴','۵','۶','۷','۸','۹'];
const fa = (n: number) => String(n).split('').map(d => PERSIAN_NUMS[parseInt(d)] || d).join('');

const CHART_CARD = 'chart-card-shine border shadow-sm shadow-black/5 dark:shadow-black/20 hover:shadow-md dark:hover:shadow-black/30 transition-shadow duration-300 card-elevated';

function getCellColor(count: number, max: number, isDark: boolean): string {
  if (count === 0) return isDark ? 'oklch(0.25 0.01 160 / 0.4)' : 'oklch(0.97 0.005 160)';
  const ratio = Math.min(count / Math.max(max, 1), 1);
  const l = isDark ? 0.25 + ratio * 0.2 : 0.95 - ratio * 0.35;
  const c = 0.04 + ratio * 0.12;
  return `oklch(${l.toFixed(3)} ${c.toFixed(3)} 160)`;
}

export default function HeatmapChart() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const [resp, setResp] = useState<HeatmapResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState<{ hour: number; day: number; count: number; x: number; y: number } | null>(null);

  const fetchHeatmap = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/heatmap');
      if (res.ok) setResp(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchHeatmap(); }, [fetchHeatmap]);

  const grid = useCallback((h: number, d: number) => {
    return resp?.data.find(p => p.hour === h && p.day === d)?.count || 0;
  }, [resp?.data]);

  const maxCount = resp ? Math.max(...resp.data.map(p => p.count), 1) : 1;

  if (loading) {
    return (
      <Card className={CHART_CARD}>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm font-bold">نقشه حرارتی</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <div className="animate-shimmer h-48 rounded-lg bg-muted/40" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={CHART_CARD}>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm font-bold flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
            <svg className="h-3.5 w-3.5 text-emerald-600" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="4" height="4" rx="1" opacity="0.4" /><rect x="9" y="3" width="4" height="4" rx="1" opacity="0.7" /><rect x="15" y="3" width="4" height="4" rx="1" /><rect x="3" y="9" width="4" height="4" rx="1" /><rect x="9" y="9" width="4" height="4" rx="1" opacity="0.5" /><rect x="3" y="15" width="4" height="4" rx="1" opacity="0.8" /></svg>
          </div>
          نقشه حرارتی پرونده‌ها
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {resp && resp.data.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-muted-foreground gap-2">
            <svg className="h-8 w-8 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" /></svg>
            <p className="text-xs">داده‌ای برای نقشه وجود ندارد</p>
          </div>
        ) : (
          <div className="relative overflow-x-auto" onMouseLeave={() => setTooltip(null)}>
            <div className="min-w-[560px]" dir="ltr">
              {/* Hour labels */}
              <div className="flex gap-[3px] mb-1 pl-16">
                {Array.from({ length: 24 }, (_, h) => (
                  <div key={h} className="flex-1 text-center text-[8px] text-muted-foreground/60 tabular-nums">
                    {fa(h)}
                  </div>
                ))}
              </div>
              {/* Grid rows */}
              <div className="flex flex-col gap-[3px]">
                {DAY_LABELS.map((label, d) => (
                  <div key={d} className="flex items-center gap-[3px]">
                    <div className="w-14 text-right text-[10px] text-muted-foreground/70 shrink-0 pr-1" dir="rtl">
                      {label}
                    </div>
                    {Array.from({ length: 24 }, (_, h) => {
                      const count = grid(h, d);
                      return (
                        <div
                          key={`${d}-${h}`}
                          className="flex-1 aspect-square rounded-[3px] cursor-pointer transition-transform hover:scale-125"
                          style={{ backgroundColor: getCellColor(count, maxCount, isDark) }}
                          onMouseEnter={(e) => {
                            const rect = (e.target as HTMLElement).getBoundingClientRect();
                            setTooltip({ hour: h, day: d, count, x: rect.left + rect.width / 2, y: rect.top });
                          }}
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
              {/* Legend */}
              <div className="flex items-center justify-end gap-1.5 mt-2 pl-16" dir="rtl">
                <span className="text-[9px] text-muted-foreground/60">کم</span>
                {[0, 0.25, 0.5, 0.75, 1].map((r, i) => (
                  <div key={i} className="w-3 h-3 rounded-[2px]" style={{ backgroundColor: getCellColor(Math.round(r * maxCount), maxCount, isDark) }} />
                ))}
                <span className="text-[9px] text-muted-foreground/60">زیاد</span>
              </div>
            </div>
            {/* Tooltip */}
            {tooltip && (
              <div
                className="fixed z-50 px-2 py-1.5 rounded-lg bg-popover text-popover-foreground border shadow-lg text-[11px] pointer-events-none"
                style={{ left: tooltip.x, top: tooltip.y - 40, transform: 'translateX(-50%)' }}
                dir="rtl"
              >
                <span className="font-medium">{DAY_LABELS[tooltip.day]}</span>
                <span className="text-muted-foreground mx-1">ساعت</span>
                <span className="font-medium">{fa(tooltip.hour)}</span>
                <span className="text-muted-foreground mx-1">:</span>
                <span className="font-bold text-emerald-600 dark:text-emerald-400">{new Intl.NumberFormat('fa-IR').format(tooltip.count)}</span>
                <span className="text-muted-foreground mr-1">مورد</span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
