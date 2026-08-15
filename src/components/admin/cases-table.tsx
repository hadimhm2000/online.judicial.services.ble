'use client';

import React, { useState, useCallback, useEffect } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Eye,
  EyeOff,
  MoreHorizontal,
  Send,
  CheckCircle2,
  AlertCircle,
  Clock,
  FileText,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  SearchX,
  FilterX,
  Trash2,
  Loader2,
  Wrench,
  PenLine,
  XCircle,
} from 'lucide-react';
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { cn } from '@/lib/utils';

export interface CaseItem {
  id: string;
  baleUserId: string;
  fullName: string;
  serviceType: string;
  status: string;
  trackingCode: string | null;
  documentCategory: string | null;
  branchName: string | null;
  branchCode: string | null;
  province: string | null;
  fee: number;
  feeStatus: string;
  isInReadyToSend: boolean;
  hasSignature: boolean;
  errorDetails: string | null;
  errorStep: string | null;
  lastCompletedStep: string | null;
  createdAt: string;
  sentToUserAt: string | null;
  readyToSendAt: string | null;
  sentViaBot: boolean;
  resultSummary: string | null;
  title: string | null;
  textContent: string | null;
  persons: string | null;
  rowNumber: string | null;
}

type ColumnKey = 'name' | 'serviceType' | 'status' | 'fee' | 'feeStatus' | 'branch' | 'date' | 'trackingCode' | 'signature' | 'actions';

const COLUMN_LABELS: Record<ColumnKey, string> = {
  name: 'نام کاربر',
  serviceType: 'نوع خدمت',
  status: 'وضعیت',
  fee: 'هزینه',
  feeStatus: 'وضعیت پرداخت',
  branch: 'شعبه / استان',
  date: 'تاریخ',
  trackingCode: 'کد پیگیری',
  signature: 'امضا',
  actions: 'عملیات',
};

const DEFAULT_COLUMN_VISIBILITY: Record<ColumnKey, boolean> = {
  name: true,
  serviceType: true,
  status: true,
  fee: true,
  feeStatus: true,
  branch: true,
  date: true,
  trackingCode: true,
  signature: true,
  actions: true,
};

const COLUMN_STORAGE_KEY = 'cases-table-column-visibility';

function isMobileWidth(): boolean {
  if (typeof window === 'undefined') return false;
  return window.innerWidth < 768;
}

function loadColumnVisibility(): Record<ColumnKey, boolean> {
  if (typeof window === 'undefined') return { ...DEFAULT_COLUMN_VISIBILITY };
  try {
    const stored = localStorage.getItem(COLUMN_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<Record<ColumnKey, boolean>>;
      return { ...DEFAULT_COLUMN_VISIBILITY, ...parsed };
    }
  } catch {
    // ignore parse errors
  }
  // On mobile, hide branch column by default for better space usage
  const defaults = { ...DEFAULT_COLUMN_VISIBILITY };
  if (isMobileWidth()) {
    defaults.branch = false;
    defaults.signature = false;
    defaults.trackingCode = false;
  }
  return defaults;
}

function saveColumnVisibility(visibility: Record<ColumnKey, boolean>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibility));
  } catch {
    // ignore storage errors
  }
}

interface CasesTableProps {
  cases: CaseItem[];
  loading?: boolean;
  pagination?: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  onSort: (field: string) => void;
  sortBy?: string;
  sortOrder?: string;
  onViewDetail: (caseItem: CaseItem) => void;
  onRowClick?: (caseItem: CaseItem) => void;
  onClearFilters?: () => void;
  onConfirmSend?: (caseItem: CaseItem) => void;
  onManualIntervention?: (caseItem: CaseItem) => void;
  showConfirmButton?: boolean;
  showInterventionButton?: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: () => void;
  onUserClick?: (caseItem: CaseItem) => void;
  onDeleteCase?: (caseItem: CaseItem) => void;
  onRefresh?: () => void;
}

const serviceTypeLabels: Record<string, string> = {
  INQUIRY: 'استعلام',
  LAVAYEH: 'ثبت لایحه',
  EZHHARNAMEH: 'اظهارنامه',
  EALAM_VAKALAHT: 'اعلام وکالت',
  STAMP_CALC: 'محاسبه تمبر',
};

const serviceTypeColors: Record<string, string> = {
  INQUIRY: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  LAVAYEH: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  EZHHARNAMEH: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300',
  EALAM_VAKALAHT: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  STAMP_CALC: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
};

