'use client';

import React, { useState, useEffect } from 'react';
import { useTheme } from 'next-themes';
import { GitBranch, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

interface PipelineStatus {
  count: number;
  breakdown: Record<string, number>;
}

interface PipelineData {
  statuses: Record<string, PipelineStatus>;
  transitions: { from: string; to: string; count: number }[];
  total: number;
}

const STATUS_CONFIG: { key: string; color: string; bg: string; border: string; darkBg: string; label: string }[] = [
  { key: 'PENDING_PAYMENT', color: 'text-rose-600 dark:text-rose-400', bg: 'bg-rose-50', border: 'border-rose-200 dark:border-rose-800', darkBg: 'dark:bg-rose-950/30', label: 'پرداخت نشده' },
  { key: 'PROCESSING', color: 'text-violet-600 dark:text-violet-400', bg: 'bg-violet-50', border: 'border-violet-200 dark:border-violet-800', darkBg: 'dark:bg-violet-950/30', label: 'در حال پردازش' },
  { key: 'INCOMPLETE', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50', border: 'border-amber-200 dark:border-amber-800', darkBg: 'dark:bg-amber-950/30', label: 'ناقص' },
  { key: 'COMPLETED', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50', border: 'border-emerald-200 dark:border-emerald-800', darkBg: 'dark:bg-emerald-950/30', label: 'تکمیل شده' },
  { key: 'FAILED', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50', border: 'border-red-200 dark:border-red-800', darkBg: 'dark:bg-red-950/30', label: 'شکست خورده' },
  { key: 'CANCELLED', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-50', border: 'border-gray-200 dark:border-gray-700', darkBg: 'dark:bg-gray-800/30', label: 'لغو شده' },
  { key: 'READY_TO_SEND', color: 'text-sky-600 dark:text-sky-400', bg: 'bg-sky-50', border: 'border-sky-200 dark:border-sky-800', darkBg: 'dark:bg-sky-950/30', label: 'آماده ارسال' },
];

const STEP_LABELS: Record<string, string> = {
  PAYMENT: 'پرداخت',
  DOCUMENT: 'سند',
  PROCESSING: 'پردازش',
  RESULT: 'نتیجه',
  READY: 'آماده',
  SENT: 'ارسال شده',
  NONE: 'شروع نشده',
  null: 'شروع نشده',
};

function PipelineSkeleton() {
  return (
    <Card className="card-elevated overflow-hidden">
      <CardHeader className="pb-3">
        <div className="animate-shimmer h-5 w-44 rounded" />
        <div className="animate-shimmer h-3.5 w-56 rounded mt-1.5" />
      </CardHeader>
      <CardContent>
        <div className="flex gap-3 overflow-hidden">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="flex-shrink-0 space-y-2">
              <div className="animate-shimmer h-24 w-32 rounded-xl" />
              <div className="animate-shimmer h-3 w-16 rounded mx-auto" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function PipelineWidget() {
  const { resolvedTheme } = useTheme();
  const [data, setData] = useState<PipelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  useEffect(() => {
    const fetchPipeline = async () => {
      try {
        const res = await fetch('/api/admin/pipeline');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setData(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : 'خطا در بارگیری');
      } finally {
        setLoading(false);
      }
    };
    fetchPipeline();
  }, []);

  if (loading) return <PipelineSkeleton />;
  if (error || !data) {
    return (
      <Card className="card-elevated">
        <CardContent className="py-8 text-center text-muted-foreground text-sm">{error || 'داده‌ای یافت نشد'}</CardContent>
      </Card>
    );
  }

  const total = data.total || 1;

  return (
    <TooltipProvider delayDuration={200}>
      <Card className="card-elevated overflow-hidden chart-card-shine animate-fade-in-up">
        <CardHeader className="pb-3 px-4 sm:px-6 pt-4 sm:pt-6">
          <CardTitle className="flex items-center gap-2 text-sm sm:text-base font-bold">
            <GitBranch className="h-4 w-4 text-emerald-500" />
            <span className="text-gradient-emerald">خط لوله وضعیت پرونده‌ها</span>
          </CardTitle>
          <p className="text-[11px] sm:text-xs text-muted-foreground mt-0.5">
            جریان پرونده‌ها در مراحل مختلف وضعیت
          </p>
        </CardHeader>
        <CardContent className="px-3 sm:px-6 pb-4 sm:pb-6">
          <div className="overflow-x-auto scrollbar-thin pb-2 -mx-1 px-1">
            <div className="flex items-stretch gap-2 sm:gap-3 min-w-max">
              {STATUS_CONFIG.map((cfg, idx) => {
                const statusData = data.statuses[cfg.key];
                const count = statusData?.count || 0;
                const pct = total > 0 ? ((count / total) * 100) : 0;
                const isHovered = hoveredIdx === idx;
                const barWidth = total > 0 ? Math.max(pct, 4) : 4;

                return (
                  <React.Fragment key={cfg.key}>
                    {idx > 0 && (
                      <div className="flex items-center shrink-0 self-center mt-[-24px]">
                        <div className="relative w-6 sm:w-10 h-[2px]">
                          <div className="absolute inset-0 bg-gradient-to-r from-gray-300 to-gray-300 dark:from-gray-700 dark:to-gray-700 rounded-full" />
                          <ArrowRight className="absolute -right-1.5 -top-[5px] h-3 w-3 text-gray-400 dark:text-gray-600" />
                        </div>
                      </div>
                    )}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div
                          className={cn(
                            'flex flex-col items-center gap-2 min-w-[100px] sm:min-w-[120px] p-3 sm:p-4 rounded-xl border transition-all duration-300 cursor-default',
                            'hover-lift-sm card-tilt',
                            cfg.bg, cfg.darkBg, cfg.border,
                            isHovered && 'ring-2 ring-offset-2 ring-offset-background',
                            isHovered && cfg.key === 'COMPLETED' && 'ring-emerald-400',
                            isHovered && cfg.key === 'FAILED' && 'ring-red-400',
                            isHovered && cfg.key === 'INCOMPLETE' && 'ring-amber-400',
                            isHovered && cfg.key === 'PENDING_PAYMENT' && 'ring-rose-400',
                            isHovered && cfg.key === 'READY_TO_SEND' && 'ring-sky-400',
                            isHovered && cfg.key === 'PROCESSING' && 'ring-violet-400',
                            isHovered && cfg.key === 'CANCELLED' && 'ring-gray-400',
                          )}
                          onMouseEnter={() => setHoveredIdx(idx)}
                          onMouseLeave={() => setHoveredIdx(null)}
                        >
                          <div className="w-full flex items-center justify-center h-8">
                            <div
                              className={cn(
                                'h-2 rounded-full transition-all duration-500',
                                cfg.key === 'COMPLETED' && 'bg-emerald-500',
                                cfg.key === 'FAILED' && 'bg-red-500',
                                cfg.key === 'INCOMPLETE' && 'bg-amber-500',
                                cfg.key === 'PENDING_PAYMENT' && 'bg-rose-500',
                                cfg.key === 'READY_TO_SEND' && 'bg-sky-500',
                                cfg.key === 'PROCESSING' && 'bg-violet-500',
                                cfg.key === 'CANCELLED' && 'bg-gray-500',
                              )}
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                          <div className="text-center">
                            <div className={cn('text-2xl sm:text-3xl font-extrabold nums-align', cfg.color)}>
                              {new Intl.NumberFormat('fa-IR').format(count)}
                            </div>
                            <div className="text-[10px] sm:text-xs font-medium text-muted-foreground mt-1 whitespace-nowrap">
                              {cfg.label}
                            </div>
                            <div className={cn(
                              'text-[10px] font-semibold mt-0.5 nums-align',
                              pct > 0 ? cfg.color : 'text-muted-foreground',
                            )}>
                              {pct.toFixed(1)}%
                            </div>
                          </div>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-[220px]">
                        <div className="text-xs space-y-1">
                          <div className="font-bold">{cfg.label}</div>
                          {statusData?.breakdown && Object.entries(statusData.breakdown).length > 0 && (
                            <div className="border-t pt-1 mt-1 space-y-0.5">
                              <div className="text-[10px] text-muted-foreground">تفکیک مراحل:</div>
                              {Object.entries(statusData.breakdown)
                                .sort(([, a], [, b]) => b - a)
                                .slice(0, 5)
                                .map(([step, cnt]) => (
                                  <div key={step} className="flex justify-between gap-3">
                                    <span>{STEP_LABELS[step] || step}</span>
                                    <span className="font-bold nums-align">{new Intl.NumberFormat('fa-IR').format(cnt)}</span>
                                  </div>
                                ))}
                            </div>
                          )}
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </React.Fragment>
                );
              })}
            </div>
          </div>
          {/* Transition summary bar */}
          {data.transitions.length > 0 && (
            <div className="mt-4 pt-3 border-t border-border/50">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] sm:text-xs text-muted-foreground">
                <span className="font-medium">بیشترین جریات:</span>
                {data.transitions.slice(0, 4).map((t, i) => (
                  <span key={i} className="flex items-center gap-1 nums-align">
                    <span className="font-medium">{STEP_LABELS[t.from] || t.from}</span>
                    <ArrowRight className="h-2.5 w-2.5" />
                    <span className="font-medium">{STATUS_CONFIG.find(s => s.key === t.to)?.label || t.to}</span>
                    <span className="text-foreground font-bold">{new Intl.NumberFormat('fa-IR').format(t.count)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
