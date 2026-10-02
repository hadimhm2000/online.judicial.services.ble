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
const ResetDataDialog = React.lazy(() => import('@/components/admin/reset-data-dialog'));
const CreditsDialog = React.lazy(() => import('@/components/admin/credits-dialog'));
const CardPaymentsDialog = React.lazy(() => import('@/components/admin/card-payments-dialog'));
const BotSettingsDialog = React.lazy(() => import('@/components/admin/bot-settings-dialog'));
const InsightsDialog = React.lazy(() => import('@/components/admin/insights-dialog'));

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
  onAddCredit?: (c: CaseItem) => void;
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
  // ⭐ v1.7 — Credits ledger
  creditsOpen?: boolean;
  onCreditsClose?: () => void;
  creditsPrefill?: { baleUserId?: string; fullName?: string; caseId?: string; trackingCode?: string | null } | null;
  onCreditsChanged?: () => void;
  // ⭐ v1.8 — Card-to-card payments
  cardPaymentsOpen?: boolean;
  onCardPaymentsClose?: () => void;
  // ⭐ v1.9 — Bot settings + feedback/funnel insights
  botSettingsOpen?: boolean;
  onBotSettingsClose?: () => void;
  insightsOpen?: boolean;
  onInsightsClose?: () => void;
  // Reset data
  resetDataOpen: boolean;
  onResetDataClose: () => void;
  onResetDataDone: () => void;
}

export default function LazyPanels({
  detailCase, detailOpen, onDetailClose, onManualIntervention, onConfirmSend, onDeleteCase, onAddCredit, adminActions,
  interventionCase, interventionOpen, onInterventionClose, onInterventionSubmit,
  batchOpen, onBatchClose, selectedIds, onBatchDone,
  activityOpen, onActivityClose,
  historyOpen, onHistoryClose, historyUser,
  botSenderOpen, onBotSenderClose, onBotSenderRefresh,
  sheetsPanelOpen, onSheetsPanelClose,
  workingHoursOpen, onWorkingHoursClose,
  exemptUsersOpen, onExemptUsersClose,
  creditsOpen = false, onCreditsClose, creditsPrefill, onCreditsChanged,
  cardPaymentsOpen = false, onCardPaymentsClose,
  botSettingsOpen = false, onBotSettingsClose,
  insightsOpen = false, onInsightsClose,
  resetDataOpen, onResetDataClose, onResetDataDone,
}: LazyPanelsProps) {
  return (
    <>
      <Suspense fallback={<LoadingFallback />}>
        <CaseDetailDialog
          caseItem={detailCase}
          open={detailOpen}
          onClose={onDetailClose}
          onManualIntervention={onManualIntervention}
          onAddCredit={onAddCredit}
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

      <Suspense fallback={<LoadingFallback />}>
        <CreditsDialog
          open={creditsOpen}
          onOpenChange={(open) => { if (!open) onCreditsClose?.(); }}
          prefill={creditsPrefill}
          onChanged={onCreditsChanged}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <CardPaymentsDialog
          open={cardPaymentsOpen}
          onOpenChange={(open) => { if (!open) onCardPaymentsClose?.(); }}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <BotSettingsDialog
          open={botSettingsOpen}
          onOpenChange={(open) => { if (!open) onBotSettingsClose?.(); }}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <InsightsDialog
          open={insightsOpen}
          onOpenChange={(open) => { if (!open) onInsightsClose?.(); }}
        />
      </Suspense>

      <Suspense fallback={<LoadingFallback />}>
        <ResetDataDialog
          open={resetDataOpen}
          onOpenChange={(open) => { if (!open) onResetDataClose(); }}
          onDone={onResetDataDone}
        />
      </Suspense>
    </>
  );
}