const statusLabels: Record<string, string> = {
  COMPLETED: 'تکمیل شده',
  INCOMPLETE: 'ناقص',
  PENDING_PAYMENT: 'پرداخت نشده',
  PROCESSING: 'در حال پردازش',
  READY_TO_SEND: 'آماده ارسال',
  FAILED: 'شکست خورده',
  CANCELLED: 'لغو شده',
};

const statusColors: Record<string, string> = {
  COMPLETED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  INCOMPLETE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  PENDING_PAYMENT: 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300',
  PROCESSING: 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300',
  READY_TO_SEND: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  FAILED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  CANCELLED: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
};

const statusLeftBorderColors: Record<string, string> = {
  COMPLETED: 'border-l-emerald-400',
  INCOMPLETE: 'border-l-amber-400',
  PENDING_PAYMENT: 'border-l-rose-400',
  PROCESSING: 'border-l-sky-400',
  READY_TO_SEND: 'border-l-indigo-400',
  FAILED: 'border-l-red-400',
  CANCELLED: 'border-l-gray-400',
};

const feeStatusLabels: Record<string, string> = {
  PAID: 'پرداخت شده',
  UNPAID: 'پرداخت نشده',
  MANUAL_APPROVED: 'تأیید دستی',
};

const feeStatusColors: Record<string, string> = {
  PAID: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  UNPAID: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
  MANUAL_APPROVED: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
};

const stepLabels: Record<string, string> = {
  PERSON_INFO: 'اطلاعات اشخاص',
  TEXT_CONTENT: 'محتوای متن',
  ATTACHMENTS: 'فایل‌ها و پیوست‌ها',
  PREVIEW: 'پیش‌نمایش',
  PAYMENT: 'پرداخت',
  SIGNATURE: 'امضای الکترونیک',
  BROWSER_AUTOMATION: 'اتوماسیون مرورگر',
  SESSION_EXPIRED: 'انقضای نشست',
  UPLOAD_FAILED: 'خطا در آپلود',
  SUBMIT_FAILED: 'خطا در ثبت',
  SIGN_CODE_TIMEOUT: 'انقضای کد امضا',
  PAYMENT_VERIFICATION_FAILED: 'خطا در تأیید پرداخت',
  NETWORK_ERROR: 'خطای شبکه',
};

const pageSizeOptions = [10, 15, 25, 50] as const;

function formatToman(n: number): string {
  return `${new Intl.NumberFormat('fa-IR').format(n)} تومان`;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return new Intl.DateTimeFormat('fa-IR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'لحظاتی پیش';
  if (minutes < 60) return `${new Intl.NumberFormat('fa-IR').format(minutes)} دقیقه پیش`;
  if (hours < 24) return `${new Intl.NumberFormat('fa-IR').format(hours)} ساعت پیش`;
  return `${new Intl.NumberFormat('fa-IR').format(days)} روز پیش`;
}

function EmptyStateIllustration() {
  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      fill="none"
      aria-hidden="true"
      className="opacity-30"
    >
      <rect x="20" y="30" width="80" height="60" rx="8" className="fill-muted-foreground/20" />
      <rect x="26" y="36" width="50" height="6" rx="3" className="fill-muted-foreground/15" />
      <rect x="26" y="48" width="68" height="4" rx="2" className="fill-muted-foreground/10" />
      <rect x="26" y="56" width="55" height="4" rx="2" className="fill-muted-foreground/10" />
      <rect x="26" y="64" width="40" height="4" rx="2" className="fill-muted-foreground/10" />
      <rect x="26" y="76" width="30" height="8" rx="4" className="fill-muted-foreground/15" />
      <circle cx="90" cy="78" r="5" className="fill-muted-foreground/10" />
      <rect x="30" y="24" width="60" height="50" rx="6" className="fill-muted-foreground/10" />
      <circle cx="98" cy="28" r="18" className="fill-muted-foreground/8" />
      <circle cx="18" cy="90" r="12" className="fill-muted-foreground/8" />
    </svg>
  );
}

