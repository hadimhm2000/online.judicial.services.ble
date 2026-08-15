import * as XLSX from 'xlsx';

export interface ExportRow {
  fullName: string;
  baleUserId: string;
  serviceType: string;
  status: string;
  fee: number;
  feeStatus: string;
  branchName: string | null;
  createdAt: string;
}

const HEADERS: string[] = [
  'نام',
  'شناسه بله',
  'نوع خدمت',
  'وضعیت',
  'هزینه',
  'وضعیت پرداخت',
  'شعبه',
  'تاریخ',
];

function rowToValues(r: ExportRow): string[] {
  return [
    r.fullName,
    r.baleUserId,
    r.serviceType,
    r.status,
    String(r.fee),
    r.feeStatus,
    r.branchName || '',
    r.createdAt,
  ];
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatToman(n: number): string {
  return new Intl.NumberFormat('fa-IR').format(n);
}

export function exportToCSV(data: ExportRow[], filename: string): void {
  const rows = data.map(rowToValues);
  const bom = '﻿';
  const csv = bom + [HEADERS, ...rows].map((r) => r.map((c) => `"${c}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportToExcel(data: ExportRow[], filename: string): void {
  const persianFormatter = new Intl.NumberFormat('fa-IR');

  const headerRow = HEADERS.map((h) => ({
    v: h,
    t: 's' as const,
    s: {
      font: { bold: true, name: 'Vazirmatn', sz: 12, color: { rgb: 'FFFFFF' } },
      fill: { fgColor: { rgb: '059669' } },
      alignment: { horizontal: 'center', vertical: 'center', wrapText: true },
    },
  }));

  const dataRows = data.map((r) => rowToValues(r).map((v, idx) => {
    if (idx === 4) {
      return {
        v: r.fee,
        t: 'n' as const,
        s: {
          font: { name: 'Vazirmatn' },
          alignment: { horizontal: 'center' },
          numFmt: '#,##0',
        },
      };
    }
    return {
      v,
      t: 's' as const,
      s: {
        font: { name: 'Vazirmatn' },
        alignment: { horizontal: 'center', vertical: 'center' },
      },
    };
  }));

  const totalFee = data.reduce((sum, r) => sum + r.fee, 0);
  const footerRow = [
    {
      v: `جمع کل: ${data.length} پرونده`,
      t: 's' as const,
      s: {
        font: { bold: true, name: 'Vazirmatn', sz: 11 },
        alignment: { horizontal: 'right' },
      },
    },
    ...Array(3).fill(null).map(() => ({ v: '', t: 's' as const })),
    {
      v: totalFee,
      t: 'n' as const,
      s: {
        font: { bold: true, name: 'Vazirmatn', sz: 11 },
        alignment: { horizontal: 'center' },
        numFmt: '#,##0',
      },
    },
    ...Array(3).fill(null).map(() => ({ v: '', t: 's' as const })),
  ];

  const aoa: XLSX.CellObject[][] = [headerRow, ...dataRows, footerRow];

  const ws = XLSX.utils.aoa_to_sheet(aoa);

  ws['!dir'] = 'rtl';

  const colWidths = HEADERS.map((_, colIdx) => {
    let maxLen = HEADERS[colIdx].length;
    data.forEach((r) => {
      const val = rowToValues(r)[colIdx];
      const len = val.length;
      if (len > maxLen) maxLen = len;
    });
    return { wch: Math.max(maxLen + 2, 12) };
  });
  ws['!cols'] = colWidths;

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'لیست پرونده‌ها');

  const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  const bom = new Uint8Array([0xEF, 0xBB, 0xBF]);
  const blob = new Blob([bom, wbout], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}
