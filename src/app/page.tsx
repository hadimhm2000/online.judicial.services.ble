'use client';

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Search, RefreshCw, Download, Shield, Bell, Filter,
  LayoutDashboard, FileCheck2, FileWarning, CreditCard, Send, AlertTriangle, ListChecks, XCircle, Activity, Moon, Sun, Play, Pause, Zap, ChevronDown, ChevronLeft, CalendarDays, Maximize2, Minimize2, Trash2, Clock, ArrowUp, Printer, Keyboard, Wifi, WifiOff, FileSpreadsheet, Volume2, VolumeX, MessageSquare, ClipboardCheck, Paperclip, Check,
} from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { exportToExcel, exportToCSV } from '@/lib/export-utils';
import type { ExportRow } from '@/lib/export-utils';
import StatsCards from '@/components/admin/stats-cards';
import KpiDashboard from '@/components/admin/kpi-dashboard';
import CasesTable, { type CaseItem } from '@/components/admin/cases-table';
import type { AdminAction } from '@/components/admin/case-detail-dialog';
const CaseDetailDialog = React.lazy(() => import('@/components/admin/case-detail-dialog').then(m => ({ default: m.default })));
const ManualInterventionDialog = React.lazy(() => import('@/components/admin/manual-intervention-dialog').then(m => ({ default: m.default })));
const BatchActionsDialog = React.lazy(() => import('@/components/admin/batch-actions').then(m => ({ default: m.default })));
const ActivityPanel = React.lazy(() => import('@/components/admin/activity-panel').then(m => ({ default: m.default })));
const UserHistoryDialog = React.lazy(() => import('@/components/admin/user-history-dialog').then(m => ({ default: m.default })));
const BotMessageSender = React.lazy(() => import('@/components/admin/bot-message-sender').then(m => ({ default: m.default })));
const GoogleSheetsPanel = React.lazy(() => import('@/components/admin/google-sheets-panel').then(m => ({ default: m.default })));

import { ServicePieChart, StatusOverviewChart, RevenueChart } from '@/components/admin/charts';
import TrendLineChart from '@/components/admin/trend-line-chart';
import HeatmapChart from '@/components/admin/heatmap-chart';
import PipelineWidget from '@/components/admin/pipeline-widget';
import ServicePerfChart from '@/components/admin/service-perf-chart';
import LoadingBar from '@/components/admin/loading-bar';
import ConfettiAnimation from '@/components/admin/confetti-animation';
import CommandPalette from '@/components/admin/command-palette';
import type { CommandAction } from '@/components/admin/command-palette';
import { useNotificationListener, useNotificationMuted } from '@/hooks/use-notification-sound';

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
  ADMIN_SEND: 'ارسال پیام مدیریت',
};

interface Stats {
  total: number;
  completed: number;
  incomplete: number;
  unpaid: number;
  readyToSend: number;
  failed: number;
  cancelled: number;
  processing: number;
  todayCases: number;
  totalRevenue: number;
  unpaidRevenue: number;
  serviceBreakdown: { _count: { id: number }; serviceType: string }[];
  createdAt?: string;
}

interface Pagination {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

interface TabConfig {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  apiParam: string;
  badgeColor?: string;
  showConfirm?: boolean;
  showIntervention?: boolean;
}

const TABS: TabConfig[] = [
  { key: 'all', label: 'همه پرونده‌ها', icon: LayoutDashboard, apiParam: '' },
  { key: 'completed', label: 'ثبت شده', icon: FileCheck2, apiParam: 'COMPLETED', badgeColor: 'bg-emerald-500' },
  { key: 'incomplete', label: 'ناقص', icon: FileWarning, apiParam: 'INCOMPLETE', badgeColor: 'bg-amber-500', showIntervention: true },
  { key: 'unpaid', label: 'پرداخت نشده', icon: CreditCard, apiParam: 'PENDING_PAYMENT', badgeColor: 'bg-rose-500' },
  { key: 'ready', label: 'آماده ارسال', icon: Send, apiParam: '', badgeColor: 'bg-sky-500', showConfirm: true },
  { key: 'failed', label: 'شکست خورده', icon: AlertTriangle, apiParam: 'FAILED', badgeColor: 'bg-red-500', showIntervention: true },
  { key: 'cancelled', label: 'لغو شده', icon: XCircle, apiParam: 'CANCELLED' },
];

const SHORTCUTS = [
  { key: 'R', label: 'بروزرسانی' },
  { key: '/ یا S', label: 'جستجو' },
  { key: 'F', label: 'فیلتر' },
  { key: '1-7', label: 'تب‌ها' },
  { key: 'Esc', label: 'خروج تمام صفحه' },
];

function StatsCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border bg-card overflow-hidden h-[88px] sm:h-[100px]"
        >
          <div className="p-3.5 sm:p-4 h-full flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1 space-y-2">
              <div className="animate-shimmer h-3 w-16 rounded" />
              <div className="animate-shimmer h-6 w-20 rounded" />
              <div className="animate-shimmer h-2.5 w-24 rounded" />
            </div>
            <div className="animate-shimmer h-9 w-9 rounded-xl shrink-0" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ChartsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border bg-card overflow-hidden h-[300px] sm:h-[340px] animate-shimmer"
          />
        ))}
      </div>
      <div className="animate-shimmer rounded-xl border bg-card h-[220px] sm:h-[260px]" />
    </div>
  );
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