function ShimmerRow({ index }: { index: number }) {
  const widths = [
    { name: 'w-28', service: 'w-16', status: 'w-14', fee: 'w-14', branch: 'w-20', feeStatus: 'w-16', date: 'w-24', action: 'w-8' },
    { name: 'w-36', service: 'w-20', status: 'w-16', fee: 'w-12', branch: 'w-28', feeStatus: 'w-14', date: 'w-20', action: 'w-8' },
    { name: 'w-32', service: 'w-14', status: 'w-20', fee: 'w-16', branch: 'w-24', feeStatus: 'w-20', date: 'w-28', action: 'w-8' },
    { name: 'w-24', service: 'w-24', status: 'w-12', fee: 'w-20', branch: 'w-16', feeStatus: 'w-12', date: 'w-16', action: 'w-8' },
    { name: 'w-40', service: 'w-16', status: 'w-16', fee: 'w-14', branch: 'w-32', feeStatus: 'w-18', date: 'w-20', action: 'w-8' },
    { name: 'w-20', service: 'w-20', status: 'w-14', fee: 'w-18', branch: 'w-20', feeStatus: 'w-16', date: 'w-24', action: 'w-8' },
    { name: 'w-32', service: 'w-14', status: 'w-20', fee: 'w-16', branch: 'w-24', feeStatus: 'w-14', date: 'w-18', action: 'w-8' },
    { name: 'w-28', service: 'w-18', status: 'w-16', fee: 'w-12', branch: 'w-28', feeStatus: 'w-20', date: 'w-22', action: 'w-8' },
  ];
  const w = widths[index % widths.length];
  return (
    <div className="flex items-center gap-3 px-4 py-2.5" style={{ animationDelay: `${index * 60}ms` }}>
      <div className="animate-shimmer h-4 w-4 rounded shrink-0" style={{ animationDelay: `${index * 60}ms` }} />
      <div className="flex-1 flex items-center gap-3 overflow-hidden">
        <div className={cn('animate-shimmer h-4 rounded shrink-0', w.name)} style={{ animationDelay: `${index * 60}ms` }} />
        <div className={cn('animate-shimmer h-5 rounded shrink-0', w.service)} style={{ animationDelay: `${index * 60 + 40}ms` }} />
        <div className={cn('animate-shimmer h-5 rounded shrink-0', w.status)} style={{ animationDelay: `${index * 60 + 80}ms` }} />
        <div className={cn('animate-shimmer h-5 rounded shrink-0', w.fee)} style={{ animationDelay: `${index * 60 + 50}ms` }} />
        <div className={cn('hidden md:block animate-shimmer h-4 rounded shrink-0', w.branch)} style={{ animationDelay: `${index * 60 + 70}ms` }} />
        <div className={cn('animate-shimmer h-4 rounded shrink-0', w.feeStatus)} style={{ animationDelay: `${index * 60 + 90}ms` }} />
        <div className={cn('hidden lg:block animate-shimmer h-4 rounded shrink-0', w.date)} style={{ animationDelay: `${index * 60 + 30}ms` }} />
        <div className={cn('animate-shimmer h-4 rounded shrink-0 ml-auto', w.action)} style={{ animationDelay: `${index * 60 + 60}ms` }} />
      </div>
    </div>
  );
}

