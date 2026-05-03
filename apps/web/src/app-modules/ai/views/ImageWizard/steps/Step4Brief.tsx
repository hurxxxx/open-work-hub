import { useEffect, useRef, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  approveImageGeneration,
  downloadGeneratedImageBlob,
  generateBrief,
  getImageGeneration,
  type ImageGeneration,
} from '../../../api/image-wizard-api';
import { BriefTurn } from '../chat/BriefTurn';
import { BriefRefineComposer } from '../chat/BriefRefineComposer';
import { ImageResultTurn } from '../chat/ImageResultTurn';
import { PendingTurn } from '../chat/PendingTurn';

const POLL_INTERVAL_MS = 2000;

interface Step4BriefProps {
  workspaceSlug: string;
  row: ImageGeneration;
  onRowReplaced: (next: ImageGeneration) => void;
  onClone: () => void;
  onDiscard: () => void;
}

export function Step4Brief({
  workspaceSlug,
  row,
  onRowReplaced,
  onClone,
  onDiscard,
}: Step4BriefProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const [busy, setBusy] = useState<'brief' | 'approve' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [imageLoadError, setImageLoadError] = useState<string | null>(null);
  const requestedInitialBriefFor = useRef<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-request the initial brief on entering step 4 if there are none yet.
  useEffect(() => {
    if (!token) return;
    if (requestedInitialBriefFor.current === row.id) return;
    if (row.brief_versions.length > 0) {
      requestedInitialBriefFor.current = row.id;
      return;
    }
    if (row.brief_status === 'approved') return;
    requestedInitialBriefFor.current = row.id;
    void runGenerateBrief();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, row.id]);

  // Poll while generating.
  useEffect(() => {
    if (!token || !row.id) return;
    if (row.image_status !== 'queued' && row.image_status !== 'running') return;
    function tick() {
      if (!token) return;
      getImageGeneration(token, workspaceSlug, row.id)
        .then((fetched) => {
          onRowReplaced(fetched);
        })
        .catch(() => {
          // ignore; next tick retries
        })
        .finally(() => {
          pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
        });
    }
    pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      pollTimer.current = null;
    };
  }, [token, workspaceSlug, row.id, row.image_status, onRowReplaced]);

  // Fetch the generated image through the authenticated API. The MinIO URL is
  // internal to the VM and cannot be used directly from the public HTTPS page.
  useEffect(() => {
    if (!token || row.image_status !== 'succeeded' || !row.id) {
      setDownloadUrl(null);
      setImageLoadError(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setImageLoadError(null);
    downloadGeneratedImageBlob(token, workspaceSlug, row.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setDownloadUrl(objectUrl);
      })
      .catch((err) => {
        if (cancelled) return;
        setDownloadUrl(null);
        setImageLoadError(
          err instanceof Error ? err.message : t('ai.imageWizard.step4.imageLoadFailed'),
        );
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, workspaceSlug, row.id, row.image_status, t]);

  async function runGenerateBrief(editInstruction?: string) {
    if (!token) return;
    setBusy('brief');
    setError(null);
    try {
      await generateBrief(token, workspaceSlug, row.id, { editInstruction });
      const refreshed = await getImageGeneration(token, workspaceSlug, row.id);
      onRowReplaced(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.briefFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function runApprove() {
    if (!token) return;
    setBusy('approve');
    setError(null);
    try {
      const approved = await approveImageGeneration(token, workspaceSlug, row.id);
      onRowReplaced(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.approveFailed'));
    } finally {
      setBusy(null);
    }
  }

  const isGeneratingImage = row.image_status === 'queued' || row.image_status === 'running';
  const isFinished = row.image_status === 'succeeded' || row.image_status === 'failed';
  const composerDisabled = row.brief_status === 'approved' || isGeneratingImage || isFinished;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h2 className="app-text-heading-2 text-app-ink">
          {t('ai.imageWizard.steps.step4.heading')}
        </h2>
        <p className="app-text-body text-app-ink/60">
          {t('ai.imageWizard.steps.step4.description')}
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
        >
          {error}
        </div>
      ) : null}

      {row.brief_versions.length === 0 && busy === 'brief' ? (
        <div className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar p-4 text-app-ink/60">
          <Loader2 size={16} className="animate-spin text-app-accent" />
          <span className="app-text-control-sm">
            {t('ai.imageWizard.step4.generatingFirstBrief')}
          </span>
        </div>
      ) : null}

      <div className="space-y-3">
        {row.brief_versions.map((version, idx) => (
          <BriefTurn
            key={`${version.created_at}-${idx}`}
            version={version}
            index={idx}
            isLatest={idx === row.brief_versions.length - 1}
            approving={busy === 'approve' && idx === row.brief_versions.length - 1}
            approveDisabled={composerDisabled}
            onApprove={runApprove}
          />
        ))}
      </div>

      {row.brief_versions.length > 0 && !isGeneratingImage && !isFinished ? (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => runGenerateBrief()}
            disabled={busy === 'brief'}
            className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent disabled:opacity-50"
          >
            {busy === 'brief' ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Sparkles size={13} />
            )}
            {t('ai.imageWizard.step4.regenerate')}
          </button>
        </div>
      ) : null}

      {isGeneratingImage ? <PendingTurn status={row.image_status as 'queued' | 'running'} /> : null}

      {isFinished ? (
        <ImageResultTurn
          imageUrl={downloadUrl}
          loading={!downloadUrl && !imageLoadError && row.image_status === 'succeeded'}
          loadError={imageLoadError}
          failureReason={row.image_status === 'failed' ? row.failure_reason : null}
          onClone={onClone}
          onDiscard={onDiscard}
        />
      ) : null}

      {!isGeneratingImage && !isFinished && row.brief_versions.length > 0 ? (
        <BriefRefineComposer
          disabled={composerDisabled}
          busy={busy === 'brief'}
          onSend={runGenerateBrief}
        />
      ) : null}
    </div>
  );
}

export default Step4Brief;
