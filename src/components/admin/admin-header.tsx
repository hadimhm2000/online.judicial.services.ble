'use client';

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
// DropdownMenu removed — all items now have dedicated header buttons
import {
  Shield, Bell, RefreshCw, Play, Pause, Volume2, VolumeX, MessageSquare,
  FileSpreadsheet, Moon, Sun, Maximize2, Minimize2, Printer, Keyboard,
  Wifi, WifiOff, Clock, Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export interface AdminHeaderProps {
  refreshing: boolean;
  onRefresh: () => void;
  autoRefresh: boolean;
  onToggleAutoRefresh: () => void;
  isMuted: boolean;
  onToggleMuted: () => void;
  activityCount: number;
  onOpenActivity: () => void;
  onOpenBotSender: () => void;
  onOpenSheetsPanel: () => void;
  onOpenWorkingHours: () => void;
  onOpenExemptUsers: () => void;
  isOnline: boolean;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onPrint: () => void;
  showShortcuts: boolean;
  onSetShowShortcuts: (v: boolean) => void;
  theme?: string;
  onToggleTheme?: () => void;
}

function PersianClock() {
  const [time, setTime] = useState('');
  useEffect(() => {
    const update = () => {
      setTime(new Intl.DateTimeFormat('fa-IR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(new Date()));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="font-mono text-xs tabular-nums text-muted-foreground/80 hidden md:flex items-center gap-1.5">
      <Clock className="h-3 w-3" />
      {time}
    </span>
  );
}

export default function AdminHeader({
  refreshing, onRefresh, autoRefresh, onToggleAutoRefresh,
  isMuted, onToggleMuted, activityCount, onOpenActivity,
  onOpenBotSender, onOpenSheetsPanel, onOpenWorkingHours, onOpenExemptUsers,
  isOnline, isFullscreen, onToggleFullscreen, onPrint,
  showShortcuts, onSetShowShortcuts, theme, onToggleTheme,
}: AdminHeaderProps) {
  return (
    <>
      <header className="sticky top-0 z-50 border-b bg-white/80 dark:bg-gray-900/80 backdrop-blur-xl premium-header glass-v3">
        <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="relative h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/25 shrink-0 neon-border">
                <Shield className="h-5 w-5 text-white" />
                <div className="absolute -top-0.5 -right-0.5 h-3 w-3 rounded-full bg-emerald-400 border-2 border-white dark:border-gray-900 animate-pulse" />
              </div>
              <div className="min-w-0">
                <h1 className="text-sm sm:text-base font-extrabold truncate text-shadow-premium">
                  پنل مدیریت خدمات قضایی
                </h1>
                <p className="text-[10px] sm:text-xs text-muted-foreground truncate">
                  سامانه آنلاین خدمات قضایی ایران
                </p>
              </div>
            </div>

            <div className="hidden md:block"><PersianClock /></div>

            <div className="flex items-center gap-1.5 sm:gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-9 gap-1.5 text-xs btn-press"
                onClick={refreshing ? undefined : onRefresh}
                disabled={refreshing}
              >
                <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
                <span className="hidden sm:inline">بروزرسانی</span>
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0"
                onClick={onToggleAutoRefresh}
                title={autoRefresh ? 'توقف بروزرسانی خودکار' : 'فعال‌سازی بروزرسانی خودکار'}
              >
                {autoRefresh ? (
                  <Pause className="h-4 w-4 text-emerald-600" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0"
                onClick={onToggleMuted}
                title={isMuted ? 'فعال کردن صدا' : 'بیصدا کردن'}
              >
                {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 relative"
                onClick={onOpenActivity}
                title="تاریخچه فعالیت‌ها"
              >
                <Bell className="h-4 w-4" />
                {activityCount > 0 && (
                  <span className="counter-badge">
                    {new Intl.NumberFormat('fa-IR').format(activityCount)}
                  </span>
                )}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 relative text-sky-600 hover:text-sky-700 hover:bg-sky-50 dark:hover:bg-sky-900/20"
                onClick={onOpenBotSender}
                title="ارسال پیام به کاربر"
              >
                <MessageSquare className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 relative text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                onClick={onOpenSheetsPanel}
                title="همگام‌سازی گوگل شیت"
              >
                <FileSpreadsheet className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-900/20"
                onClick={onOpenWorkingHours}
                title="ساعات کاری"
              >
                <Clock className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 text-violet-600 hover:text-violet-700 hover:bg-violet-50 dark:hover:bg-violet-900/20"
                onClick={onOpenExemptUsers}
                title="کاربران معاف از پرداخت"
              >
                <Users className="h-4 w-4" />
              </Button>

              {onToggleTheme && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 w-9 p-0"
                  onClick={onToggleTheme}
                  title="تغییر تم"
                >
                  {theme === 'dark' ? <Sun className="h-4 w-4 hidden dark:block" /> : <Moon className="h-4 w-4 dark:hidden" />}
                </Button>
              )}

              <div className={cn(
                'hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all duration-300',
                isOnline
                  ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400'
                  : 'bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400'
              )}>
                {isOnline ? (
                  <Wifi className="h-3.5 w-3.5" />
                ) : (
                  <WifiOff className="h-3.5 w-3.5 animate-pulse" />
                )}
                <span>{isOnline ? 'آنلاین' : 'آفلاین'}</span>
              </div>

              <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-muted/50 text-xs text-muted-foreground">
                {autoRefresh ? (
                  <>
                    <div className="relative">
                      <div className="h-2.5 w-2.5 rounded-full bg-emerald-500 status-dot-live" />
                    </div>
                    <span className="animate-pulse">خودکار</span>
                  </>
                ) : (
                  <span>متوقف</span>
                )}
              </div>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 hidden sm:flex"
                onClick={onToggleFullscreen}
                title={isFullscreen ? 'خروج از تمام صفحه' : 'تمام صفحه'}
              >
                {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 hidden sm:flex"
                onClick={onPrint}
                title="چاپ"
              >
                <Printer className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 hidden sm:flex"
                onClick={() => onSetShowShortcuts(true)}
                title="میانبر کلیدی"
              >
                <Keyboard className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {!isOnline && (
        <div className="border-b bg-red-50 dark:bg-red-950/30 px-3 sm:px-6 py-2 flex items-center justify-center gap-2 animate-fade-in-up">
          <WifiOff className="h-4 w-4 text-red-500 animate-pulse" />
          <span className="text-xs font-medium text-red-600 dark:text-red-400">
            اتصال شما برقرار نیست — داده‌ها ممکن است به‌روز نباشند
          </span>
        </div>
      )}
    </>
  );
}