const CasesTableMemo = React.memo(function CasesTable({
  cases,
  loading = false,
  pagination,
  onPageChange,
  onPageSizeChange,
  onSort,
  sortBy = 'createdAt',
  sortOrder = 'desc',
  onViewDetail,
  onRowClick,
  onClearFilters,
  onConfirmSend,
  onManualIntervention,
  showConfirmButton = false,
  showInterventionButton = false,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onUserClick,
  onDeleteCase,
  onRefresh,
}: CasesTableProps) {
  const allSelected = cases.length > 0 && cases.every((c) => selectedIds.has(c.id));
  const [goToPageValue, setGoToPageValue] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<ColumnKey, boolean>>(DEFAULT_COLUMN_VISIBILITY);
  const [statusUpdating, setStatusUpdating] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const rowClickHandler = onRowClick ?? onViewDetail;

  const visibleColumns = (Object.keys(columnVisibility) as ColumnKey[]).filter((k) => columnVisibility[k]);
  const totalColSpan = 1 + 1 + visibleColumns.length + (showConfirmButton ? 1 : 0);

  const toggleColumn = useCallback((key: ColumnKey) => {
    setColumnVisibility((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      saveColumnVisibility(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const loaded = loadColumnVisibility();
    setColumnVisibility(loaded);
  }, []);

  const handleStatusChange = useCallback(async (caseId: string, newStatus: string) => {
    setStatusUpdating(caseId);
    try {
      const res = await fetch(`/api/admin/cases/${caseId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error('Failed to update status');
      onRefresh?.();
    } catch {
      // keep current state on error
    } finally {
      setStatusUpdating(null);
    }
  }, [onRefresh]);

  const handleGoToPage = useCallback(() => {
    if (!pagination) return;
    const num = parseInt(goToPageValue, 10);
    if (!isNaN(num) && num >= 1 && num <= pagination.totalPages) {
      setGoToPageValue('');
      onPageChange(num);
    }
  }, [pagination, goToPageValue, onPageChange]);

  if (loading) {
    return (
      <div className="rounded-xl border bg-card overflow-hidden shadow-sm shadow-black/5 dark:shadow-black/20">
        <div className="px-4 py-3 border-b border-border/50">
          <div className="animate-shimmer h-4 w-36 rounded" />
        </div>
        <div className="space-y-0">
          {Array.from({ length: 8 }).map((_, i) => (
            <ShimmerRow key={i} index={i} />
          ))}
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-t border-border/50">
          <div className="animate-shimmer h-3 w-40 rounded" />
          <div className="flex gap-1">
            <div className="animate-shimmer h-8 w-8 rounded" />
            <div className="animate-shimmer h-8 w-8 rounded" />
            <div className="animate-shimmer h-8 w-8 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (!cases || cases.length === 0) {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 overflow-hidden">
        <div className="flex flex-col items-center justify-center py-16 sm:py-24 text-muted-foreground">
          <EmptyStateIllustration />
          <div className="mt-6 text-center">
            <h3 className="text-lg font-bold text-foreground/80">
              {'پرونده‌ای یافت نشد'}
            </h3>
            <p className="text-sm mt-2 text-muted-foreground/70 max-w-sm">
              {'فیلترهای جستجو را تغییر دهید یا پرونده جدیدی ثبت کنید'}
            </p>
          </div>
          {onClearFilters && (
            <Button
              variant="outline"
              size="sm"
              className="mt-5 gap-2 text-xs"
              onClick={onClearFilters}
            >
              <FilterX className="h-3.5 w-3.5" />
              {'پاک کردن فیلترها'}
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="rounded-xl border bg-card overflow-hidden shadow-sm shadow-black/5 dark:shadow-black/20">
        <div className="flex items-center justify-between px-4 py-2 bg-gradient-to-l from-muted/30 to-muted/10 dark:from-gray-800/40 dark:to-gray-800/20">
          <div className="flex items-center gap-2">
            {pagination && (
              <Badge variant="secondary" className="text-[11px] font-normal px-2.5 py-0.5">
                <SearchX className="h-3 w-3 ml-1 opacity-50" />
                {new Intl.NumberFormat('fa-IR').format(pagination.total)} {'مورد'}
              </Badge>
            )}
          </div>
          {/* Desktop: Popover for column visibility */}
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 px-2 text-muted-foreground hover:text-foreground hidden sm:inline-flex" title={'نمایش / پنهان ستون‌ها'}>
                <EyeOff className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-56 p-3">
              <p className="text-xs font-semibold mb-2.5 text-foreground/80">
                {'ستون‌های جدول'}
              </p>
              <div className="space-y-1.5">
                {(Object.keys(COLUMN_LABELS) as ColumnKey[]).map((key) => (
                  <label
                    key={key}
                    className="flex items-center gap-2.5 py-1 px-1.5 rounded-md hover:bg-muted/60 cursor-pointer transition-colors"
                  >
                    <Checkbox
                      checked={columnVisibility[key]}
                      onCheckedChange={() => toggleColumn(key)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="text-xs">{COLUMN_LABELS[key]}</span>
                  </label>
                ))}
              </div>
            </PopoverContent>
          </Popover>
          {/* Mobile: Sheet (slide-up panel) for column visibility */}
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 px-2 text-muted-foreground hover:text-foreground sm:hidden" title={'نمایش / پنهان ستون‌ها'}>
                <EyeOff className="h-4 w-4" />
              </Button>
            </SheetTrigger>
            <SheetContent side="bottom" className="max-h-[70vh] overflow-y-auto" dir="rtl">
              <SheetHeader>
                <SheetTitle>{'نمایش / پنهان ستون‌ها'}</SheetTitle>
                <SheetDescription>{'ستون‌های مورد نظر را انتخاب کنید'}</SheetDescription>
              </SheetHeader>
              <div className="space-y-1 mt-4">
                {(Object.keys(COLUMN_LABELS) as ColumnKey[]).map((key) => (
                  <label
                    key={key}
                    className="flex items-center gap-3 py-3 px-3 rounded-lg hover:bg-muted/60 cursor-pointer transition-colors min-h-[44px]"
                  >
                    <Checkbox
                      checked={columnVisibility[key]}
                      onCheckedChange={() => toggleColumn(key)}
                    />
                    <span className="text-sm">{COLUMN_LABELS[key]}</span>
                  </label>
                ))}
              </div>
            </SheetContent>
          </Sheet>
        </div>
        <div className="overflow-x-auto mobile-scroll-shadow">
          <Table>
            <TableHeader className="table-header-premium">
              <TableRow className="bg-gradient-to-l from-muted/40 to-muted/20 hover:from-muted/40 hover:to-muted/20 dark:from-gray-800/60 dark:to-gray-800/30 border-b-0 relative">
                <TableHead className="w-8 px-1" />
                <TableHead className="w-8 sm:w-10 px-2 sm:px-3">
                  <Checkbox
                    checked={allSelected}
                    onCheckedChange={onToggleSelectAll}
                    aria-label="انتخاب همه"
                  />
                </TableHead>
                {columnVisibility.name && (
                  <TableHead className="px-3 py-3 text-xs font-semibold">
                    <button
                      onClick={() => onSort('fullName')}
                      className="flex items-center gap-1 hover:text-foreground transition-colors"
                    >
                      {'نام کاربر'}
                      <ArrowUpDown className="h-3 w-3 opacity-50" />
                    </button>
                  </TableHead>
                )}
                {columnVisibility.serviceType && (
                  <TableHead className="px-3 py-3 text-xs font-semibold">
                    <button
                      onClick={() => onSort('serviceType')}
                      className="flex items-center gap-1 hover:text-foreground transition-colors"
                    >
                      {'نوع خدمت'}
                      <ArrowUpDown className="h-3 w-3 opacity-50" />
                    </button>
                  </TableHead>
                )}
                {columnVisibility.trackingCode && (
                  <TableHead className="px-3 py-3 text-xs font-semibold hidden xl:table-cell">
                    {'کد پیگیری'}
                  </TableHead>
                )}
                {columnVisibility.status && (
                  <TableHead className="px-3 py-3 text-xs font-semibold">{'وضعیت'}</TableHead>
                )}
                {columnVisibility.feeStatus && (
                  <TableHead className="px-3 py-3 text-xs font-semibold">{'وضعیت پرداخت'}</TableHead>
                )}
                {columnVisibility.branch && (
                  <TableHead className="px-3 py-3 text-xs font-semibold hidden md:table-cell">{'شعبه / استان'}</TableHead>
                )}
                {columnVisibility.fee && (
                  <TableHead className="px-3 py-3 text-xs font-semibold">
                    <button
                      onClick={() => onSort('fee')}
                      className="flex items-center gap-1 hover:text-foreground transition-colors"
                    >
                      {'هزینه'}
                      <ArrowUpDown className="h-3 w-3 opacity-50" />
                    </button>
                  </TableHead>
                )}
                {columnVisibility.date && (
                  <TableHead className="px-3 py-3 text-xs font-semibold hidden lg:table-cell">
                    <button
                      onClick={() => onSort('createdAt')}
                      className="flex items-center gap-1 hover:text-foreground transition-colors"
                    >
                      {'تاریخ'}
                      <ArrowUpDown className="h-3 w-3 opacity-50" />
                    </button>
                  </TableHead>
                )}
                {columnVisibility.signature && (
                  <TableHead className="px-3 py-3 text-xs font-semibold text-center">
                    {'امضا'}
                  </TableHead>
                )}
                {showConfirmButton && (
                  <TableHead className="px-3 py-3 text-xs font-semibold text-center">
                    {'تأیید ارسال'}
                  </TableHead>
                )}
                {columnVisibility.actions && (
                  <TableHead className="px-3 py-3 text-xs font-semibold text-center w-16">
                    {'عملیات'}
                  </TableHead>
                )}
              </TableRow>
              <tr className="h-[1px]">
                <td colSpan={20} className="p-0">
                  <div className="h-[1px] bg-gradient-to-l from-transparent via-border to-transparent" />
                </td>
              </tr>
            </TableHeader>
            <TableBody>
              {cases.map((c, idx) => (
                <React.Fragment key={c.id}>
                <TableRow
                  data-status={c.status}
                  className={cn(
                    'table-row-premium table-row-enter',
                    selectedIds.has(c.id) && 'bg-primary/5 ring-1 ring-primary/20',
                    c.status === 'FAILED' && 'bg-red-50/30 dark:bg-red-950/10',
                    c.status === 'INCOMPLETE' && 'border-r-4 border-r-amber-400',
                    c.isInReadyToSend && 'bg-sky-50/40 dark:bg-sky-950/10 border-r-4 border-r-sky-400'
                  )}
                  style={{ animationDelay: `${idx * 30}ms` }}
                  onClick={() => rowClickHandler(c)}
                >
                  <TableCell className="px-1 w-8" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn-micro p-1 rounded-md hover:bg-muted/80 transition-colors"
                      onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                      aria-label={expandedId === c.id ? 'بستن' : 'باز کردن'}
                      aria-expanded={expandedId === c.id}
                    >
                      <ChevronDown className={cn(
                        'h-3.5 w-3.5 text-muted-foreground transition-transform duration-200',
                        expandedId === c.id && 'rotate-180'
                      )} />
                    </button>
                  </TableCell>
                  <TableCell className="px-2 sm:px-3" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(c.id)}
                      onCheckedChange={() => onToggleSelect(c.id)}
                      aria-label={`انتخاب ${c.fullName}`}
                    />
                  </TableCell>
                  {columnVisibility.name && (
                    <TableCell className="px-3 py-3">
                      <div>
                        <p className="font-medium text-sm hover:text-primary transition-colors" onClick={(e) => { e.stopPropagation(); onUserClick?.(c); }}>{c.fullName}</p>
                        <p className="text-[11px] text-blue-600 dark:text-blue-400 font-mono font-medium" dir="ltr" onClick={(e) => { e.stopPropagation(); onUserClick?.(c); }}>
                          ID: {c.baleUserId}
                        </p>
                      </div>
                    </TableCell>
                  )}
                  {columnVisibility.serviceType && (
                    <TableCell className="px-3 py-3">
                      <Badge
                        variant="secondary"
                        className={cn('text-[11px] font-medium', serviceTypeColors[c.serviceType])}
                      >
                        {serviceTypeLabels[c.serviceType] || c.serviceType}
                      </Badge>
                    </TableCell>
                  )}
                  {columnVisibility.trackingCode && (
                    <TableCell className="px-3 py-3 hidden xl:table-cell" onClick={(e) => e.stopPropagation()}>
                      <p className="text-[11px] text-muted-foreground font-mono" dir="ltr">
                        {c.trackingCode || '—'}
                      </p>
                    </TableCell>
                  )}
                  {columnVisibility.status && (
                    <TableCell className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                      {statusUpdating === c.id ? (
                        <div className="flex items-center justify-center">
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        </div>
                      ) : (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button className="cursor-pointer focus-visible:outline-none">
                              <Badge
                                variant="secondary"
                                data-status={c.status}
                                className={cn(
                                  'badge-status text-[11px] font-medium transition-opacity hover:opacity-80',
                                  statusColors[c.status]
                                )}
                              >
                                {c.isInReadyToSend ? 'آماده ارسال' : statusLabels[c.status] || c.status}
                              </Badge>
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="start" className="w-44">
                            {(Object.keys(statusLabels) as Array<keyof typeof statusLabels>).map((key) => (
                              <DropdownMenuItem
                                key={key}
                                onClick={() => handleStatusChange(c.id, key)}
                                disabled={key === c.status}
                                className={cn(
                                  'text-xs gap-2',
                                  key === c.status && 'font-semibold'
                                )}
                              >
                                <span className={cn('h-2 w-2 rounded-full shrink-0', statusColors[key]?.split(' ')[0])} />
                                {statusLabels[key]}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                      {c.status === 'FAILED' && c.errorStep && (
                        <div className="flex items-center gap-1 mt-1">
                          <AlertCircle className="h-3 w-3 text-red-500" />
                          <span className="text-[10px] text-red-600">
                            {stepLabels[c.errorStep] || c.errorStep}
                          </span>
                        </div>
                      )}
                      {c.status === 'INCOMPLETE' && c.lastCompletedStep && (
                        <div className="flex items-center gap-1 mt-1">
                          <Clock className="h-3 w-3 text-amber-500" />
                          <span className="text-[10px] text-amber-600">
                            {'تا: '}{stepLabels[c.lastCompletedStep] || c.lastCompletedStep}
                          </span>
                        </div>
                      )}
                    </TableCell>
                  )}
                  {columnVisibility.feeStatus && (
                    <TableCell className="px-3 py-3">
                      <Badge
                        variant="outline"
                        className={cn('text-[11px]', feeStatusColors[c.feeStatus])}
                      >
                        {feeStatusLabels[c.feeStatus] || c.feeStatus}
                      </Badge>
                    </TableCell>
                  )}
                  {columnVisibility.branch && (
                    <TableCell className="px-3 py-3 hidden md:table-cell">
                      <p className="text-xs truncate max-w-[150px]">
                        {c.branchName || c.province || '—'}
                      </p>
                    </TableCell>
                  )}
                  {columnVisibility.fee && (
                    <TableCell className="px-3 py-3">
                      <p className="text-xs font-medium nums-align" dir="ltr">
                        {formatToman(c.fee)}
                      </p>
                    </TableCell>
                  )}
                  {columnVisibility.date && (
                    <TableCell className="px-3 py-3 hidden lg:table-cell">
                      <p className="text-[11px] text-muted-foreground nums-align">
                        {relativeTime(c.createdAt)}
                      </p>
                      <p className="text-[10px] text-muted-foreground/70 nums-align">
                        {formatDate(c.createdAt)}
                      </p>
                    </TableCell>
                  )}
                  {columnVisibility.signature && (
                    <TableCell className="px-3 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                      {c.serviceType === 'INQUIRY' ? (
                        <span className="text-[10px] text-muted-foreground">{'—'}</span>
                      ) : c.hasSignature ? (
                        <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 text-[10px] gap-1">
                          <PenLine className="h-3 w-3" />
                          {'دارای امضا'}
                        </Badge>
                      ) : (
                        <Badge className="bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300 text-[10px] gap-1">
                          <XCircle className="h-3 w-3" />
                          {'بدون امضا'}
                        </Badge>
                      )}
                    </TableCell>
                  )}
                  {showConfirmButton && (
                    <TableCell className="px-3 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                        onClick={(e) => { e.stopPropagation(); onConfirmSend?.(c); }}
                        title={'تأیید و ارسال'}
                      >
                        <CheckCircle2 className="h-5 w-5" />
                      </Button>
                    </TableCell>
                  )}
                  {columnVisibility.actions && (
                    <TableCell className="px-3 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          <DropdownMenuItem onClick={() => onViewDetail(c)}>
                            <Eye className="h-4 w-4 ml-2" />
                            {'مشاهده جزئیات'}
                          </DropdownMenuItem>
                          {showConfirmButton && (
                            <DropdownMenuItem
                              onClick={() => onConfirmSend?.(c)}
                              className="text-emerald-600"
                            >
                              <CheckCircle2 className="h-4 w-4 ml-2" />
                              {'تأیید و ارسال'}
                            </DropdownMenuItem>
                          )}
                          {showInterventionButton && (
                            <DropdownMenuItem
                              onClick={() => onManualIntervention?.(c)}
                              className="text-amber-600"
                            >
                              <Send className="h-4 w-4 ml-2" />
                              {'مداخله دستی / ارسال'}
                            </DropdownMenuItem>
                          )}
                          {onDeleteCase && (
                            <DropdownMenuItem
                              onClick={() => onDeleteCase(c)}
                              className="text-red-600 focus:text-red-600"
                            >
                              <Trash2 className="h-4 w-4 ml-2" />
                              {'حذف پرونده'}
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  )}
                </TableRow>
                {expandedId === c.id && (
                <TableRow className={cn('table-row-premium bg-muted/20 dark:bg-muted/10 hover:bg-muted/20 dark:hover:bg-muted/10')}>
                  <td colSpan={totalColSpan} className="p-0">
                    <div className="animate-fade-in-up px-4 py-3">
                      <div className="glass-v2 rounded-lg max-w-4xl mx-auto p-4">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                          {/* Left column */}
                          <div className="flex flex-col gap-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge variant="secondary" className={cn('text-[11px] font-medium', serviceTypeColors[c.serviceType])}>
                                {serviceTypeLabels[c.serviceType] || c.serviceType}
                              </Badge>
                              <Badge variant="secondary" className={cn('badge-status text-[11px] font-medium', statusColors[c.status])}>
                                {c.isInReadyToSend ? 'آماده ارسال' : statusLabels[c.status] || c.status}
                              </Badge>
                            </div>
                            {c.trackingCode && (
                              <p className="text-[11px] text-muted-foreground font-mono" dir="ltr">
                                {c.trackingCode}
                              </p>
                            )}
                          </div>
                          {/* Center column */}
                          <div className="flex flex-col gap-1.5 text-xs text-muted-foreground">
                            <p>{c.branchName || '—'}</p>
                            <p>{c.province || '—'}</p>
                            <p className="nums-align">{new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' }).format(new Date(c.createdAt))}</p>
                          </div>
                          {/* Right column */}
                          <div className="flex flex-col gap-1.5 text-xs items-start sm:items-end">
                            <p className="font-medium nums-align" dir="ltr">{c.fee.toLocaleString('fa-IR')} {'تومان'}</p>
                            <Badge variant="outline" className={cn('text-[11px]', feeStatusColors[c.feeStatus])}>
                              {feeStatusLabels[c.feeStatus] || c.feeStatus}
                            </Badge>
                            {(() => { try { const p = JSON.parse(c.persons as string); return Array.isArray(p) && p.length > 0 ? (
                              <p className="text-[11px] text-muted-foreground">{new Intl.NumberFormat('fa-IR').format(p.length)} {'نفر'}</p>
                            ) : null; } catch { return null; } })()}
                          </div>
                        </div>
                        {/* Quick actions */}
                        <div className="divider-gradient my-3" />
                        <div className="flex items-center gap-2 flex-wrap">
                          <Button
                            variant="outline"
                            size="sm"
                            className="btn-micro h-7 gap-1.5 text-[11px]"
                            onClick={(e) => { e.stopPropagation(); onViewDetail(c); }}
                          >
                            <Eye className="h-3 w-3" />
                            {'مشاهده جزئیات'}
                          </Button>
                          {showInterventionButton && onManualIntervention && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="btn-micro h-7 gap-1.5 text-[11px] text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-950/20"
                              onClick={(e) => { e.stopPropagation(); onManualIntervention(c); }}
                            >
                              <Wrench className="h-3 w-3" />
                              {'مداخله دستی'}
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                </TableRow>
                )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {pagination && pagination.totalPages > 1 && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mt-4 px-1 gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <p className="text-xs text-muted-foreground">
              {'نمایش '}{new Intl.NumberFormat('fa-IR').format((pagination.page - 1) * pagination.limit + 1)}
              {'تا '}{new Intl.NumberFormat('fa-IR').format(Math.min(pagination.page * pagination.limit, pagination.total))}
              {' از '}{new Intl.NumberFormat('fa-IR').format(pagination.total)} {'مورد'}
            </p>
            {onPageSizeChange && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground/70">{'تعداد:'}</span>
                <Select
                  value={String(pagination.limit)}
                  onValueChange={(v) => onPageSizeChange(Number(v))}
                >
                  <SelectTrigger size="sm" className="h-7 w-[60px] text-[11px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {pageSizeOptions.map((size) => (
                      <SelectItem key={size} value={String(size)} className="text-[11px]">
                        {new Intl.NumberFormat('fa-IR').format(size)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1.5 sm:gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-10 sm:h-8 w-10 sm:w-9 p-0 sm:px-2.5"
              disabled={pagination.page <= 1}
              onClick={() => onPageChange(pagination.page - 1)}
            >
              <ChevronRight className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
            </Button>
            {Array.from({ length: Math.min(5, pagination.totalPages) }).map((_, i) => {
              let pageNum: number;
              if (pagination.totalPages <= 5) {
                pageNum = i + 1;
              } else if (pagination.page <= 3) {
                pageNum = i + 1;
              } else if (pagination.page >= pagination.totalPages - 2) {
                pageNum = pagination.totalPages - 4 + i;
              } else {
                pageNum = pagination.page - 2 + i;
              }
              return (
                <Button
                  key={pageNum}
                  variant={pagination.page === pageNum ? 'default' : 'outline'}
                  size="sm"
                  className={cn(
                    'h-10 sm:h-8 w-10 sm:w-8 p-0 text-xs transition-all',
                    pagination.page === pageNum && 'shadow-sm'
                  )}
                  onClick={() => onPageChange(pageNum)}
                >
                  {new Intl.NumberFormat('fa-IR').format(pageNum)}
                </Button>
              );
            })}
            <Button
              variant="outline"
              size="sm"
              className="h-10 sm:h-8 w-10 sm:w-9 p-0 sm:px-2.5"
              disabled={pagination.page >= pagination.totalPages}
              onClick={() => onPageChange(pagination.page + 1)}
            >
              <ChevronLeft className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
            </Button>
            {pagination.totalPages > 5 && (
              <div className="flex items-center gap-1.5 mr-2 pr-2 border-r border-border/50">
                <span className="text-[11px] text-muted-foreground/60 whitespace-nowrap">{'صفحه'}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={goToPageValue}
                  onChange={(e) => setGoToPageValue(e.target.value.replace(/[^\d]/g, ''))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleGoToPage();
                  }}
                  placeholder={new Intl.NumberFormat('fa-IR').format(pagination.page)}
                  className="h-7 w-12 text-[11px] text-center rounded-md border border-input bg-transparent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring placeholder:text-muted-foreground/40"
                  dir="ltr"
                />
                <span className="text-[11px] text-muted-foreground/40">/ {new Intl.NumberFormat('fa-IR').format(pagination.totalPages)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {pagination && pagination.total <= 15 && pagination.totalPages <= 1 && (
        <p className="text-[11px] text-muted-foreground/60 mt-3 text-center">
          {new Intl.NumberFormat('fa-IR').format(pagination.total)} {'مورد'}
        </p>
      )}
    </div>
  );
});
CasesTableMemo.displayName = 'CasesTable';

export default CasesTableMemo;
