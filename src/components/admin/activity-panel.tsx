'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  History,
  RefreshCw,
  CheckCircle2,
  Send,
  AlertTriangle,
  FileCheck2,
  ArrowLeftRight,
  Search,
  Inbox,
} from 'lucide-react';

interface ActivityLog {
  id: string;
  caseId: string | null;
  action: string;
  details: string | null;
  createdAt: string;
}

interface ActivityPanelProps {
  open: boolean;
  onClose: () => void;
}

const ACTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  STATUS_CHANGE: ArrowLeftRight,
  CONFIRM_SEND: Send,
  MOVE_TO_READY: FileCheck2,
  BATCH_APPROVE_PAYMENT: CheckCircle2,
  BATCH_STATUS_CHANGE: ArrowLeftRight,
  BATCH_MOVE_TO_READY: FileCheck2,
  BATCH_CONFIRM_SEND: Send,
  MANUAL_INTERVENTION: AlertTriangle,
};

const ACTION_COLORS: Record<string, { dot: string; badge: string; border: string }> = {
  STATUS_CHANGE: { dot: 'bg-sky-500', badge: 'bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300', border: 'border-sky-200 dark:border-sky-800' },
  CONFIRM_SEND: { dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', border: 'border-emerald-200 dark:border-emerald-800' },
  MOVE_TO_READY: { dot: 'bg-indigo-500', badge: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300', border: 'border-indigo-200 dark:border-indigo-800' },
  BATCH_APPROVE_PAYMENT: { dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', border: 'border-emerald-200 dark:border-emerald-800' },
  BATCH_STATUS_CHANGE: { dot: 'bg-sky-500', badge: 'bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300', border: 'border-sky-200 dark:border-sky-800' },
  BATCH_MOVE_TO_READY: { dot: 'bg-indigo-500', badge: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300', border: 'border-indigo-200 dark:border-indigo-800' },
  BATCH_CONFIRM_SEND: { dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', border: 'border-emerald-200 dark:border-emerald-800' },
  MANUAL_INTERVENTION: { dot: 'bg-amber-500', badge: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', border: 'border-amber-200 dark:border-amber-800' },
};

const ACTION_LABELS: Record<string, string> = {
  STATUS_CHANGE: 'تغییر وضعیت',
  CONFIRM_SEND: 'تأیید ارسال',
  MOVE_TO_READY: 'انتقال به آماده',
  BATCH_APPROVE_PAYMENT: 'تأیید پرداخت',
  BATCH_STATUS_CHANGE: 'تغییر وضعیت',
  BATCH_MOVE_TO_READY: 'انتقال دسته‌ای',
  BATCH_CONFIRM_SEND: 'ارسال دسته‌ای',
  MANUAL_INTERVENTION: 'مداخله دستی',
};

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'لحظاتی پیش';
  if (mins < 60) return `${new Intl.NumberFormat('fa-IR').format(mins)} دقیقه پیش`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${new Intl.NumberFormat('fa-IR').format(hrs)} ساعت پیش`;
  const days = Math.floor(hrs / 24);
  return `${new Intl.NumberFormat('fa-IR').format(days)} روز پیش`;
}

function formatFullDate(dateStr: string): string {
  return new Intl.DateTimeFormat('fa-IR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dateStr));
}

export default function ActivityPanel({ open, onClose }: ActivityPanelProps) {
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/activity-logs?limit=100');
      if (res.ok) setLogs(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchLogs();
  }, [open, fetchLogs]);

  const filteredLogs = useMemo(() => {
    if (!searchQuery.trim()) return logs;
    const q = searchQuery.toLowerCase();
    return logs.filter((log) =>
      (log.action && log.action.toLowerCase().includes(q)) ||
      (log.details && log.details.toLowerCase().includes(q))
    );
  }, [logs, searchQuery]);

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-full sm:w-[420px]" dir="rtl">
        <SheetHeader className="p-5 pb-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-base font-bold flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-purple-500 to-violet-600 flex items-center justify-center shadow-sm shadow-violet-500/25">
                <History className="h-4 w-4 text-white" />
              </div>
              {"تاریخچه فعالیت‌ها"}
            </SheetTitle>
            <Button
              variant="outline"
              size="sm"
              className="h-8 transition-all duration-200 hover:shadow-sm"
              onClick={fetchLogs}
              disabled={loading}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            </Button>
          </div>
          {logs.length > 0 && (
            <p className="text-xs text-muted-foreground mt-1.5">
              {new Intl.NumberFormat('fa-IR').format(logs.length)} {"فعالیت اخیر"}
            </p>
          )}
        </SheetHeader>
        <div className="p-5">
          {logs.length > 0 && (
            <div className="relative mb-4">
              <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={"جستجو در فعالیت‌ها..."}
                className="pr-9 h-9 text-sm transition-all duration-200 focus:ring-2 focus:ring-primary/20"
              />
            </div>
          )}

          {filteredLogs.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <svg width="120" height="120" viewBox="0 0 120 120" fill="none" className="mb-4 opacity-30">
                <rect x="20" y="25" width="80" height="70" rx="8" stroke="currentColor" strokeWidth="2" fill="none" />
                <line x1="35" y1="45" x2="85" y2="45" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <line x1="35" y1="55" x2="75" y2="55" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <line x1="35" y1="65" x2="65" y2="65" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <line x1="35" y1="75" x2="80" y2="75" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <circle cx="90" cy="30" r="12" stroke="currentColor" strokeWidth="2" fill="var(--background)" />
                <line x1="85" y1="30" x2="95" y2="30" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <line x1="90" y1="25" x2="90" y2="35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <div className="flex items-center gap-2 mb-1">
                <Inbox className="h-5 w-5" />
                <p className="text-sm font-medium">{searchQuery ? 'نتیجه‌ای یافت نشد' : 'فعالیتی ثبت نشده'}</p>
              </div>
              <p className="text-xs text-muted-foreground/60">
                {searchQuery ? 'عبارت دیگری را امتحان کنید' : 'اقدامات ادمین اینجا نمایان می‌شود'}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[calc(100vh-180px)]">
              <div className="space-y-0 relative">
                <div className="absolute right-[15px] top-3 bottom-3 w-px bg-gradient-to-b from-primary/30 via-border to-transparent" />

                {filteredLogs.map((log, i) => {
                  const Icon = ACTION_ICONS[log.action] || History;
                  const colors = ACTION_COLORS[log.action] || { dot: 'bg-gray-500', badge: 'bg-gray-50 text-gray-700 dark:bg-gray-900/30 dark:text-gray-300', border: 'border-gray-200 dark:border-gray-800' };

                  return (
                    <div
                      key={log.id}
                      className="flex gap-3 relative pr-1 animate-slide-in-right"
                      style={{ animationDelay: `${Math.min(i * 50, 300)}ms` }}
                    >
                      <div className="relative z-10 flex items-center justify-center">
                        <span className={cn('h-3 w-3 rounded-full shrink-0 shadow-sm', colors.dot)} />
                        <div className="h-[30px] w-[30px] rounded-full flex items-center justify-center shrink-0 absolute bg-background border-2 border-border">
                          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                        </div>
                      </div>

                      <div className={cn(
                        'flex-1 min-w-0 rounded-xl p-3 transition-all duration-200 hover:shadow-sm hover:bg-muted/60 border border-transparent hover:border-border/50 mb-2'
                      )}>
                        <div className="flex items-center justify-between gap-2">
                          <Badge
                            className={cn('text-[10px] font-medium shadow-sm border', colors.badge, colors.border)}
                          >
                            {ACTION_LABELS[log.action] || log.action}
                          </Badge>
                          <span className="text-[10px] text-muted-foreground shrink-0 font-mono">
                            {formatFullDate(log.createdAt)}
                          </span>
                        </div>
                        {log.details && (
                          <p className="text-xs text-muted-foreground mt-1.5 leading-6">
                            {log.details}
                          </p>
                        )}
                        <p className="text-[10px] text-muted-foreground/50 mt-1">
                          {formatTimeAgo(log.createdAt)}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
