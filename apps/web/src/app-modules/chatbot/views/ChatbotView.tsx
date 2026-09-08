import { LazyMotion, domAnimation, m } from 'motion/react';
import { Suspense, lazy } from 'react';

import { ApprovalModal } from './chat/ApprovalModal';
import { ChatComposer } from './chat/ChatComposer';
import { ChatThread } from './chat/ChatThread';
import { ChatTopBar } from './chat/ChatTopBar';
import { EmptyState } from './chat/EmptyState';
import { ToolCallCard } from './chat/ToolCallCard';
import type { ChatbotExperienceConfig } from './chatbot-experience';
import { resolveFailedPromptRestoreInput } from './chatbot-view-model';
import { ChatbotConversationListPanel } from './ChatbotConversationListPanel';
import {
  useChatbotViewController,
  type ChatbotViewController,
} from './useChatbotViewController';

const ArtifactPanel = lazy(() =>
  import('./chat/ArtifactPanel').then((module) => ({
    default: module.ArtifactPanel,
  })),
);

export interface ChatbotViewProps {
  experience?: ChatbotExperienceConfig;
}

export function ChatbotView({ experience }: ChatbotViewProps) {
  const controller = useChatbotViewController(experience);
  return <ChatbotViewContent controller={controller} />;
}

function ApprovalNotice({ controller }: { controller: ChatbotViewController }) {
  const { actions, derived, state } = controller;
  const {
    approvalAction,
    approvalError,
    blockingApproval,
    pendingApproval,
    resumableApproval,
  } = state;
  const { handleAbandonApproval, resumePendingApproval } = actions;
  const { t } = derived;

  if (!blockingApproval) {
    return null;
  }

  const blockingApprovalAction =
    approvalAction?.approvalId === blockingApproval.approval_id
      ? approvalAction.kind
      : null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <div>
        <p className="app-text-body-sm text-app-ink">
          {pendingApproval
            ? t('apps:ai.view.approvalBlocking')
            : t('apps:ai.view.approvalResumeHint')}
        </p>
        <p className="app-text-caption text-app-ink/60">
          {blockingApproval.tool}
          {blockingApproval.resource_preview
            ? ` · ${blockingApproval.resource_preview}`
            : ''}
        </p>
        {approvalError && !pendingApproval ? (
          <p
            role="alert"
            className="app-text-caption mt-1 text-[var(--ui-color-danger)]"
          >
            {approvalError}
          </p>
        ) : null}
      </div>
      {pendingApproval ? (
        <button
          type="button"
          onClick={() => {
            void handleAbandonApproval(pendingApproval);
          }}
          disabled={Boolean(blockingApprovalAction)}
          className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:border-app-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {blockingApprovalAction === 'abandon'
            ? t('apps:ai.view.abandonPending')
            : t('apps:ai.approval.cancelRequest')}
        </button>
      ) : resumableApproval ? (
        <button
          type="button"
          onClick={() => {
            void resumePendingApproval(resumableApproval);
          }}
          disabled={Boolean(blockingApprovalAction)}
          className="app-text-control rounded-md bg-app-accent px-3 py-2 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {blockingApprovalAction === 'resume'
            ? t('apps:ai.view.resuming')
            : t('apps:ai.view.resume')}
        </button>
      ) : null}
    </div>
  );
}

function FailedPromptNotice({
  controller,
}: {
  controller: ChatbotViewController;
}) {
  const { actions, derived, state } = controller;
  const { failedPromptRecovery } = state;
  const { setFailedPromptRecovery, setInput } = actions;
  const { t } = derived;

  if (!failedPromptRecovery) {
    return null;
  }

  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2"
    >
      <p className="app-text-body-sm text-app-ink">
        {t('apps:ai.message.failedPromptSaved')}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setInput((current) =>
              resolveFailedPromptRestoreInput(current, failedPromptRecovery),
            );
            setFailedPromptRecovery('');
          }}
          className="app-text-control rounded-md bg-app-accent px-3 py-2 text-app-accent-fg transition-colors hover:bg-app-accent-hover"
        >
          {t('apps:ai.message.restoreFailedPrompt')}
        </button>
        <button
          type="button"
          onClick={() => setFailedPromptRecovery('')}
          className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:border-app-accent"
        >
          {t('apps:ai.message.dismissFailedPrompt')}
        </button>
      </div>
    </div>
  );
}

function ChatComposerBlock({
  autoFocus = false,
  controller,
}: {
  autoFocus?: boolean;
  controller: ChatbotViewController;
}) {
  const { actions, derived, state } = controller;
  const {
    blockingApproval,
    chatError,
    chatState,
    input,
    isComposerDisabled,
    isConversationReady,
    isLoadingConversation,
    isSending,
  } = state;
  const { abortChat, handleSelectTool, handleSubmit, setInput } = actions;
  const { slashCommandItems, t } = derived;

  const composerPlaceholder = isLoadingConversation
    ? t('apps:ai.view.conversationLoading')
    : !isConversationReady
      ? t('apps:ai.view.conversationUnavailable')
      : blockingApproval
        ? t('apps:ai.view.approvalBlocking')
        : undefined;

  return (
    <>
      <ApprovalNotice controller={controller} />
      <FailedPromptNotice controller={controller} />
      <ChatComposer
        input={input}
        onInputChange={setInput}
        onSubmit={handleSubmit}
        onAbort={abortChat}
        isSending={isSending}
        isStreaming={chatState.transport === 'stream'}
        chatError={chatError}
        isDisabled={isComposerDisabled}
        onSelectTool={handleSelectTool}
        toolItems={slashCommandItems}
        placeholder={composerPlaceholder}
        autoFocus={autoFocus}
        leadingControls={null}
      />
    </>
  );
}

