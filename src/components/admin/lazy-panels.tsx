'use client';

import React, { Suspense } from 'react';
import type { CaseItem } from '@/components/admin/cases-table';
import type { AdminAction } from '@/components/admin/case-detail-dialog';

const CaseDetailDialog = React.lazy(() => import('@/components/admin/case-detail-dialog'));
const ManualInterventionDialog = React.lazy(() => import('@/components/admin/manual-intervention-dialog'));
const BatchActionsDialog = React.lazy(() => import('@/components/admin/batch-actions'));
const ActivityPanel = React.lazy(() => import('@/components/admin/activity-panel'));
const UserHistoryDialog = React.lazy(() => import('@/components/admin/user-history-dialog'));
const BotMessageSender = React.lazy(() => import('@/components/admin/bot-message-sender'));
const GoogleSheetsPanel = React.lazy(() => import('@/components/admin/google-sheets-panel'));
const WorkingHoursDialog = React.lazy(() => import('@/components/admin/working-hours-dialog'));
const ExemptUsersDialog = React.lazy(() => import('@/components/admin/exempt-users-dialog'));

function LoadingFallback() {
  return <div className="animate-pulse h-8 w-48 rounded-lg bg-muted" />;
}

interface LazyPanelsProps {
  // Case detail
  detailCase: CaseItem | null;
  detailOpen: boolean;
  onDetailClose: () => void;
  onManualIntervention: (c: CaseItem) => void;
  onConfirmSend: (c: CaseItem) => void;
  onDeleteCase: (c: CaseItem) => void;
  adminActions: AdminAction[];
  // Manual intervention
  interventionCase: CaseItem | null;
  interventionOpen: boolean;
  onInterventionClose: () => void;
  onInterventionSubmit: (data: {
    caseId: string;
    adminNote: string;
    actionType: string;
    newStatus: string;
    uploadedFileUrls: string[];
    sentViaBot: boolean;
  }) => Promise<void>;
  // Batch
  batchOpen: boolean;
  onBatchClose: () => void;
  selectedIds: string[];
  onBatchDone: () => void;
  // Activity
  activityOpen: boolean;
  onActivityClose: () => void;
  // User history
  historyOpen: boolean;
  onHistoryClose: () => void;
  historyUser: { baleUserId: string; fullName: string } | null;
  // Bot sender
  botSenderOpen: boolean;
  onBotSenderClose: () => void;
  onBotSenderRefresh: () => void;
  // Google Sheets
  sheetsPanelOpen: boolean;
  onSheetsPanelClose: () => void;
  // Working hours
  workingHoursOpen: boolean;
  onWorkingHoursClose: () => void;
  // Exempt users
  exemptUsersOpen: boolean;
  onExemptUsersClose: () => void;
}

export default function LazyPanels({
  detailCase, detailOpen, onDetailClose, onManualIntervention, onConfirmSend, onDeleteCase, adminActions,
  interventionCase, interventionOpen, onInterventionClose, onInterventionSubmit,
  batchOpen, onBatchClose, selectedIds, onBatchDone,
  activityOpen, onActivityClose,
  historyOpen, onHistoryClose, historyUser,
  botSenderOpen, onBotSenderClose, onBotSenderRefresh,
  sheetsPanelOpen, onSheetsPanelClose,
  workingHoursOpen, onWorkingHoursClose,
  exemptUsersOpen, onExemptUsersClose,
}: LazyPanelsProps) {
  return (
    <>
      <Suspense fallback={<LoadingFallback />}>
        <CaseDetailDialog
          caseItem={detailCase}
          open={detailOpen}
          onClose={onDetailClose}
          onManualIntervention={onManualIntervention}
          onConfirmSend={onConfirmSend}
          onDeleteCase={onDeleteCase}
          adminActions={adminActions}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <ManualInterventionDialog
          caseItem={interventionCase}
          open={interventionOpen}
          onClose={onInterventionClose}
          onSubmit={onInterventionSubmit}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <BatchActionsDialog
          selectedIds={selectedIds}
          open={batchOpen}
          onClose={onBatchClose}
          onDone={onBatchDone}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <ActivityPanel
          open={activityOpen}
          onClose={onActivityClose}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <UserHistoryDialog
          baleUserId={historyUser?.baleUserId || ''}
          fullName={historyUser?.fullName || ''}
          open={historyOpen}
          onClose={onHistoryClose}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <BotMessageSender
          open={botSenderOpen}
          onClose={onBotSenderClose}
          onRefresh={onBotSenderRefresh}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <GoogleSheetsPanel
          open={sheetsPanelOpen}
          onClose={onSheetsPanelClose}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <WorkingHoursDialog
          open={workingHoursOpen}
          onOpenChange={(open) => { if (!open) onWorkingHoursClose(); }}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <ExemptUsersDialog
          open={exemptUsersOpen}
          onOpenChange={(open) => { if (!open) onExemptUsersClose(); }}
        />
      </Suspense>
    </>
  );
}
