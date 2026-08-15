'use client';

import React from 'react';
import { Send, Paperclip, XCircle, CreditCard } from 'lucide-react';

interface AlertBarProps {
  stats: {
    failed?: number;
    readyToSend?: number;
    processing?: number;
    unpaid?: number;
  } | null;
  onTabChange: (key: string) => void;
}

export default function AlertBar({ stats, onTabChange }: AlertBarProps) {
  if (!stats) return null;
  const hasAlerts = (stats.failed || 0) > 0 || (stats.readyToSend || 0) > 0 || (stats.processing || 0) > 0 || (stats.unpaid || 0) > 0;
  if (!hasAlerts) return null;

  return (
    <div className="relative border-b alert-bar-animated overflow-hidden">
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-l from-amber-400 via-rose-400 to-sky-400 animate-gradient-border" />
      <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-2 flex items-center gap-2 overflow-x-auto scrollbar-none">
        {stats.readyToSend > 0 && (
          <button
            className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 font-medium hover:bg-sky-100 dark:hover:bg-sky-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-sky-200 dark:border-sky-800"
            onClick={() => onTabChange('ready')}
          >
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/15 dark:bg-sky-400/20">
              <Send className="h-3.5 w-3.5" />
            </span>
            <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.readyToSend)} اعلام برای ارسال آماده شده است.</span>
            <XCircle className="h-3 w-3 opacity-50" />
          </button>
        )}
        {stats.processing > 0 && (
          <button
            className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 font-medium hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-blue-200 dark:border-blue-800"
            onClick={() => onTabChange('all')}
          >
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-blue-500/15 dark:bg-blue-400/20">
              <Paperclip className="h-3.5 w-3.5" />
            </span>
            <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.processing)} اعلام در حال ارسال است.</span>
            <XCircle className="h-3 w-3 opacity-50" />
          </button>
        )}
        {stats.failed > 0 && (
          <button
            className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 font-medium hover:bg-red-100 dark:hover:bg-red-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-red-200 dark:border-red-800"
            onClick={() => onTabChange('failed')}
          >
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-red-500/15 dark:bg-red-400/20">
              <XCircle className="h-3.5 w-3.5" />
            </span>
            <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.failed)} اعلام در حال بررسی است.</span>
            <XCircle className="h-3 w-3 opacity-50" />
          </button>
        )}
        {stats.unpaid > 0 && (
          <button
            className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-50 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400 font-medium hover:bg-rose-100 dark:hover:bg-rose-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-rose-200 dark:border-rose-800"
            onClick={() => onTabChange('unpaid')}
          >
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-rose-500/15 dark:bg-rose-400/20">
              <CreditCard className="h-3.5 w-3.5" />
            </span>
            <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.unpaid)} پرداخت نشده</span>
            <XCircle className="h-3 w-3 opacity-50" />
          </button>
        )}
      </div>
    </div>
  );
}