function ChatbotViewContent({
  controller,
}: {
  controller: ChatbotViewController;
}) {
  const { actions, derived, state } = controller;
  const {
    approvalAction,
    approvalError,
    chatState,
    currentConversationId,
    editingText,
    editingTurnId,
    forceFollowKey,
    health,
    healthError,
    isLoadingConversation,
    isRunInProgress,
    isSending,
    pendingApproval,
    recoveredRunIsActive,
    routeArtifactId,
    turns,
  } = state;
  const {
    handleAbandonApproval,
    handleCloseArtifact,
    handleCopyTurn,
    handleOpenArtifact,
    handleResolveApproval,
    handleRetryTurn,
    handleStartEditTurn,
    setEditingText,
    setEditingTurnId,
    submitEditedTurn,
  } = actions;
  const {
    activeArtifact,
    allArtifacts,
    confirmDialog,
    durableRun,
    experience,
    t,
    visibleToolCalls,
  } = derived;

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-app-bg"
      >
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-app-surface lg:flex-row">
          <ChatbotConversationListPanel
            activeConversationId={currentConversationId}
            navigationDisabled={isSending}
            pendingConversationTitle={
              isSending ? chatState.pendingUserContent : null
            }
            routeId={experience.routeId}
            scopeRef={experience.conversationScope?.ref}
            scopeResourceId={experience.conversationScope?.resourceId}
            eyebrow={experience.sidebarEyebrow}
            title={experience.sidebarTitle}
          />

          <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-app-surface">
            <ChatTopBar
              title={experience.title}
              health={health}
              healthError={healthError}
            />

            {turns.length === 0 && !isRunInProgress ? (
              <EmptyState
                greeting={
                  isLoadingConversation
                    ? t('apps:ai.view.conversationLoading')
                    : experience.emptyGreeting
                }
                subline={
                  isLoadingConversation
                    ? t('apps:ai.view.wait')
                    : experience.emptySubline
                }
              >
                <div className="space-y-2">
                  <ChatComposerBlock controller={controller} autoFocus />
                </div>
              </EmptyState>
            ) : (
              <>
                <ChatThread
                  turns={turns}
                  typingLabel={t('ai.message.typing')}
                  jumpToBottomLabel={t('ai.message.jumpToBottom')}
                  activeArtifactId={routeArtifactId}
                  onOpenArtifact={handleOpenArtifact}
                  onCopyTurn={handleCopyTurn}
                  onEditTurn={handleStartEditTurn}
                  onRetryTurn={(turn) => {
                    void handleRetryTurn(turn);
                  }}
                  editingTurnId={editingTurnId}
                  editValue={editingText}
                  onEditValueChange={setEditingText}
                  onSubmitEdit={() => {
                    void submitEditedTurn();
                  }}
                  onCancelEdit={() => {
                    setEditingTurnId(null);
                    setEditingText('');
                  }}
                  sourceArtifactTypes={experience.sourceArtifactTypes}
                  artifactRenderers={experience.artifactRenderers}
                  resolvedArtifacts={allArtifacts}
                  liveAssistant={
                    isRunInProgress
                      ? {
                          content: isSending ? chatState.contentBuffer : '',
                          reasoning: isSending ? chatState.reasoningBuffer : '',
                          status: isSending ? chatState.status : 'streaming',
                          artifacts: isSending ? chatState.artifacts : [],
                          progress:
                            durableRun && recoveredRunIsActive
                              ? {
                                  currentStage: durableRun.currentStage,
                                  progressPercent: durableRun.progressPercent,
                                }
                              : undefined,
                        }
                      : null
                  }
                  forceFollowKey={forceFollowKey}
                />
                {visibleToolCalls.map((call) => (
                  <ToolCallCard key={call.call_id} call={call} />
                ))}
                <div className="sticky bottom-0 z-10 space-y-2 border-t border-app-border bg-app-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
                  <ChatComposerBlock controller={controller} />
                </div>
              </>
            )}
          </section>
        </div>
        {pendingApproval ? (
          <ApprovalModal
            key={pendingApproval.approval_id}
            approval={pendingApproval}
            isSubmitting={
              approvalAction?.approvalId === pendingApproval.approval_id
            }
            errorMessage={approvalError}
            onResolve={(decision, reason) =>
              handleResolveApproval(pendingApproval, decision, reason)
            }
            onClose={() => handleAbandonApproval(pendingApproval)}
          />
        ) : null}
        {confirmDialog}
        {activeArtifact ? (
          <Suspense fallback={null}>
            <ArtifactPanel
              artifact={activeArtifact}
              artifacts={allArtifacts}
              renderers={experience.artifactRenderers}
              onClose={handleCloseArtifact}
            />
          </Suspense>
        ) : null}
      </m.div>
    </LazyMotion>
  );
}