export default function AdminPanel() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [pagination, setPagination] = useState<Pagination | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  const [search, setSearch] = useState('');
  const [serviceFilter, setServiceFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState('createdAt');
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showCharts, setShowCharts] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [branchFilter, setBranchFilter] = useState('');
  const [provinceFilter, setProvinceFilter] = useState('all');
  const [errorFilter, setErrorFilter] = useState('all');
  const [refreshing, setRefreshing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [confirmSendCase, setConfirmSendCase] = useState<CaseItem | null>(null);
  const [confirmSendOpen, setConfirmSendOpen] = useState(false);
  const [deleteCase, setDeleteCase] = useState<CaseItem | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [searchTimer, setSearchTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  const [activityCount, setActivityCount] = useState(0);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);

  const { theme, setTheme } = useTheme();
  const searchRef = useRef<HTMLInputElement>(null);
  const prevFailedRef = useRef(0);
  const prevReadyToSendRef = useRef(0);

  const [detailCase, setDetailCase] = useState<CaseItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [interventionCase, setInterventionCase] = useState<CaseItem | null>(null);
  const [interventionOpen, setInterventionOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [adminActions, setAdminActions] = useState<AdminAction[]>([]);
  const [historyUser, setHistoryUser] = useState<{ baleUserId: string; fullName: string } | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [showConfetti, setShowConfetti] = useState(false);
  const [isMuted, setMuted] = useNotificationMuted();
  const [botSenderOpen, setBotSenderOpen] = useState(false);
  const [sheetsPanelOpen, setSheetsPanelOpen] = useState(false);
  const [batchConfirmSending, setBatchConfirmSending] = useState(false);
  const [batchConfirmDone, setBatchConfirmDone] = useState(false);

  useNotificationListener(
    stats?.failed || 0,
    prevFailedRef,
    stats?.readyToSend || 0,
    prevReadyToSendRef,
  );

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    setIsOnline(navigator.onLine);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/stats');
      if (res.ok) setStats(await res.json());
    } catch (e) {
      console.error(e);
    }
  }, []);

  const fetchActivityCount = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/activity-logs?limit=1');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) setActivityCount(data.length > 0 ? Math.min(data.length + 5, 99) : 0);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchCases = useCallback(async () => {
    setLoading(true);
    try {
      const tab = TABS.find((t) => t.key === activeTab);
      const params = new URLSearchParams();
      if (tab?.apiParam) params.set('status', tab.apiParam);
      if (activeTab === 'ready') params.set('readyToSend', 'true');
      if (search) params.set('search', search);
      if (serviceFilter !== 'all') params.set('serviceType', serviceFilter);
      if (dateFrom) params.set('dateFrom', dateFrom);
      if (dateTo) params.set('dateTo', dateTo);
      if (sortBy) params.set('sortBy', sortBy);
      if (sortOrder) params.set('sortOrder', sortOrder);
      if (branchFilter) params.set('branchName', branchFilter);
      if (provinceFilter !== 'all') params.set('province', provinceFilter);
      if (errorFilter === 'hasError') params.set('hasError', 'true');
      if (errorFilter !== 'all' && errorFilter !== 'hasError' && errorFilter) params.set('errorStep', errorFilter);
      params.set('page', String(page));
      params.set('limit', String(pageSize));

      const res = await fetch(`/api/admin/cases?${params}`);
      if (res.ok) {
        const data = await res.json();
        setCases(data.cases);
        setPagination(data.pagination);
      }
    } catch (e) {
      console.error(e);
      toast.error('خطا در دریافت اطلاعات');
    } finally {
      setLoading(false);
    }
  }, [activeTab, search, serviceFilter, dateFrom, dateTo, sortBy, sortOrder, page, pageSize, branchFilter, provinceFilter, errorFilter]);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchStats(), fetchCases(), fetchActivityCount()]);
    setRefreshing(false);
    toast.success('بروزرسانی انجام شد');
  }, [fetchStats, fetchCases, fetchActivityCount]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchStats();
      fetchCases();
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchStats, fetchCases]);

  useEffect(() => {
    fetchStats();
    fetchActivityCount();
  }, [fetchStats, fetchActivityCount]);

  useEffect(() => {
    fetchCases();
    setSelectedIds(new Set());
  }, [fetchCases]);

  useEffect(() => {
    const handleScroll = () => {
      setShowBackToTop(window.scrollY > 400);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const handleFullscreen = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreen);
    return () => document.removeEventListener('fullscreenchange', handleFullscreen);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    if (searchTimer) clearTimeout(searchTimer);
    setSearchTimer(setTimeout(() => {
      setPage(1);
    }, 400));
  }, [searchTimer]);

  const getDatePreset = (preset: string) => {
    const now = new Date();
    const fmt = (d: Date) => d.toISOString().slice(0, 10);
    if (preset === 'today') {
      setDateFrom(fmt(now));
      setDateTo(fmt(now));
    } else if (preset === 'week') {
      const weekAgo = new Date(now.getTime() - 7 * 86400000);
      setDateFrom(fmt(weekAgo));
      setDateTo(fmt(now));
    } else if (preset === 'month') {
      const monthAgo = new Date(now.getTime() - 30 * 86400000);
      setDateFrom(fmt(monthAgo));
      setDateTo(fmt(now));
    }
    setPage(1);
  };

  const clearAllFilters = useCallback(() => {
    setSearch('');
    setServiceFilter('all');
    setDateFrom('');
    setDateTo('');
    setBranchFilter('');
    setProvinceFilter('all');
    setErrorFilter('all');
    setPage(1);
  }, []);

  const requestConfirmSend = useCallback((c: CaseItem) => {
    setConfirmSendCase(c);
    setConfirmSendOpen(true);
  }, []);

  const executeConfirmSend = useCallback(async () => {
    if (!confirmSendCase) return;
    setConfirmSendOpen(false);
    try {
      const res = await fetch(`/api/admin/cases/${confirmSendCase.id}/confirm-send`, { method: 'POST' });
      if (res.ok) {
        toast.success(`پرونده ${confirmSendCase.fullName} تأیید و ارسال شد`);
        setShowConfetti(true);
        fetchCases();
        fetchStats();
        if (detailOpen) setDetailOpen(false);
      } else {
        toast.error('خطا در تأیید ارسال');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    }
    setConfirmSendCase(null);
  }, [confirmSendCase, detailOpen, fetchCases, fetchStats]);

  const handleDeleteCase = useCallback(async () => {
    if (!deleteCase) return;
    setDeleteOpen(false);
    try {
      const res = await fetch(`/api/admin/cases/${deleteCase.id}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success(`پرونده ${deleteCase.fullName} حذف شد`);
        fetchCases();
        fetchStats();
      } else {
        toast.error('خطا در حذف');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    }
    setDeleteCase(null);
  }, [deleteCase, fetchCases, fetchStats]);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    setPage(1);
    setSearch('');
  };

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
    setPage(1);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (cases.every((c) => selectedIds.has(c.id))) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(cases.map((c) => c.id)));
    }
  };

  const handleViewDetail = async (c: CaseItem) => {
    setDetailCase(c);
    setDetailOpen(true);
    try {
      const res = await fetch(`/api/admin/cases/${c.id}`);
      if (res.ok) {
        const data = await res.json();
        setDetailCase(data.case || c);
        setAdminActions(data.adminActions || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleIntervention = (c: CaseItem) => {
    setInterventionCase(c);
    setInterventionOpen(true);
  };

  const handleInterventionSubmit = async (data: {
    caseId: string;
    adminNote: string;
    actionType: string;
    newStatus: string;
    uploadedFileUrls: string[];
    sentViaBot: boolean;
  }) => {
    const res = await fetch(`/api/admin/cases/${data.caseId}/manual-intervention`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'خطا');
    }
    fetchCases();
    fetchStats();
    fetchActivityCount();
  };

  const handleUserClick = (c: CaseItem) => {
    setHistoryUser({ baleUserId: c.baleUserId, fullName: c.fullName });
    setHistoryOpen(true);
  };

  const handleExport = async (format: 'csv' | 'excel') => {
    try {
      const tab = TABS.find((t) => t.key === activeTab);
      const params = new URLSearchParams();
      if (tab?.apiParam) params.set('status', tab.apiParam);
      if (activeTab === 'ready') params.set('readyToSend', 'true');
      if (search) params.set('search', search);
      params.set('limit', '1000');

      const res = await fetch(`/api/admin/cases?${params}`);
      if (res.ok) {
        const data = await res.json();
        const rows = data.cases as CaseItem[];
        if (rows.length === 0) {
          toast.error('داده‌ای برای خروجی وجود ندارد');
          return;
        }
        const exportRows: ExportRow[] = rows.map((r) => ({
          fullName: r.fullName,
          baleUserId: r.baleUserId,
          serviceType: r.serviceType,
          status: r.status,
          fee: r.fee,
          feeStatus: r.feeStatus,
          branchName: r.branchName,
          createdAt: r.createdAt,
        }));
        const filename = `cases-${activeTab}-${new Date().toISOString().slice(0, 10)}`;
        if (format === 'csv') {
          exportToCSV(exportRows, filename);
          toast.success('فایل CSV دانلود شد');
        } else {
          exportToExcel(exportRows, filename);
          toast.success('فایل Excel دانلود شد');
        }
      }
    } catch (e) {
      toast.error('خطا در خروجی گرفتن');
    }
  };

  const handlePrint = () => window.print();

  const handleBatchConfirmSend = useCallback(async () => {
    if (selectedIds.size === 0) return;
    setBatchConfirmSending(true);
    try {
      const res = await fetch('/api/admin/cases/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: Array.from(selectedIds), action: 'CONFIRM_SEND_ALL' }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || `${new Intl.NumberFormat('fa-IR').format(selectedIds.size)} پرونده تأیید و ارسال شد`);
        setBatchConfirmDone(true);
        setTimeout(() => setBatchConfirmDone(false), 3000);
        setShowConfetti(true);
        setSelectedIds(new Set());
        fetchCases();
        fetchStats();
        fetchActivityCount();
      } else {
        toast.error('خطا در تأیید دسته‌ای');
      }
    } catch {
      toast.error('خطا در ارتباط با سرور');
    } finally {
      setBatchConfirmSending(false);
    }
  }, [selectedIds, fetchCases, fetchStats, fetchActivityCount]);

  const handleSeed = async () => {
    try {
      const res = await fetch('/api/admin/seed', { method: 'POST' });
      if (res.ok) {
        toast.success('داده‌های آزمایشی ایجاد شد');
        fetchStats();
        fetchCases();
      }
    } catch (e) {
      toast.error('خطا');
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.target as HTMLElement).isContentEditable) return;

      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        refreshAll();
      }
      if (e.key === '/' || e.key === 's' || e.key === 'S') {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        setShowFilters((v) => !v);
      }
      const num = parseInt(e.key);
      if (num >= 1 && num <= TABS.length) {
        e.preventDefault();
        handleTabChange(TABS[num - 1].key);
      }
      if (e.key === 'Escape' && isFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [refreshAll, isFullscreen]);

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('scrolled-into-view');
          }
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    );
    const els = document.querySelectorAll('.scroll-reveal');
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [stats, loading]);

  const currentTab = TABS.find((t) => t.key === activeTab);

  const alertCount = stats ? (stats.failed || 0) + (stats.readyToSend || 0) + (stats.unpaid || 0) + (stats.processing || 0) : 0;

  return (
    <div className="gradient-mesh-bg grid-pattern-bg min-h-screen flex flex-col bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950 transition-colors duration-300" data-loading={loading ? 'true' : 'false'}>
      <LoadingBar loading={loading} />
      {/* 1. Header - premium-header */}
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
              {/* Mobile-only: show only refresh, auto-refresh toggle, bell, theme */}
              <Button
                variant="outline"
                size="sm"
                className="h-9 gap-1.5 text-xs btn-press"
                onClick={refreshing ? undefined : refreshAll}
                disabled={refreshing}
              >
                <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
                <span className="hidden sm:inline">بروزرسانی</span>
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0"
                onClick={() => setAutoRefresh(!autoRefresh)}
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
                onClick={() => setMuted(!isMuted)}
                title={isMuted ? 'فعال کردن صدا' : 'بیصدا کردن'}
              >
                {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 relative"
                onClick={() => setActivityOpen(true)}
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
                onClick={() => setBotSenderOpen(true)}
                title="ارسال پیام به کاربر"
              >
                <MessageSquare className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 relative text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                onClick={() => setSheetsPanelOpen(true)}
                title="همگام‌سازی گوگل شیت"
              >
                <FileSpreadsheet className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                title="تغییر تم"
              >
                <Moon className="h-4 w-4 dark:hidden" />
                <Sun className="h-4 w-4 hidden dark:block" />
              </Button>

              {/* Desktop-only: clock, online indicator, fullscreen, print, keyboard shortcuts */}
              {/* Connection status indicator */}
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

              {/* 12. Auto-refresh indicator - larger dot, status-dot-live, pulse text */}
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
                onClick={toggleFullscreen}
                title={isFullscreen ? 'خروج از تمام صفحه' : 'تمام صفحه'}
              >
                {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 hidden sm:flex"
                onClick={handlePrint}
                title="چاپ"
              >
                <Printer className="h-4 w-4" />
              </Button>

              {/* 8. Keyboard shortcut help button */}
              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 hidden sm:flex"
                onClick={() => setShowShortcuts(true)}
                title="میانبر کلیدی"
              >
                <Keyboard className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Offline warning banner */}
      {!isOnline && (
        <div className="border-b bg-red-50 dark:bg-red-950/30 px-3 sm:px-6 py-2 flex items-center justify-center gap-2 animate-fade-in-up">
          <WifiOff className="h-4 w-4 text-red-500 animate-pulse" />
          <span className="text-xs font-medium text-red-600 dark:text-red-400">
            اتصال شما برقرار نیست — داده‌ها ممکن است به‌روز نباشند
          </span>
        </div>
      )}

      {/* 2. Alert Bar - announcement banners matching screenshot format */}
      {stats && (stats.failed > 0 || stats.readyToSend > 0 || stats.processing > 0) && (
        <div className="relative border-b alert-bar-animated overflow-hidden">
          <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-l from-amber-400 via-rose-400 to-sky-400 animate-gradient-border" />
          <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-2 flex items-center gap-2 overflow-x-auto scrollbar-none">
            {stats.readyToSend > 0 && (
              <button
                className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 font-medium hover:bg-sky-100 dark:hover:bg-sky-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-sky-200 dark:border-sky-800"
                onClick={() => handleTabChange('ready')}
              >
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/15 dark:bg-sky-400/20">
                  <Send className="h-3.5 w-3.5" />
                </span>
                <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.readyToSend)} {`اعلام برای ارسال آماده شده است.`}</span>
                <XCircle className="h-3 w-3 opacity-50" />
              </button>
            )}
            {stats.processing > 0 && (
              <button
                className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 font-medium hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-blue-200 dark:border-blue-800"
                onClick={() => handleTabChange('all')}
              >
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-blue-500/15 dark:bg-blue-400/20">
                  <Paperclip className="h-3.5 w-3.5" />
                </span>
                <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.processing)} {`اعلام در حال ارسال است.`}</span>
                <XCircle className="h-3 w-3 opacity-50" />
              </button>
            )}
            {stats.failed > 0 && (
              <button
                className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 font-medium hover:bg-red-100 dark:hover:bg-red-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-red-200 dark:border-red-800"
                onClick={() => handleTabChange('failed')}
              >
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-red-500/15 dark:bg-red-400/20">
                  <XCircle className="h-3.5 w-3.5" />
                </span>
                <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.failed)} {`اعلام در حال بررسی است.`}</span>
                <XCircle className="h-3 w-3 opacity-50" />
              </button>
            )}
            {stats.unpaid > 0 && (
              <button
                className="btn-premium flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-50 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400 font-medium hover:bg-rose-100 dark:hover:bg-rose-900/30 transition-all hover:scale-[1.02] active:scale-[0.98] shrink-0 shadow-sm border border-rose-200 dark:border-rose-800"
                onClick={() => handleTabChange('unpaid')}
              >
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-rose-500/15 dark:bg-rose-400/20">
                  <CreditCard className="h-3.5 w-3.5" />
                </span>
                <span className="text-xs whitespace-nowrap">{new Intl.NumberFormat('fa-IR').format(stats.unpaid)} {`پرداخت نشده`}</span>
                <XCircle className="h-3 w-3 opacity-50" />
              </button>
            )}
          </div>
        </div>
      )}

      <main className="flex-1 max-w-[1600px] w-full mx-auto px-3 sm:px-6 py-4 sm:py-6 space-y-5 animate-fade-in-up">
        <div className="scroll-reveal">
          {!stats && <StatsCardsSkeleton />}
          {stats && <StatsCards stats={stats} />}
        </div>
        <div className="divider-gradient" />
        <div className="scroll-reveal"><KpiDashboard /></div>
        <div className="scroll-reveal"><PipelineWidget /></div>
        {showCharts && !stats && <ChartsSkeleton />}
        {stats && showCharts && (
          <div className="scroll-reveal space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <ServicePieChart data={stats.serviceBreakdown} />
              <StatusOverviewChart stats={stats} />
              <RevenueChart stats={stats} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <ServicePerfChart />
            </div>
            <TrendLineChart />
            <HeatmapChart />
          </div>
        )}
        <div className="space-y-3">
          <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
            {/* 11. TabsList - rounded-xl, inner shadow, scrollbar-none */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
              <TabsList className="bg-muted/60 p-1 h-auto flex-shrink-0 rounded-xl shadow-[inset_0_1px_2px_oklch(0_0_0/6%)]">
                {TABS.map((tab, idx) => {
                  const Icon = tab.icon;
                  const badgeValue = stats
                    ? tab.key === 'completed' ? stats.completed
                      : tab.key === 'incomplete' ? stats.incomplete
                      : tab.key === 'unpaid' ? stats.unpaid
                      : tab.key === 'failed' ? stats.failed
                      : tab.key === 'ready' ? stats.readyToSend
                      : 0
                    : 0;
                  const hasNonZeroBadge = badgeValue > 0;
                  return (
                    <TabsTrigger
                      key={tab.key}
                      value={tab.key}
                      className="gap-1.5 text-xs sm:text-sm px-2.5 sm:px-4 min-h-[44px] sm:min-h-0 data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all"
                    >
                      <Icon className="h-3.5 w-3.5" />
                      <span>{tab.label}</span>
                      {/* 10. Tab badges - animate-badge-pulse for non-zero values */}
                      {stats && tab.apiParam && (
                        <Badge
                          className={cn(
                            'h-5 min-w-5 px-1.5 text-[10px] font-bold rounded-full text-white',
                            tab.badgeColor,
                            hasNonZeroBadge && 'animate-badge-pulse'
                          )}
                        >
                          {tab.key === 'completed' && stats.completed}
                          {tab.key === 'incomplete' && stats.incomplete}
                          {tab.key === 'unpaid' && stats.unpaid}
                          {tab.key === 'failed' && stats.failed}
                        </Badge>
                      )}
                      {stats && tab.key === 'ready' && (
                        <Badge className={cn(
                          'h-5 min-w-5 px-1.5 text-[10px] font-bold rounded-full text-white bg-sky-500',
                          hasNonZeroBadge && 'animate-badge-pulse'
                        )}>
                          {stats.readyToSend}
                        </Badge>
                      )}
                      {/* 7. kbd-shortcut for tab number hints */}
                      <kbd className="hidden lg:inline-flex kbd-shortcut">
                        {new Intl.NumberFormat('fa-IR').format(idx + 1)}
                      </kbd>
                    </TabsTrigger>
                  );
                })}
              </TabsList>
            </div>
          </Tabs>
          <div className="flex flex-wrap items-center gap-2">
            {/* 9. Search Input - breathe glow on focus */}
            <div className="relative flex-1 min-w-0 sm:min-w-[200px] max-w-full sm:max-w-md">
              <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                ref={searchRef}
                placeholder="جستجو (نام، کد رهگیری، شناسه بله...)  /"
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setSearchFocused(false)}
                className={cn(
                  'pr-9 h-9 text-sm bg-background shadow-sm focus-ring-premium',
                  searchFocused && 'animate-breathe-glow'
                )}
              />
              <button
                onClick={() => setCmdPaletteOpen(true)}
                className="absolute left-2 top-1/2 -translate-y-1/2 kbd-shortcut px-1.5 py-0.5 text-[9px] font-mono cursor-pointer hover:bg-muted transition-colors"
                title="Ctrl+K"
              >
                Ctrl K
              </button>
            </div>
            <Select value={serviceFilter} onValueChange={(v) => { setServiceFilter(v); setPage(1); }}>
              <SelectTrigger className="w-[140px] h-9 text-xs shadow-sm">
                <SelectValue placeholder="نوع خدمت" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">همه خدمات</SelectItem>
                <SelectItem value="INQUIRY">استعلام</SelectItem>
                <SelectItem value="LAVAYEH">ثبت لایحه</SelectItem>
                <SelectItem value="EZHHARNAMEH">اظهارنامه</SelectItem>
                <SelectItem value="EALAM_VAKALAHT">اعلام وکالت</SelectItem>
                <SelectItem value="STAMP_CALC">محاسبه تمبر</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant={showFilters ? 'default' : 'outline'}
              size="sm"
              className="h-9 gap-1.5 text-xs shadow-sm hover-lift-sm btn-press"
              onClick={() => setShowFilters(!showFilters)}
            >
              <Filter className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">فیلترها</span>
              <ChevronDown className={cn('h-3 w-3 transition-transform', showFilters && 'rotate-180')} />
            </Button>
            <div className="flex items-center gap-1.5 mr-auto">
              {selectedIds.size > 0 && (
                <Button
                  size="sm"
                  className="h-9 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 shadow-sm"
                  onClick={() => setBatchOpen(true)}
                >
                  <ListChecks className="h-3.5 w-3.5" />
                  {'عملیات دسته‌ای'} ({new Intl.NumberFormat('fa-IR').format(selectedIds.size)})
                </Button>
              )}
              {selectedIds.size > 0 && activeTab === 'ready' && (
                <Button
                  size="sm"
                  className={cn(
                    'h-9 gap-1.5 text-xs shadow-sm',
                    batchConfirmDone
                      ? 'bg-emerald-500 hover:bg-emerald-500'
                      : 'bg-sky-600 hover:bg-sky-700'
                  )}
                  onClick={handleBatchConfirmSend}
                  disabled={batchConfirmSending}
                >
                  {batchConfirmSending ? (
                    <div className="h-3.5 w-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : batchConfirmDone ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <ClipboardCheck className="h-3.5 w-3.5" />
                  )}
                  {batchConfirmDone
                    ? 'انجام شد'
                    : `تایید و ارسال (${new Intl.NumberFormat('fa-IR').format(selectedIds.size)})`}
                </Button>
              )}

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5 text-xs shadow-sm hover-lift-sm btn-press"
                  >
                    <Download className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">{'خروجی'}</span>
                    <ChevronDown className="h-3 w-3 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => handleExport('csv')}>
                    <Download className="ml-2 h-4 w-4" />
                    {'خروجی CSV'}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport('excel')}>
                    <FileSpreadsheet className="ml-2 h-4 w-4" />
                    {'خروجی Excel'}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                variant="outline"
                size="sm"
                className="h-9 gap-1.5 text-xs shadow-sm btn-press"
                onClick={() => setShowCharts(!showCharts)}
              >
                <Activity className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">نمودارها</span>
              </Button>
            </div>
          </div>
          {/* 3. Filter Panel - glass-panel, rounded-2xl, staggered animations */}
          {showFilters && (
            <>
            <div className="glass-panel rounded-2xl flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-end gap-3 p-4 border animate-in slide-in-from-top-2 duration-200">
              <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
                <label className="text-[11px] font-medium text-muted-foreground">از تاریخ</label>
                <Input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                  className="h-9 w-full sm:w-[160px] text-xs"
                />
              </div>
              <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '50ms' }}>
                <label className="text-[11px] font-medium text-muted-foreground">تا تاریخ</label>
                <Input
                  type="date"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                  className="h-9 w-full sm:w-[160px] text-xs"
                />
              </div>
              <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
                <label className="text-[11px] font-medium text-muted-foreground">دسترسی سریع</label>
                <div className="flex gap-1">
                  {([['today', 'امروز'], ['week', 'این هفته'], ['month', 'این ماه']] as const).map(([key, label]) => (
                    <Button
                      key={key}
                      variant="outline"
                      size="sm"
                      className="h-9 text-[11px] px-2.5"
                      onClick={() => getDatePreset(key)}
                    >
                      <CalendarDays className="h-3 w-3 ml-1" />
                      {label}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '150ms' }}>
                <label className="text-[11px] font-medium text-muted-foreground">مرتب‌سازی</label>
                <Select value={`${sortBy}-${sortOrder}`} onValueChange={(v) => {
                  const [field, order] = v.split('-');
                  setSortBy(field);
                  setSortOrder(order);
                  setPage(1);
                }}>
                  <SelectTrigger className="h-9 w-full sm:w-[160px] text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="createdAt-desc">جدیدترین</SelectItem>
                    <SelectItem value="createdAt-asc">قدیمی‌ترین</SelectItem>
                    <SelectItem value="fullName-asc">نام (الف-ی)</SelectItem>
                    <SelectItem value="fullName-desc">نام (ی-الف)</SelectItem>
                    <SelectItem value="fee-desc">گران‌ترین</SelectItem>
                    <SelectItem value="fee-asc">ارزان‌ترین</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {(dateFrom || dateTo || search) && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 text-xs text-muted-foreground hover:text-foreground animate-fade-in-up"
                  style={{ animationDelay: '200ms' }}
                  onClick={clearAllFilters}
                >
                  <XCircle className="h-3.5 w-3.5 ml-1" />
                  پاک‌سازی
                </Button>
              )}
            </div>
            <div className="w-full border-t border-border/50 pt-3 mt-1">
              <button
                type="button"
                className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors animate-fade-in-up"
                style={{ animationDelay: '250ms' }}
                onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
              >
                <ChevronLeft className={cn('h-3.5 w-3.5 transition-transform duration-200', showAdvancedFilters && '-rotate-90')} />
                {'فیلتر پیشرفته'}
              </button>
              {showAdvancedFilters && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                  <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-medium text-muted-foreground">{'نام شعبه'}</label>
                      {branchFilter && (
                        <button onClick={() => { setBranchFilter(''); setPage(1); }} className="text-[10px] text-muted-foreground hover:text-foreground">
                          <XCircle className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                    <div className="relative">
                      <Search className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        placeholder={'جستجوی شعبه...'}
                        value={branchFilter}
                        onChange={(e) => { setBranchFilter(e.target.value); setPage(1); }}
                        className="h-9 pr-8 text-xs"
                      />
                    </div>
                  </div>
                  <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '350ms' }}>
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-medium text-muted-foreground">{'استان'}</label>
                      {provinceFilter !== 'all' && (
                        <button onClick={() => { setProvinceFilter('all'); setPage(1); }} className="text-[10px] text-muted-foreground hover:text-foreground">
                          <XCircle className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                    <Select value={provinceFilter} onValueChange={(v) => { setProvinceFilter(v); setPage(1); }}>
                      <SelectTrigger className="h-9 w-full text-xs">
                        <SelectValue placeholder={'همه استان‌ها'} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">{'همه استان‌ها'}</SelectItem>
                        <SelectItem value="تهران">{'تهران'}</SelectItem>
                        <SelectItem value="اصفهان">{'اصفهان'}</SelectItem>
                        <SelectItem value="فارس">{'فارس'}</SelectItem>
                        <SelectItem value="خراسان رضوی">{'خراسان رضوی'}</SelectItem>
                        <SelectItem value="آذربایجان شرقی">{'آذربایجان شرقی'}</SelectItem>
                        <SelectItem value="مازندران">{'مازندران'}</SelectItem>
                        <SelectItem value="گیلان">{'گیلان'}</SelectItem>
                        <SelectItem value="خوزستان">{'خوزستان'}</SelectItem>
                        <SelectItem value="هرمزگان">{'هرمزگان'}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '400ms' }}>
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-medium text-muted-foreground">{'فیلتر خطا'}</label>
                      {errorFilter !== 'all' && (
                        <button onClick={() => { setErrorFilter('all'); setPage(1); }} className="text-[10px] text-muted-foreground hover:text-foreground">
                          <XCircle className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                    <Select value={errorFilter} onValueChange={(v) => { setErrorFilter(v); setPage(1); }}>
                      <SelectTrigger className="h-9 w-full text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">{'همه'}</SelectItem>
                        <SelectItem value="hasError">{'فقط خطادار'}</SelectItem>
                        <SelectItem value="PAYMENT">{'خطا در پرداخت'}</SelectItem>
                        <SelectItem value="SUBMIT">{'خطا در ثبت'}</SelectItem>
                        <SelectItem value="RESULT">{'خطا در دریافت نتیجه'}</SelectItem>
                        <SelectItem value="DOCUMENT">{'خطا در مستندات'}</SelectItem>
                        <SelectItem value="SEND">{'خطا در ارسال'}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
            </div>
            </>
          )}
          {/* 13. Active Filter Tags - animate-slide-in-right, left border accent */}
          {(search || serviceFilter !== 'all' || dateFrom || dateTo || branchFilter || provinceFilter !== 'all' || errorFilter !== 'all') && !showFilters && (
            <div className="animate-slide-in-right flex items-center gap-1.5 flex-wrap border-r-2 border-r-primary/30 pr-2">
              <span className="text-[11px] text-muted-foreground">فیلترهای فعال:</span>
              {search && (
                <Badge variant="secondary" className="text-[10px] gap-1">
                  جستجو: {search}
                  <button onClick={() => { setSearch(''); setPage(1); }} className="hover:text-foreground">
                    <XCircle className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {serviceFilter !== 'all' && (
                <Badge variant="secondary" className="text-[10px] gap-1">
                  {SERVICE_LABELS[serviceFilter] || serviceFilter}
                  <button onClick={() => { setServiceFilter('all'); setPage(1); }} className="hover:text-foreground">
                    <XCircle className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {branchFilter && (
                <Badge variant="secondary" className="text-[10px] gap-1">
                  {'شعبه: '}{branchFilter}
                  <button onClick={() => { setBranchFilter(''); setPage(1); }} className="hover:text-foreground">
                    <XCircle className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {provinceFilter !== 'all' && (
                <Badge variant="secondary" className="text-[10px] gap-1">
                  {provinceFilter}
                  <button onClick={() => { setProvinceFilter('all'); setPage(1); }} className="hover:text-foreground">
                    <XCircle className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {errorFilter !== 'all' && (
                <Badge variant="secondary" className="text-[10px] gap-1">
                  {errorFilter === 'hasError' ? 'خطادار' : errorFilter}
                  <button onClick={() => { setErrorFilter('all'); setPage(1); }} className="hover:text-foreground">
                    <XCircle className="h-3 w-3" />
                  </button>
                </Badge>
              )}
            </div>
          )}
        </div>
        {/* Ready to Send info banner */}
        {activeTab === 'ready' && stats && stats.readyToSend > 0 && (
          <div className="scroll-reveal">
            <div className="rounded-xl bg-gradient-to-l from-sky-50 via-white to-sky-50 dark:from-sky-950/20 dark:via-gray-900 dark:to-sky-950/20 border border-sky-200 dark:border-sky-800 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center shrink-0">
                  <ClipboardCheck className="h-5 w-5 text-sky-600" />
                </div>
                <div>
                  <p className="text-sm font-bold text-sky-700 dark:text-sky-300">{new Intl.NumberFormat('fa-IR').format(stats.readyToSend)} {`پرونده برای ارسال آماده است`}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{`آیتم‌های مورد نظر را انتخاب کنید و دکمه تایید و ارسال را بزنید`}</p>
                </div>
              </div>
              {selectedIds.size > 0 && (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-medium text-sky-600 dark:text-sky-400">{new Intl.NumberFormat('fa-IR').format(selectedIds.size)} {`انتخاب شده`}</span>
                  <Button
                    size="sm"
                    className={cn(
                      'h-10 gap-2 text-xs shadow-md',
                      batchConfirmDone ? 'bg-emerald-500' : 'bg-sky-600 hover:bg-sky-700'
                    )}
                    onClick={handleBatchConfirmSend}
                    disabled={batchConfirmSending}
                  >
                    {batchConfirmSending ? (
                      <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : batchConfirmDone ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    {batchConfirmDone
                      ? `انجام شد!`
                      : `تایید و ارسال`}
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
        <div className="scroll-reveal">
        <CasesTable
          cases={cases}
          loading={loading}
          pagination={pagination}
          onPageChange={setPage}
          onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
          onSort={handleSort}
          sortBy={sortBy}
          sortOrder={sortOrder}
          onViewDetail={handleViewDetail}
          onRowClick={handleViewDetail}
          onClearFilters={clearAllFilters}
          onConfirmSend={requestConfirmSend}
          onManualIntervention={handleIntervention}
          onDeleteCase={(c) => { setDeleteCase(c); setDeleteOpen(true); }}
          showConfirmButton={currentTab?.showConfirm}
          showInterventionButton={currentTab?.showIntervention}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onToggleSelectAll={toggleSelectAll}
          onUserClick={handleUserClick}
          onRefresh={() => { fetchCases(); fetchStats(); }}
        />
        </div>
        {/* 7. Keyboard shortcut hints - kbd-shortcut class */}
        <div className="flex items-center justify-center gap-4 text-[10px] text-muted-foreground/60 pb-2">
          <span className="flex items-center gap-1">
            <kbd className="kbd-shortcut">R</kbd>
            بروزرسانی
          </span>
          <span className="flex items-center gap-1">
            <kbd className="kbd-shortcut">/</kbd>
            جستجو
          </span>
          <span className="flex items-center gap-1">
            <kbd className="kbd-shortcut">F</kbd>
            فیلتر
          </span>
          <span className="flex items-center gap-1">
            <kbd className="kbd-shortcut">1-7</kbd>
            تب‌ها
          </span>
        </div>
      </main>

      {/* 4. Footer - glass-footer, dividers, larger dots, gradient version text */}
      <footer className="glass-v2 mt-auto">
        <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] text-muted-foreground hidden sm:block">
              پنل مدیریت خدمات قضایی آنلاین {'—'}{' '}
              <span className="bg-gradient-to-l from-emerald-600 to-teal-500 bg-clip-text text-transparent font-bold">نسخه ۸.۰</span>
            </p>
            <div className="hidden sm:block w-px h-4 bg-border" />
            {stats && (
              <div className="hide-on-tiny flex items-center gap-3 text-[10px] text-muted-foreground mx-auto">
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  <span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.completed)}</span> تکمیل
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-amber-500" />
                  <span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.incomplete)}</span> ناقص
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-red-500" />
                  <span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.failed)}</span> شکست
                </span>
                <span className="text-muted-foreground/50">|</span>
                <span>درآمد: <span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.totalRevenue)}</span> ت</span>
              </div>
            )}
            <div className="hidden sm:block w-px h-4 bg-border" />
            <div className="flex items-center gap-1.5">
              <Button variant="ghost" size="sm" className="h-7 text-[10px] text-muted-foreground hover-glow-emerald" onClick={handleSeed}>
                <Zap className="h-3 w-3 ml-1" />
                <span className="hidden sm:inline">داده آزمایشی</span>
              </Button>
            </div>
          </div>
        </div>
      </footer>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <CaseDetailDialog
        caseItem={detailCase}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        onManualIntervention={handleIntervention}
        onConfirmSend={requestConfirmSend}
        onDeleteCase={(c) => { setDeleteCase(c); setDeleteOpen(true); setDetailOpen(false); }}
        adminActions={adminActions}
      />
      </Suspense>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <ManualInterventionDialog
        caseItem={interventionCase}
        open={interventionOpen}
        onClose={() => setInterventionOpen(false)}
        onSubmit={handleInterventionSubmit}
      />
      </Suspense>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <BatchActionsDialog
        selectedIds={Array.from(selectedIds)}
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        onDone={() => { fetchCases(); fetchStats(); setSelectedIds(new Set()); fetchActivityCount(); }}
      />
      </Suspense>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <ActivityPanel open={activityOpen} onClose={() => setActivityOpen(false)} />
      </Suspense>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <UserHistoryDialog
        baleUserId={historyUser?.baleUserId || ''}
        fullName={historyUser?.fullName || ''}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
      </Suspense>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <BotMessageSender
        open={botSenderOpen}
        onClose={() => setBotSenderOpen(false)}
        onRefresh={() => { fetchStats(); fetchCases(); }}
      />
      </Suspense>

      <Suspense fallback={<div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />}>
      <GoogleSheetsPanel
        open={sheetsPanelOpen}
        onClose={() => setSheetsPanelOpen(false)}
      />
      </Suspense>

      {/* 14. Confirm Send Dialog - dialog-premium, animate-float icon, gradient preview */}
      <Dialog open={confirmSendOpen} onOpenChange={setConfirmSendOpen}>
        <DialogContent className="max-w-sm p-0 dialog-premium" dir="rtl">
          <DialogHeader className="p-5 pb-0">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center animate-float">
                <Send className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold">تأیید ارسال</DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground mt-1">
                  آیا از ارسال نتیجه پرونده مطمئن هستید؟
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <div className="p-5">
            {confirmSendCase && (
              <div className="bg-gradient-to-br from-emerald-50/80 to-teal-50/50 dark:from-emerald-950/20 dark:to-teal-950/10 rounded-lg p-3 space-y-1.5 border border-emerald-100 dark:border-emerald-900/30">
                <p className="text-sm font-medium">{confirmSendCase.fullName}</p>
                <p className="text-xs text-muted-foreground">{SERVICE_LABELS[confirmSendCase.serviceType] || confirmSendCase.serviceType}</p>
                {confirmSendCase.trackingCode && (
                  <p className="text-[11px] text-muted-foreground font-mono" dir="ltr">کد: {confirmSendCase.trackingCode}</p>
                )}
              </div>
            )}
          </div>
          <DialogFooter className="p-5 pt-0 gap-2">
            <Button variant="outline" onClick={() => setConfirmSendOpen(false)}>انصراف</Button>
            <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={executeConfirmSend}>
              <Send className="h-4 w-4 ml-2" />
              تأیید و ارسال
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 14. Delete Dialog - dialog-premium, animate-float icon, gradient preview */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="max-w-sm p-0 dialog-premium" dir="rtl">
          <DialogHeader className="p-5 pb-0">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center animate-float">
                <Trash2 className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold">حذف پرونده</DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground mt-1">
                  این عمل غیرقابل بازگشت است
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <div className="p-5">
            {deleteCase && (
              <div className="bg-gradient-to-br from-red-50/80 to-rose-50/50 dark:from-red-950/20 dark:to-rose-950/10 rounded-lg p-3 space-y-1.5 border border-red-200 dark:border-red-800">
                <p className="text-sm font-medium">{deleteCase.fullName}</p>
                <p className="text-xs text-muted-foreground">{SERVICE_LABELS[deleteCase.serviceType] || deleteCase.serviceType}</p>
              </div>
            )}
          </div>
          <DialogFooter className="p-5 pt-0 gap-2">
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>انصراف</Button>
            <Button className="bg-red-600 hover:bg-red-700" onClick={handleDeleteCase}>
              <Trash2 className="h-4 w-4 ml-2" />
              حذف نهایی
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 8. Keyboard Shortcut Help Overlay */}
      <Dialog open={showShortcuts} onOpenChange={setShowShortcuts}>
        <DialogContent className="max-w-md p-0 dialog-premium" dir="rtl">
          <DialogHeader className="p-5 pb-0">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center animate-float">
                <Keyboard className="h-5 w-5 text-violet-600" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold">میانبر کلیدی</DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground mt-1">
                  دسترسی سریع به ابزارهای پنل
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <div className="p-5">
            <div className="grid grid-cols-2 gap-2.5">
              {SHORTCUTS.map((s) => (
                <div
                  key={s.key}
                  className="flex items-center gap-3 p-2.5 rounded-lg bg-muted/40 border border-border/50"
                >
                  <kbd className="kbd-shortcut shrink-0 text-[10px]">{s.key}</kbd>
                  <span className="text-xs text-muted-foreground">{s.label}</span>
                </div>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ConfettiAnimation active={showConfetti} onComplete={() => setShowConfetti(false)} />

      {/* Command Palette - Ctrl+K */}
      <CommandPalette open={cmdPaletteOpen} onOpenChange={setCmdPaletteOpen} actions={[
        { id: 'refresh', label: 'بروزرسانی', icon: RefreshCw, shortcut: 'R', group: 'عملیات', onSelect: refreshAll },
        { id: 'search', label: 'جستجو', icon: Search, shortcut: '/ S', group: 'عملیات', onSelect: () => searchRef.current?.focus() },
        { id: 'filter', label: 'فیلترها', icon: Filter, shortcut: 'F', group: 'عملیات', onSelect: () => setShowFilters(true) },
        { id: 'export-csv', label: 'خروجی CSV', icon: FileSpreadsheet, group: 'خروجی', onSelect: () => handleExport('csv') },
        { id: 'export-excel', label: 'خروجی Excel', icon: FileSpreadsheet, group: 'خروجی', onSelect: () => handleExport('excel') },
        { id: 'print', label: 'چاپ', icon: Printer, group: 'خروجی', onSelect: handlePrint },
        { id: 'tab-all', label: 'همه پرونده‌ها', icon: LayoutDashboard, shortcut: '1', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('all') },
        { id: 'tab-completed', label: 'ثبت شده', icon: FileCheck2, shortcut: '2', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('completed') },
        { id: 'tab-incomplete', label: 'ناقص', icon: FileWarning, shortcut: '3', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('incomplete') },
        { id: 'tab-unpaid', label: 'پرداخت نشده', icon: CreditCard, shortcut: '4', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('unpaid') },
        { id: 'tab-ready', label: 'آماده ارسال', icon: Send, shortcut: '5', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('ready') },
        { id: 'tab-failed', label: 'شکست خورده', icon: AlertTriangle, shortcut: '6', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('failed') },
        { id: 'tab-cancelled', label: 'لغو شده', icon: XCircle, shortcut: '7', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('cancelled') },
        { id: 'toggle-charts', label: stats && showCharts ? 'مخفی کردن نمودارها' : 'نمایش نمودارها', icon: ListChecks, group: 'تنظیمات', onSelect: () => setShowCharts(v => !v) },
        { id: 'toggle-theme', label: theme === 'dark' ? 'حالت روشن' : 'حالت تاریک', icon: theme === 'dark' ? Sun : Moon, group: 'تنظیمات', onSelect: () => setTheme(theme === 'dark' ? 'light' : 'dark') },
        { id: 'activity', label: 'تاریخچه فعالیت‌ها', icon: Activity, group: 'تنظیمات', onSelect: () => setActivityOpen(true) },
        { id: 'shortcuts', label: 'میانبر کلیدی', icon: Keyboard, group: 'تنظیمات', onSelect: () => setShowShortcuts(true) },
        { id: 'bot-sender', label: 'ارسال پیام به کاربر', icon: MessageSquare, group: 'تنظیمات', onSelect: () => setBotSenderOpen(true) },
        { id: 'google-sheets', label: 'همگام‌سازی گوگل شیت', icon: FileSpreadsheet, group: 'تنظیمات', onSelect: () => setSheetsPanelOpen(true) },
      ] as CommandAction[]} />

      {/* 6. Back to Top - back-to-top-btn, gradient background */}
      {showBackToTop && (
        <button
          onClick={scrollToTop}
          className="fixed bottom-20 left-5 z-40 h-10 w-10 rounded-full bg-gradient-to-br from-primary to-primary/80 text-primary-foreground back-to-top-btn hover:scale-110 active:scale-95 flex items-center justify-center animate-slide-up-fade-in print:hidden"
          title="بازگشت به بالا"
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      )}

      {/* 5. Mobile Bottom Nav - mobile-nav-premium, gradient active indicator */}
      {TABS.length > 0 && (
        <nav className="fixed bottom-0 left-0 right-0 z-50 sm:hidden mobile-nav-premium print:hidden safe-bottom">
          <div className="flex items-center justify-around py-1.5 px-1">
            {TABS.slice(0, 5).map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabChange(tab.key)}
                  className={cn(
                    'flex flex-col items-center gap-0.5 py-1 px-2 rounded-lg transition-all min-w-[48px] relative',
                    isActive
                      ? 'text-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="text-[9px] font-medium leading-tight">{tab.label}</span>
                  {isActive && (
                    <div className="absolute -top-1 inset-x-2 h-0.5 rounded-full bg-gradient-to-l from-primary/80 via-primary to-primary/80" />
                  )}
                </button>
              );
            })}
          </div>
        </nav>
      )}
    </div>
  );
}
