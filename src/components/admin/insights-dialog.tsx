'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, Star, Filter } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// ⭐ v1.9 — رضایت کاربران (Feedback) و قیف تبدیل فرم‌ها (FunnelEvent)

const FLOW_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام', LAVAYEH: 'لایحه', EZHHARNAMEH: 'اظهارنامه', TAJDID_NAZAR: 'دعاوی اعتراضی',
  CHECK: 'دادخواست', EALAM_VAKALAHT: 'اعلام وکالت', REGIONAL_VALUE: 'ارزش منطقه‌ای',
  DAMAGES: 'خسارت تأخیر و مهریه', BULK: 'ثبت دسته‌جمعی', CONTRACT_FIX: 'اصلاح قرارداد',
};

interface FeedbackData {
  summary: { count: number; average: number; distribution: number[] };
  items: { id: string; baleUserId: string; fullName: string | null; rating: number; context: string | null; createdAt: string }[];
}

interface FunnelFlow {
  flow: string;
  entered: number;
  paid: number;
  steps: { step: string; users: number }[];
}

const fa = (n: number) => new Intl.NumberFormat('fa-IR').format(n);
const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);

interface InsightsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function InsightsDialog({ open, onOpenChange }: InsightsDialogProps) {
  const [feedback, setFeedback] = useState<FeedbackData | null>(null);
  const [flows, setFlows] = useState<FunnelFlow[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch('/api/admin/feedback?days=30').then((r) => (r.ok ? r.json() : Promise.reject())),
      fetch('/api/admin/funnel?days=30').then((r) => (r.ok ? r.json() : Promise.reject())),
    ])
      .then(([fb, fn]) => {
        setFeedback(fb);
        setFlows(fn.flows || []);
      })
      .catch(() => toast.error('خطا در خواندن داده‌ها'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[88vh] dialog-premium" dir="rtl">
        <DialogHeader>
          <DialogTitle className="text-base font-bold">رضایت کاربران و قیف تبدیل</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">۳۰ روز اخیر</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : (
          <Tabs defaultValue="funnel" dir="rtl">
            <TabsList>
              <TabsTrigger value="funnel" className="gap-1.5"><Filter className="h-3.5 w-3.5" />قیف تبدیل</TabsTrigger>
              <TabsTrigger value="feedback" className="gap-1.5"><Star className="h-3.5 w-3.5" />رضایت کاربران</TabsTrigger>
            </TabsList>

            <TabsContent value="funnel" className="max-h-[60vh] overflow-y-auto scrollbar-premium space-y-4 pt-2">
              {!flows?.length && <p className="text-sm text-muted-foreground py-6 text-center">هنوز داده‌ای ثبت نشده است.</p>}
              {flows?.map((f) => {
                const biggestDrop = f.steps.reduce<{ step: string; drop: number } | null>((best, s, i) => {
                  if (i === 0) return best;
                  const drop = f.steps[i - 1].users - s.users;
                  return !best || drop > best.drop ? { step: s.step, drop } : best;
                }, null);
                return (
                  <section key={f.flow} className="p-3 rounded-xl border bg-card space-y-2">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <h3 className="font-bold text-sm">{FLOW_LABELS[f.flow] || f.flow}</h3>
                      <span className="text-xs text-muted-foreground">
                        ورود: {fa(f.entered)} نفر — پرداخت: {fa(f.paid)} نفر ({fa(pct(f.paid, f.entered))}٪)
                      </span>
                    </div>
                    <div className="space-y-1">
                      {f.steps.map((s) => (
                        <div key={s.step} className="flex items-center gap-2 text-xs">
                          <span
                            className={cn('w-56 truncate font-mono', biggestDrop?.step === s.step && biggestDrop.drop > 0 && 'text-red-600 font-bold')}
                            dir="ltr" title={s.step}
                          >
                            {s.step}
                          </span>
                          <div className="flex-1 h-2.5 rounded-full bg-muted overflow-hidden">
                            <div className="h-full bg-sky-500" style={{ width: `${pct(s.users, f.entered)}%` }} />
                          </div>
                          <span className="w-20 text-left tabular-nums">{fa(s.users)} ({fa(pct(s.users, f.entered))}٪)</span>
                        </div>
                      ))}
                    </div>
                    {biggestDrop && biggestDrop.drop > 0 && (
                      <p className="text-xs text-red-600">
                        بیشترین ریزش پیش از مرحلهٔ <span dir="ltr" className="font-mono">{biggestDrop.step}</span>: {fa(biggestDrop.drop)} نفر
                      </p>
                    )}
                  </section>
                );
              })}
            </TabsContent>

            <TabsContent value="feedback" className="max-h-[60vh] overflow-y-auto scrollbar-premium space-y-4 pt-2">
              {feedback && (
                <>
                  <div className="flex items-center gap-6 p-3 rounded-xl border bg-card">
                    <div className="text-center">
                      <div className="text-2xl font-bold">{feedback.summary.count ? feedback.summary.average.toFixed(1) : '—'}</div>
                      <div className="text-xs text-muted-foreground">میانگین از ۵ ({fa(feedback.summary.count)} نظر)</div>
                    </div>
                    <div className="flex-1 space-y-1">
                      {[5, 4, 3, 2, 1].map((r) => {
                        const n = feedback.summary.distribution[r - 1] || 0;
                        return (
                          <div key={r} className="flex items-center gap-2 text-xs">
                            <span className="w-8">{fa(r)}⭐</span>
                            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                              <div className={cn('h-full', r <= 2 ? 'bg-red-500' : 'bg-amber-500')} style={{ width: `${pct(n, feedback.summary.count)}%` }} />
                            </div>
                            <span className="w-8 text-left tabular-nums">{fa(n)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {feedback.items.map((i) => (
                      <div key={i.id} className={cn('flex items-center gap-3 p-2 rounded-lg border text-xs', i.rating <= 2 && 'border-red-300 bg-red-50/50 dark:bg-red-900/10')}>
                        <span className="w-10 font-bold">{fa(i.rating)}⭐</span>
                        <span className="flex-1 truncate">{i.fullName || i.baleUserId}{i.context ? ` — ${i.context}` : ''}</span>
                        <span className="text-muted-foreground">{new Intl.DateTimeFormat('fa-IR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(i.createdAt))}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}
