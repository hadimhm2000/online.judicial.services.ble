'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Search, Download, Filter,
  LayoutDashboard, FileCheck2, FileWarning, CreditCard, Send, AlertTriangle, ListChecks, XCircle, Activity,
  ChevronDown, ChevronLeft, CalendarDays, ArrowUp, Zap, ClipboardCheck, Check, Paperclip,
  Settings, Users, FileSpreadsheet, Printer, Keyboard, Sun, Moon, MessageSquare,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { exportToExcel, exportToCSV } from '@/lib/export-utils';
import type { ExportRow } from '@/lib/export-utils';
import StatsCards from '@/components/admin/stats-cards';
import KpiDashboard from '@/components/admin/kpi-dashboard';
import CasesTable, { type CaseItem } from '@/components/admin/cases-table';
import type { AdminAction } from '@/components/admin/case-detail-dialog';
import { ServicePieChart, StatusOverviewChart, RevenueChart } from '@/components/admin/charts';
import TrendLineChart from '@/components/admin/trend-line-chart';
import HeatmapChart from '@/components/admin/heatmap-chart';
import PipelineWidget from '@/components/admin/pipeline-widget';
import ServicePerfChart from '@/components/admin/service-perf-chart';
import LoadingBar from '@/components/admin/loading-bar';
import ConfettiAnimation from '@/components/admin/confetti-animation';
import CommandPalette from '@/components/admin/command-palette';
import type { CommandAction } from '@/components/admin/command-palette';
import AdminHeader from '@/components/admin/admin-header';
import AlertBar from '@/components/admin/alert-bar';
import FilterBar from '@/components/admin/filter-bar';
import PageDialogs from '@/components/admin/page-dialogs';
import MobileNav from '@/components/admin/mobile-nav';
import LazyPanels from '@/components/admin/lazy-panels';
import { useNotificationListener, useNotificationMuted } from '@/hooks/use-notification-sound';

const SERVICE_LABELS: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
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
  isServiceType?: string;
  excludeInquiry?: boolean;
}

const TABS: TabConfig[] = [
  { key: 'all', label: 'همه پرونده‌ها', icon: LayoutDashboard, apiParam: '', excludeInquiry: true },
  { key: 'inquiry', label: 'استعلامات', icon: Search, apiParam: '', badgeColor: 'bg-blue-500', isServiceType: 'INQUIRY' },
  { key: 'completed', label: 'ثبت شده', icon: FileCheck2, apiParam: 'COMPLETED', badgeColor: 'bg-emerald-500', excludeInquiry: true },
  { key: 'incomplete', label: 'ناقص', icon: FileWarning, apiParam: 'INCOMPLETE', badgeColor: 'bg-amber-500', showIntervention: true, excludeInquiry: true },
  { key: 'unpaid', label: 'پرداخت نشده', icon: CreditCard, apiParam: 'PENDING_PAYMENT', badgeColor: 'bg-rose-500', excludeInquiry: true },
  { key: 'ready', label: 'آماده ارسال', icon: Send, apiParam: '', badgeColor: 'bg-sky-500', showConfirm: true },
  { key: 'failed', label: 'شکست خورده', icon: AlertTriangle, apiParam: 'FAILED', badgeColor: 'bg-red-500', showIntervention: true, excludeInquiry: true },
  { key: 'cancelled', label: 'لغو شده', icon: XCircle, apiParam: 'CANCELLED', excludeInquiry: true },
];

const SHORTCUTS = [
  { key: 'R', label: 'بروزرسانی' },
  { key: '/ یا S', label: 'جستجو' },
  { key: 'F', label: 'فیلتر' },
  { key: '1-8', label: 'تب‌ها' },
  { key: 'Esc', label: 'خروج تمام صفحه' },
];

function StatsCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="rounded-xl border bg-card overflow-hidden h-[88px] sm:h-[100px]">
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
          <div key={i} className="rounded-xl border bg-card overflow-hidden h-[300px] sm:h-[340px] animate-shimmer" />
        ))}
      </div>
      <div className="animate-shimmer rounded-xl border bg-card h-[220px] sm:h-[260px]" />
    </div>
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
  const [workingHoursOpen, setWorkingHoursOpen] = useState(false);
  const [exemptUsersOpen, setExemptUsersOpen] = useState(false);

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
      if (tab?.isServiceType) params.set('serviceType', tab.isServiceType);
      if (tab?.excludeInquiry) params.set('excludeInquiry', 'true');
      if (search) params.set('search', search);
      if (serviceFilter !== 'all' && activeTab !== 'inquiry') params.set('serviceType', serviceFilter);
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
    if (preset === 'today') { setDateFrom(fmt(now)); setDateTo(fmt(now)); }
    else if (preset === 'week') { setDateFrom(fmt(new Date(now.getTime() - 7 * 86400000))); setDateTo(fmt(now)); }
    else if (preset === 'month') { setDateFrom(fmt(new Date(now.getTime() - 30 * 86400000))); setDateTo(fmt(now)); }
    setPage(1);
  };

  const clearAllFilters = useCallback(() => {
    setSearch(''); setServiceFilter('all'); setDateFrom(''); setDateTo('');
    setBranchFilter(''); setProvinceFilter('all'); setErrorFilter('all'); setPage(1);
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
        setShowConfetti(true); fetchCases(); fetchStats();
        if (detailOpen) setDetailOpen(false);
      } else { toast.error('خطا در تأیید ارسال'); }
    } catch { toast.error('خطا در ارتباط با سرور'); }
    setConfirmSendCase(null);
  }, [confirmSendCase, detailOpen, fetchCases, fetchStats]);

  const handleDeleteCase = useCallback(async () => {
    if (!deleteCase) return;
    setDeleteOpen(false);
    try {
      const res = await fetch(`/api/admin/cases/${deleteCase.id}`, { method: 'DELETE' });
      if (res.ok) { toast.success(`پرونده ${deleteCase.fullName} حذف شد`); fetchCases(); fetchStats(); }
      else { toast.error('خطا در حذف'); }
    } catch { toast.error('خطا در ارتباط با سرور'); }
    setDeleteCase(null);
  }, [deleteCase, fetchCases, fetchStats]);

  const handleTabChange = (key: string) => { setActiveTab(key); setPage(1); setSearch(''); };

  const handleSort = (field: string) => {
    if (sortBy === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    else { setSortBy(field); setSortOrder('desc'); }
    setPage(1);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  const toggleSelectAll = () => {
    if (cases.every((c) => selectedIds.has(c.id))) setSelectedIds(new Set());
    else setSelectedIds(new Set(cases.map((c) => c.id)));
  };

  const handleViewDetail = async (c: CaseItem) => {
    setDetailCase(c); setDetailOpen(true);
    try {
      const res = await fetch(`/api/admin/cases/${c.id}`);
      if (res.ok) { const data = await res.json(); setDetailCase(data.case || c); setAdminActions(data.adminActions || []); }
    } catch (e) { console.error(e); }
  };

  const handleIntervention = (c: CaseItem) => { setInterventionCase(c); setInterventionOpen(true); };

  const handleInterventionSubmit = async (data: {
    caseId: string; adminNote: string; actionType: string; newStatus: string;
    uploadedFileUrls: string[]; sentViaBot: boolean;
  }) => {
    const res = await fetch(`/api/admin/cases/${data.caseId}/manual-intervention`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.error || 'خطا'); }
    fetchCases(); fetchStats(); fetchActivityCount();
  };

  const handleUserClick = (c: CaseItem) => { setHistoryUser({ baleUserId: c.baleUserId, fullName: c.fullName }); setHistoryOpen(true); };

  const handleExport = async (format: 'csv' | 'excel') => {
    try {
      const tab = TABS.find((t) => t.key === activeTab);
      const params = new URLSearchParams();
      if (tab?.apiParam) params.set('status', tab.apiParam);
      if (activeTab === 'ready') params.set('readyToSend', 'true');
      if (tab?.isServiceType) params.set('serviceType', tab.isServiceType);
      if (tab?.excludeInquiry) params.set('excludeInquiry', 'true');
      if (search) params.set('search', search);
      params.set('limit', '1000');
      const res = await fetch(`/api/admin/cases?${params}`);
      if (res.ok) {
        const data = await res.json();
        const rows = data.cases as CaseItem[];
        if (rows.length === 0) { toast.error('داده‌ای برای خروجی وجود ندارد'); return; }
        const exportRows: ExportRow[] = rows.map((r) => ({
          fullName: r.fullName, baleUserId: r.baleUserId, serviceType: r.serviceType,
          status: r.status, fee: r.fee, feeStatus: r.feeStatus, branchName: r.branchName, createdAt: r.createdAt,
        }));
        const filename = `cases-${activeTab}-${new Date().toISOString().slice(0, 10)}`;
        if (format === 'csv') { exportToCSV(exportRows, filename); toast.success('فایل CSV دانلود شد'); }
        else { exportToExcel(exportRows, filename); toast.success('فایل Excel دانلود شد'); }
      }
    } catch { toast.error('خطا در خروجی گرفتن'); }
  };

  const handlePrint = () => window.print();

  const handleConfirmSendAll = useCallback(async () => {
    setBatchConfirmSending(true);
    try {
      // Fetch ALL ready-to-send case IDs (not just selected ones)
      const params = new URLSearchParams();
      params.set('readyToSend', 'true');
      params.set('limit', '1000');
      const res = await fetch(`/api/admin/cases?${params}`);
      if (!res.ok) { toast.error('خطا در دریافت لیست'); return; }
      const data = await res.json();
      const allIds = (data.cases as CaseItem[]).map((c: CaseItem) => c.id);
      if (allIds.length === 0) { toast.error('موردی برای ارسال وجود ندارد'); return; }

      const batchRes = await fetch('/api/admin/cases/batch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: allIds, action: 'CONFIRM_SEND_ALL' }),
      });
      if (batchRes.ok) {
        const batchData = await batchRes.json();
        toast.success(batchData.message || `${new Intl.NumberFormat('fa-IR').format(allIds.length)} پرونده تأیید و ارسال شد`);
        setBatchConfirmDone(true); setTimeout(() => setBatchConfirmDone(false), 3000);
        setShowConfetti(true); setSelectedIds(new Set());
        fetchCases(); fetchStats(); fetchActivityCount();
      } else { toast.error('خطا در تأیید دسته‌ای'); }
    } catch { toast.error('خطا در ارتباط با سرور'); }
    finally { setBatchConfirmSending(false); }
  }, [fetchCases, fetchStats, fetchActivityCount]);

  const handleBatchConfirmSend = useCallback(async () => {
    if (selectedIds.size === 0) return;
    setBatchConfirmSending(true);
    try {
      const res = await fetch('/api/admin/cases/batch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: Array.from(selectedIds), action: 'CONFIRM_SEND_ALL' }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || `${new Intl.NumberFormat('fa-IR').format(selectedIds.size)} پرونده تأیید و ارسال شد`);
        setBatchConfirmDone(true); setTimeout(() => setBatchConfirmDone(false), 3000);
        setShowConfetti(true); setSelectedIds(new Set());
        fetchCases(); fetchStats(); fetchActivityCount();
      } else { toast.error('خطا در تأیید دسته‌ای'); }
    } catch { toast.error('خطا در ارتباط با سرور'); }
    finally { setBatchConfirmSending(false); }
  }, [selectedIds, fetchCases, fetchStats, fetchActivityCount]);

  const handleSeed = async () => {
    try {
      const res = await fetch('/api/admin/seed', { method: 'POST' });
      if (res.ok) { toast.success('داده‌های آزمایشی ایجاد شد'); fetchStats(); fetchCases(); }
    } catch { toast.error('خطا'); }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.target as HTMLElement).isContentEditable) return;
      if (e.key === 'r' || e.key === 'R') { e.preventDefault(); refreshAll(); }
      if (e.key === '/' || e.key === 's' || e.key === 'S') { e.preventDefault(); searchRef.current?.focus(); }
      if (e.key === 'f' || e.key === 'F') { e.preventDefault(); setShowFilters((v) => !v); }
      const num = parseInt(e.key);
      if (num >= 1 && num <= TABS.length) { e.preventDefault(); handleTabChange(TABS[num - 1].key); }
      if (e.key === 'Escape' && isFullscreen) { document.exitFullscreen().catch(() => {}); }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [refreshAll, isFullscreen]);

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => { entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add('scrolled-into-view'); }); },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    );
    const els = document.querySelectorAll('.scroll-reveal');
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [stats, loading]);

  const currentTab = TABS.find((t) => t.key === activeTab);

  const handleServiceFilterChange = (v: string) => { setServiceFilter(v); setPage(1); };

  return (
    <div className="gradient-mesh-bg grid-pattern-bg min-h-screen flex flex-col bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950 transition-colors duration-300" data-loading={loading ? 'true' : 'false'}>
      <LoadingBar loading={loading} />

      <AdminHeader
        refreshing={refreshing}
        onRefresh={refreshAll}
        autoRefresh={autoRefresh}
        onToggleAutoRefresh={() => setAutoRefresh(!autoRefresh)}
        isMuted={isMuted}
        onToggleMuted={() => setMuted(!isMuted)}
        activityCount={activityCount}
        onOpenActivity={() => setActivityOpen(true)}
        onOpenBotSender={() => setBotSenderOpen(true)}
        onOpenSheetsPanel={() => setSheetsPanelOpen(true)}
        onOpenWorkingHours={() => setWorkingHoursOpen(true)}
        onOpenExemptUsers={() => setExemptUsersOpen(true)}
        isOnline={isOnline}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
        onPrint={handlePrint}
        showShortcuts={showShortcuts}
        onSetShowShortcuts={setShowShortcuts}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      />

      <AlertBar stats={stats} onTabChange={handleTabChange} />

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
                      : tab.key === 'inquiry' ? (stats.serviceBreakdown?.find((s: { serviceType: string }) => s.serviceType === 'INQUIRY')?._count?.id || 0)
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
                      {stats && tab.apiParam && (
                        <Badge className={cn('h-5 min-w-5 px-1.5 text-[10px] font-bold rounded-full text-white', tab.badgeColor, hasNonZeroBadge && 'animate-badge-pulse')}>
                          {tab.key === 'completed' && stats.completed}
                          {tab.key === 'incomplete' && stats.incomplete}
                          {tab.key === 'unpaid' && stats.unpaid}
                          {tab.key === 'failed' && stats.failed}
                        </Badge>
                      )}
                      {stats && tab.key === 'inquiry' && (
                        <Badge className={cn('h-5 min-w-5 px-1.5 text-[10px] font-bold rounded-full text-white bg-blue-500', hasNonZeroBadge && 'animate-badge-pulse')}>
                          {stats.serviceBreakdown?.find((s: { serviceType: string }) => s.serviceType === 'INQUIRY')?._count?.id || 0}
                        </Badge>
                      )}
                      {stats && tab.key === 'ready' && (
                        <Badge className={cn('h-5 min-w-5 px-1.5 text-[10px] font-bold rounded-full text-white bg-sky-500', hasNonZeroBadge && 'animate-badge-pulse')}>
                          {stats.readyToSend}
                        </Badge>
                      )}
                      <kbd className="hidden lg:inline-flex kbd-shortcut">{new Intl.NumberFormat('fa-IR').format(idx + 1)}</kbd>
                    </TabsTrigger>
                  );
                })}
              </TabsList>
            </div>
          </Tabs>

          <div className="flex flex-wrap items-center gap-2">
            <FilterBar
              search={search}
              onSearchChange={handleSearchChange}
              serviceFilter={serviceFilter}
              onServiceFilterChange={handleServiceFilterChange}
              showFilters={showFilters}
              onToggleFilters={() => setShowFilters(!showFilters)}
              searchRef={searchRef}
              searchFocused={searchFocused}
              onSearchFocus={() => setSearchFocused(true)}
              onSearchBlur={() => setSearchFocused(false)}
              onOpenCmdPalette={() => setCmdPaletteOpen(true)}
            />

            <div className="flex items-center gap-1.5 mr-auto">
              {selectedIds.size > 0 && (
                <Button size="sm" className="h-9 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 shadow-sm" onClick={() => setBatchOpen(true)}>
                  <ListChecks className="h-3.5 w-3.5" />
                  {'عملیات دسته‌ای'} ({new Intl.NumberFormat('fa-IR').format(selectedIds.size)})
                </Button>
              )}
              {selectedIds.size > 0 && activeTab === 'ready' && (
                <Button
                  size="sm"
                  className={cn('h-9 gap-1.5 text-xs shadow-sm', batchConfirmDone ? 'bg-emerald-500 hover:bg-emerald-500' : 'bg-sky-600 hover:bg-sky-700')}
                  onClick={handleBatchConfirmSend}
                  disabled={batchConfirmSending}
                >
                  {batchConfirmSending ? <div className="h-3.5 w-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    : batchConfirmDone ? <Check className="h-3.5 w-3.5" /> : <ClipboardCheck className="h-3.5 w-3.5" />}
                  {batchConfirmDone ? 'انجام شد' : `تایید و ارسال (${new Intl.NumberFormat('fa-IR').format(selectedIds.size)})`}
                </Button>
              )}

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-9 gap-1.5 text-xs shadow-sm hover-lift-sm btn-press">
                    <Download className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">{'خروجی'}</span>
                    <ChevronDown className="h-3 w-3 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => handleExport('csv')}><Download className="ml-2 h-4 w-4" />{'خروجی CSV'}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport('excel')}><FileSpreadsheet className="ml-2 h-4 w-4" />{'خروجی Excel'}</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button variant="outline" size="sm" className="h-9 gap-1.5 text-xs shadow-sm btn-press" onClick={() => setShowCharts(!showCharts)}>
                <Activity className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">نمودارها</span>
              </Button>
            </div>
          </div>

          {showFilters && (
            <>
              <div className="glass-panel rounded-2xl flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-end gap-3 p-4 border animate-in slide-in-from-top-2 duration-200">
                <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
                  <label className="text-[11px] font-medium text-muted-foreground">از تاریخ</label>
                  <Input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} className="h-9 w-full sm:w-[160px] text-xs" />
                </div>
                <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '50ms' }}>
                  <label className="text-[11px] font-medium text-muted-foreground">تا تاریخ</label>
                  <Input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} className="h-9 w-full sm:w-[160px] text-xs" />
                </div>
                <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
                  <label className="text-[11px] font-medium text-muted-foreground">دسترسی سریع</label>
                  <div className="flex gap-1">
                    {([['today', 'امروز'], ['week', 'این هفته'], ['month', 'این ماه']] as const).map(([key, label]) => (
                      <Button key={key} variant="outline" size="sm" className="h-9 text-[11px] px-2.5" onClick={() => getDatePreset(key)}>
                        <CalendarDays className="h-3 w-3 ml-1" />{label}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '150ms' }}>
                  <label className="text-[11px] font-medium text-muted-foreground">مرتب‌سازی</label>
                  <Select value={`${sortBy}-${sortOrder}`} onValueChange={(v) => { const [field, order] = v.split('-'); setSortBy(field); setSortOrder(order); setPage(1); }}>
                    <SelectTrigger className="h-9 w-full sm:w-[160px] text-xs"><SelectValue /></SelectTrigger>
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
                  <Button variant="ghost" size="sm" className="h-9 text-xs text-muted-foreground hover:text-foreground animate-fade-in-up" style={{ animationDelay: '200ms' }} onClick={clearAllFilters}>
                    <XCircle className="h-3.5 w-3.5 ml-1" />پاک‌سازی
                  </Button>
                )}
              </div>
              <div className="w-full border-t border-border/50 pt-3 mt-1">
                <button type="button" className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors animate-fade-in-up" style={{ animationDelay: '250ms' }} onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}>
                  <ChevronLeft className={cn('h-3.5 w-3.5 transition-transform duration-200', showAdvancedFilters && '-rotate-90')} />
                  {'فیلتر پیشرفته'}
                </button>
                {showAdvancedFilters && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                    <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-medium text-muted-foreground">{'نام شعبه'}</label>
                        {branchFilter && <button onClick={() => { setBranchFilter(''); setPage(1); }} className="text-[10px] text-muted-foreground hover:text-foreground"><XCircle className="h-3 w-3" /></button>}
                      </div>
                      <Input placeholder={'جستجوی شعبه...'} value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setPage(1); }} className="h-9 text-xs" />
                    </div>
                    <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '350ms' }}>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-medium text-muted-foreground">{'استان'}</label>
                        {provinceFilter !== 'all' && <button onClick={() => { setProvinceFilter('all'); setPage(1); }} className="text-[10px] text-muted-foreground hover:text-foreground"><XCircle className="h-3 w-3" /></button>}
                      </div>
                      <Select value={provinceFilter} onValueChange={(v) => { setProvinceFilter(v); setPage(1); }}>
                        <SelectTrigger className="h-9 w-full text-xs"><SelectValue placeholder={'همه استان‌ها'} /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">{'همه استان‌ها'}</SelectItem>
                          {['تهران', 'اصفهان', 'فارس', 'خراسان رضوی', 'آذربایجان شرقی', 'مازندران', 'گیلان', 'خوزستان', 'هرمزگان'].map((p) => (
                            <SelectItem key={p} value={p}>{p}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5 animate-fade-in-up" style={{ animationDelay: '400ms' }}>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-medium text-muted-foreground">{'فیلتر خطا'}</label>
                        {errorFilter !== 'all' && <button onClick={() => { setErrorFilter('all'); setPage(1); }} className="text-[10px] text-muted-foreground hover:text-foreground"><XCircle className="h-3 w-3" /></button>}
                      </div>
                      <Select value={errorFilter} onValueChange={(v) => { setErrorFilter(v); setPage(1); }}>
                        <SelectTrigger className="h-9 w-full text-xs"><SelectValue /></SelectTrigger>
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

          {(search || serviceFilter !== 'all' || dateFrom || dateTo || branchFilter || provinceFilter !== 'all' || errorFilter !== 'all') && !showFilters && (
            <div className="animate-slide-in-right flex items-center gap-1.5 flex-wrap border-r-2 border-r-primary/30 pr-2">
              <span className="text-[11px] text-muted-foreground">فیلترهای فعال:</span>
              {search && <Badge variant="secondary" className="text-[10px] gap-1">جستجو: {search}<button onClick={() => { setSearch(''); setPage(1); }} className="hover:text-foreground"><XCircle className="h-3 w-3" /></button></Badge>}
              {serviceFilter !== 'all' && <Badge variant="secondary" className="text-[10px] gap-1">{SERVICE_LABELS[serviceFilter] || serviceFilter}<button onClick={() => { setServiceFilter('all'); setPage(1); }} className="hover:text-foreground"><XCircle className="h-3 w-3" /></button></Badge>}
              {branchFilter && <Badge variant="secondary" className="text-[10px] gap-1">{'شعبه: '}{branchFilter}<button onClick={() => { setBranchFilter(''); setPage(1); }} className="hover:text-foreground"><XCircle className="h-3 w-3" /></button></Badge>}
              {provinceFilter !== 'all' && <Badge variant="secondary" className="text-[10px] gap-1">{provinceFilter}<button onClick={() => { setProvinceFilter('all'); setPage(1); }} className="hover:text-foreground"><XCircle className="h-3 w-3" /></button></Badge>}
              {errorFilter !== 'all' && <Badge variant="secondary" className="text-[10px] gap-1">{errorFilter === 'hasError' ? 'خطادار' : errorFilter}<button onClick={() => { setErrorFilter('all'); setPage(1); }} className="hover:text-foreground"><XCircle className="h-3 w-3" /></button></Badge>}
            </div>
          )}
        </div>

        {activeTab === 'ready' && stats && stats.readyToSend > 0 && (
          <div className="scroll-reveal">
            <div className="rounded-xl bg-gradient-to-l from-sky-50 via-white to-sky-50 dark:from-sky-950/20 dark:via-gray-900 dark:to-sky-950/20 border border-sky-200 dark:border-sky-800 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-sky-100 dark:bg-sky-900/30 flex items-center justify-center shrink-0"><ClipboardCheck className="h-5 w-5 text-sky-600" /></div>
                <div>
                  <p className="text-sm font-bold text-sky-700 dark:text-sky-300">{new Intl.NumberFormat('fa-IR').format(stats.readyToSend)} {'پرونده برای ارسال آماده است'}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{'آیتم‌های مورد نظر را انتخاب کنید یا همه را یکجا ارسال کنید'}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  className="h-10 gap-2 text-xs shadow-md bg-gradient-to-l from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white"
                  onClick={handleConfirmSendAll}
                  disabled={batchConfirmSending}
                >
                  {batchConfirmSending ? <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Send className="h-4 w-4" />}
                  {'تایید و ارسال همه'}
                </Button>
                {selectedIds.size > 0 && (
                  <>
                    <span className="text-xs font-medium text-sky-600 dark:text-sky-400">{new Intl.NumberFormat('fa-IR').format(selectedIds.size)} {'انتخاب شده'}</span>
                    <Button size="sm" className={cn('h-10 gap-2 text-xs shadow-md', batchConfirmDone ? 'bg-emerald-500' : 'bg-sky-600 hover:bg-sky-700')} onClick={handleBatchConfirmSend} disabled={batchConfirmSending}>
                      {batchConfirmSending ? <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : batchConfirmDone ? <Check className="h-4 w-4" /> : <Send className="h-4 w-4" />}
                      {batchConfirmDone ? 'انجام شد!' : 'تایید انتخاب‌شده‌ها'}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="scroll-reveal">
          <CasesTable
            cases={cases} loading={loading} pagination={pagination}
            onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
            onSort={handleSort} sortBy={sortBy} sortOrder={sortOrder}
            onViewDetail={handleViewDetail} onRowClick={handleViewDetail}
            onClearFilters={clearAllFilters}
            onConfirmSend={requestConfirmSend}
            onManualIntervention={handleIntervention}
            onDeleteCase={(c) => { setDeleteCase(c); setDeleteOpen(true); }}
            showConfirmButton={currentTab?.showConfirm}
            showInterventionButton={currentTab?.showIntervention}
            selectedIds={selectedIds} onToggleSelect={toggleSelect} onToggleSelectAll={toggleSelectAll}
            onUserClick={handleUserClick}
            onRefresh={() => { fetchCases(); fetchStats(); }}
          />
        </div>

        <div className="flex items-center justify-center gap-4 text-[10px] text-muted-foreground/60 pb-2">
          <span className="flex items-center gap-1"><kbd className="kbd-shortcut">R</kbd>بروزرسانی</span>
          <span className="flex items-center gap-1"><kbd className="kbd-shortcut">/</kbd>جستجو</span>
          <span className="flex items-center gap-1"><kbd className="kbd-shortcut">F</kbd>فیلتر</span>
          <span className="flex items-center gap-1"><kbd className="kbd-shortcut">1-8</kbd>تب‌ها</span>
        </div>
      </main>

      <footer className="glass-v2 mt-auto">
        <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] text-muted-foreground hidden sm:block">
              پنل مدیریت خدمات قضایی آنلاین —{' '}
              <span className="bg-gradient-to-l from-emerald-600 to-teal-500 bg-clip-text text-transparent font-bold">نسخه ۸.۰</span>
            </p>
            <div className="hidden sm:block w-px h-4 bg-border" />
            {stats && (
              <div className="hide-on-tiny flex items-center gap-3 text-[10px] text-muted-foreground mx-auto">
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /><span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.completed)}</span> تکمیل</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500" /><span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.incomplete)}</span> ناقص</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /><span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.failed)}</span> شکست</span>
                <span className="text-muted-foreground/50">|</span>
                <span>درآمد: <span className="nums-align">{new Intl.NumberFormat('fa-IR').format(stats.totalRevenue)}</span> ت</span>
              </div>
            )}
            <div className="hidden sm:block w-px h-4 bg-border" />
            <div className="flex items-center gap-1.5">
              <Button variant="ghost" size="sm" className="h-7 text-[10px] text-muted-foreground hover-glow-emerald" onClick={handleSeed}>
                <Zap className="h-3 w-3 ml-1" /><span className="hidden sm:inline">داده آزمایشی</span>
              </Button>
            </div>
          </div>
        </div>
      </footer>

      <LazyPanels
        detailCase={detailCase} detailOpen={detailOpen} onDetailClose={() => setDetailOpen(false)}
        onManualIntervention={handleIntervention} onConfirmSend={requestConfirmSend}
        onDeleteCase={(c) => { setDeleteCase(c); setDeleteOpen(true); setDetailOpen(false); }}
        adminActions={adminActions}
        interventionCase={interventionCase} interventionOpen={interventionOpen}
        onInterventionClose={() => setInterventionOpen(false)} onInterventionSubmit={handleInterventionSubmit}
        batchOpen={batchOpen} onBatchClose={() => setBatchOpen(false)}
        selectedIds={Array.from(selectedIds)} onBatchDone={() => { fetchCases(); fetchStats(); setSelectedIds(new Set()); fetchActivityCount(); }}
        activityOpen={activityOpen} onActivityClose={() => setActivityOpen(false)}
        historyOpen={historyOpen} onHistoryClose={() => setHistoryOpen(false)} historyUser={historyUser}
        botSenderOpen={botSenderOpen} onBotSenderClose={() => setBotSenderOpen(false)} onBotSenderRefresh={() => { fetchStats(); fetchCases(); }}
        sheetsPanelOpen={sheetsPanelOpen} onSheetsPanelClose={() => setSheetsPanelOpen(false)}
        workingHoursOpen={workingHoursOpen} onWorkingHoursClose={() => setWorkingHoursOpen(false)}
        exemptUsersOpen={exemptUsersOpen} onExemptUsersClose={() => setExemptUsersOpen(false)}
      />

      <PageDialogs
        confirmSendOpen={confirmSendOpen} onConfirmSendOpenChange={setConfirmSendOpen}
        confirmSendCase={confirmSendCase} onConfirmSend={executeConfirmSend}
        deleteOpen={deleteOpen} onDeleteOpenChange={setDeleteOpen}
        deleteCase={deleteCase} onDelete={handleDeleteCase}
        showShortcuts={showShortcuts} onShortcutsOpenChange={setShowShortcuts}
        shortcuts={SHORTCUTS}
      />

      <ConfettiAnimation active={showConfetti} onComplete={() => setShowConfetti(false)} />

      <CommandPalette open={cmdPaletteOpen} onOpenChange={setCmdPaletteOpen} actions={[
        { id: 'refresh', label: 'بروزرسانی', icon: Search, shortcut: 'R', group: 'عملیات', onSelect: refreshAll },
        { id: 'search', label: 'جستجو', icon: Search, shortcut: '/ S', group: 'عملیات', onSelect: () => searchRef.current?.focus() },
        { id: 'filter', label: 'فیلترها', icon: Filter, shortcut: 'F', group: 'عملیات', onSelect: () => setShowFilters(true) },
        { id: 'export-csv', label: 'خروجی CSV', icon: FileSpreadsheet, group: 'خروجی', onSelect: () => handleExport('csv') },
        { id: 'export-excel', label: 'خروجی Excel', icon: FileSpreadsheet, group: 'خروجی', onSelect: () => handleExport('excel') },
        { id: 'print', label: 'چاپ', icon: Printer, group: 'خروجی', onSelect: handlePrint },
        { id: 'tab-all', label: 'همه پرونده‌ها', icon: LayoutDashboard, shortcut: '1', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('all') },
        { id: 'tab-inquiry', label: 'استعلامات', icon: Search, shortcut: '2', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('inquiry') },
        { id: 'tab-completed', label: 'ثبت شده', icon: FileCheck2, shortcut: '3', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('completed') },
        { id: 'tab-incomplete', label: 'ناقص', icon: FileWarning, shortcut: '4', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('incomplete') },
        { id: 'tab-unpaid', label: 'پرداخت نشده', icon: CreditCard, shortcut: '5', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('unpaid') },
        { id: 'tab-ready', label: 'آماده ارسال', icon: Send, shortcut: '6', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('ready') },
        { id: 'tab-failed', label: 'شکست خورده', icon: AlertTriangle, shortcut: '7', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('failed') },
        { id: 'tab-cancelled', label: 'لغو شده', icon: XCircle, shortcut: '8', group: 'تب‌های داشبورد', onSelect: () => handleTabChange('cancelled') },
        { id: 'toggle-charts', label: stats && showCharts ? 'مخفی کردن نمودارها' : 'نمایش نمودارها', icon: ListChecks, group: 'تنظیمات', onSelect: () => setShowCharts(v => !v) },
        { id: 'toggle-theme', label: theme === 'dark' ? 'حالت روشن' : 'حالت تاریک', icon: theme === 'dark' ? Sun : Moon, group: 'تنظیمات', onSelect: () => setTheme(theme === 'dark' ? 'light' : 'dark') },
        { id: 'activity', label: 'تاریخچه فعالیت‌ها', icon: Activity, group: 'تنظیمات', onSelect: () => setActivityOpen(true) },
        { id: 'shortcuts', label: 'میانبر کلیدی', icon: Keyboard, group: 'تنظیمات', onSelect: () => setShowShortcuts(true) },
        { id: 'bot-sender', label: 'ارسال پیام به کاربر', icon: MessageSquare, group: 'تنظیمات', onSelect: () => setBotSenderOpen(true) },
        { id: 'google-sheets', label: 'همگام‌سازی گوگل شیت', icon: FileSpreadsheet, group: 'تنظیمات', onSelect: () => setSheetsPanelOpen(true) },
        { id: 'working-hours', label: 'ساعات کاری', icon: Clock, group: 'تنظیمات', onSelect: () => setWorkingHoursOpen(true) },
        { id: 'exempt-users', label: 'کاربران معاف', icon: Users, group: 'تنظیمات', onSelect: () => setExemptUsersOpen(true) },
      ] as CommandAction[]} />

      {showBackToTop && (
        <button onClick={scrollToTop} className="fixed bottom-20 left-5 z-40 h-10 w-10 rounded-full bg-gradient-to-br from-primary to-primary/80 text-primary-foreground back-to-top-btn hover:scale-110 active:scale-95 flex items-center justify-center animate-slide-up-fade-in print:hidden" title="بازگشت به بالا">
          <ArrowUp className="h-4 w-4" />
        </button>
      )}

      <MobileNav tabs={TABS} activeTab={activeTab} onTabChange={handleTabChange} />
    </div>
  );
}
