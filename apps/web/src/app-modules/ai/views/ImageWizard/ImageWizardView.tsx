import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ChevronLeft, Download, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  approveImageGeneration,
  createImageGeneration,
  deleteReferenceImage,
  generateBrief,
  getImageDownloadUrl,
  getImageGeneration,
  ImageWizardApiError,
  patchImageGeneration,
  uploadReferenceImage,
  type DetailsPayload,
  type ImageGeneration,
  type LayoutPayload,
  type ReferenceImageRole,
  type StylePayload,
} from '../../api/image-wizard-api';
import {
  ASPECT_OPTIONS,
  LAYOUT_OPTIONS,
} from './wizard-options';
import { UseCaseStep } from './steps/UseCaseStep';
import { StyleStep } from './steps/StyleStep';
import { LayoutStep } from './steps/LayoutStep';
import { ReferenceImagesStep } from './steps/ReferenceImagesStep';
import { ContextStep } from './steps/ContextStep';
import { ReviewBriefStep } from './steps/ReviewBriefStep';

const PATCH_DEBOUNCE_MS = 500;
const POLL_INTERVAL_MS = 2000;

const DEFAULT_STYLE: StylePayload = {
  chips: [],
  palette: 'auto',
  background: 'auto',
  quality: 'high',
};
const DEFAULT_LAYOUT: LayoutPayload = {
  layout_id: LAYOUT_OPTIONS[0],
  aspect: ASPECT_OPTIONS[0],
};
const DEFAULT_DETAILS: DetailsPayload = { audience: '', notes: '' };
const BRIEF_INPUT_KEYS: Array<keyof ImageGeneration> = [
  'use_case',
  'use_case_other',
  'style',
  'layout',
  'details',
  'context_refs',
  'reference_image_keys',
];

interface ImageWizardViewProps {
  workspaceSlug: string;
  generationId: string | null;
  onGenerationCreated: (id: string) => void;
}

function buildEmptyDraft(): ImageGeneration {
  const now = new Date(0).toISOString();
  return {
    id: '',
    workspace_id: '',
    owner_id: '',
    use_case: '',
    use_case_other: '',
    style: { ...DEFAULT_STYLE },
    layout: { ...DEFAULT_LAYOUT },
    details: { ...DEFAULT_DETAILS },
    context_refs: [],
    reference_image_keys: [],
    brief_versions: [],
    brief_status: 'drafting',
    image_status: 'idle',
    image_storage_key: null,
    image_model: null,
    agent_trace_id: null,
    failure_reason: null,
    approved_at: null,
    completed_at: null,
    created_at: now,
    updated_at: now,
  };
}

function invalidatesBrief(patch: Partial<ImageGeneration>): boolean {
  return BRIEF_INPUT_KEYS.some((key) =>
    Object.prototype.hasOwnProperty.call(patch, key),
  );
}

export function ImageWizardView({
  workspaceSlug,
  generationId,
  onGenerationCreated,
}: ImageWizardViewProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const navigate = useNavigate();

  const [row, setRow] = useState<ImageGeneration>(() => buildEmptyDraft());
  const [loading, setLoading] = useState<boolean>(Boolean(generationId));
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<
    null | 'patching' | 'uploading' | 'brief' | 'approve' | 'download'
  >(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  const patchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestRowRef = useRef<ImageGeneration>(row);
  const createPromiseRef = useRef<Promise<ImageGeneration> | null>(null);
  const initialLoadDone = useRef(false);

  useEffect(() => {
    latestRowRef.current = row;
  }, [row]);

  // Initial load by generationId.
  useEffect(() => {
    if (!token || !generationId) {
      initialLoadDone.current = !generationId;
      if (!generationId) setRow(buildEmptyDraft());
      return;
    }
    setLoading(true);
    let cancelled = false;
    getImageGeneration(token, workspaceSlug, generationId)
      .then((fetched) => {
        if (cancelled) return;
        setRow(fetched);
        initialLoadDone.current = true;
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, generationId]);

  // Poll when image is queued or running.
  useEffect(() => {
    if (!token || !row.id) return;
    if (row.image_status !== 'queued' && row.image_status !== 'running') return;

    function tick() {
      if (!token) return;
      getImageGeneration(token, workspaceSlug, row.id)
        .then((fetched) => {
          setRow((current) => (current.id === fetched.id ? fetched : current));
        })
        .catch(() => {
          // Swallow; next tick will retry.
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
  }, [token, workspaceSlug, row.id, row.image_status]);

  // Download URL for succeeded image.
  useEffect(() => {
    if (!token || row.image_status !== 'succeeded' || !row.id) {
      setDownloadUrl(null);
      return;
    }
    let cancelled = false;
    getImageDownloadUrl(token, workspaceSlug, row.id)
      .then((response) => {
        if (cancelled) return;
        setDownloadUrl(response.url);
      })
      .catch(() => {
        if (cancelled) return;
        setDownloadUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, row.id, row.image_status]);

  function clearAutosaveTimer() {
    if (patchTimer.current) clearTimeout(patchTimer.current);
    patchTimer.current = null;
  }

  function draftPayload(draft: ImageGeneration) {
    return {
      use_case: draft.use_case,
      use_case_other: draft.use_case_other,
      style: draft.style,
      layout: draft.layout,
      details: draft.details,
      context_refs: draft.context_refs,
    };
  }

  async function persistDraft(
    draft: ImageGeneration = latestRowRef.current,
    showPatching = false,
  ): Promise<ImageGeneration> {
    if (!token) throw new Error(t('ai.imageWizard.errors.saveFailed'));
    clearAutosaveTimer();
    if (draft.brief_status === 'approved') return draft;
    if (!draft.id && createPromiseRef.current) {
      return createPromiseRef.current;
    }

    const save = (async () => {
      if (showPatching) setBusyAction('patching');
      if (!draft.id) {
        const created = await createImageGeneration(token, workspaceSlug, draftPayload(draft));
        latestRowRef.current = created;
        setRow(created);
        onGenerationCreated(created.id);
        return created;
      }

      const updated = await patchImageGeneration(
        token,
        workspaceSlug,
        draft.id,
        draftPayload(draft),
      );
      const current = latestRowRef.current;
      const merged = current.id === updated.id ? { ...current, ...updated } : updated;
      latestRowRef.current = merged;
      setRow((existing) =>
        existing.id === updated.id ? { ...existing, ...updated } : existing,
      );
      return merged;
    })();

    if (!draft.id) {
      createPromiseRef.current = save;
      save.then(
        () => {
          if (createPromiseRef.current === save) {
            createPromiseRef.current = null;
          }
        },
        () => {
          if (createPromiseRef.current === save) {
            createPromiseRef.current = null;
          }
        },
      );
    }

    try {
      const saved = await save;
      setError(null);
      return saved;
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.saveFailed'));
      throw err;
    } finally {
      if (showPatching) {
        setBusyAction((current) => (current === 'patching' ? null : current));
      }
    }
  }

  function scheduleAutosave(next: ImageGeneration) {
    if (!token || next.brief_status === 'approved') return;
    clearAutosaveTimer();
    patchTimer.current = setTimeout(async () => {
      patchTimer.current = null;
      try {
        await persistDraft(next, true);
      } catch {
        // persistDraft already surfaced the localized error.
      }
    }, PATCH_DEBOUNCE_MS);
  }

  const update = useCallback(
    (patch: Partial<ImageGeneration>) => {
      setRow((current) => {
        const next = {
          ...current,
          ...patch,
          brief_status:
            current.brief_status === 'ready' && invalidatesBrief(patch)
              ? 'drafting'
              : current.brief_status,
        };
        latestRowRef.current = next;
        scheduleAutosave(next);
        return next;
      });
    },
    // scheduleAutosave reads token + workspaceSlug from closure each call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [token, workspaceSlug],
  );

  async function handleUploadReference(file: File, role: ReferenceImageRole) {
    if (!token) return;
    try {
      setBusyAction('uploading');
      const draft = await persistDraft(latestRowRef.current);
      const id = draft.id;
      const ref = await uploadReferenceImage(token, workspaceSlug, id, file, role);
      setRow((current) => {
        const next = {
          ...current,
          reference_image_keys: [...current.reference_image_keys, ref],
          brief_status: current.brief_status === 'ready' ? 'drafting' : current.brief_status,
        };
        latestRowRef.current = next;
        return next;
      });
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('ai.imageWizard.errors.uploadFailed'),
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteReference(storageKey: string) {
    if (!token || !row.id) return;
    try {
      await deleteReferenceImage(token, workspaceSlug, row.id, storageKey);
      setRow((current) => {
        const next = {
          ...current,
          reference_image_keys: current.reference_image_keys.filter(
            (ref) => ref.storage_key !== storageKey,
          ),
          brief_status: current.brief_status === 'ready' ? 'drafting' : current.brief_status,
        };
        latestRowRef.current = next;
        return next;
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('ai.imageWizard.errors.deleteFailed'),
      );
    }
  }

  async function handleGenerateBrief(editInstruction?: string) {
    if (!token) return;
    try {
      setBusyAction('brief');
      const draft = await persistDraft(latestRowRef.current);
      const id = draft.id;
      await generateBrief(token, workspaceSlug, id, { editInstruction });
      const refreshed = await getImageGeneration(token, workspaceSlug, id);
      latestRowRef.current = refreshed;
      setRow(refreshed);
      setError(null);
    } catch (err) {
      const message =
        err instanceof ImageWizardApiError
          ? err.message
          : t('ai.imageWizard.errors.briefFailed');
      setError(message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleApprove() {
    if (!token || !latestRowRef.current.id) return;
    try {
      setBusyAction('approve');
      const saved = await persistDraft(latestRowRef.current);
      if (saved.brief_status !== 'ready') {
        setError(t('ai.imageWizard.errors.briefOutdated'));
        return;
      }
      const approved = await approveImageGeneration(token, workspaceSlug, saved.id);
      latestRowRef.current = approved;
      setRow(approved);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('ai.imageWizard.errors.approveFailed'),
      );
    } finally {
      setBusyAction(null);
    }
  }

  const hasInput = useMemo(() => {
    if (!row.use_case) return false;
    if (row.use_case === 'other' && !row.use_case_other.trim()) return false;
    return true;
  }, [row.use_case, row.use_case_other]);

  const galleryHref = useMemo(
    () => `/tool/image-wizard?workspace=${encodeURIComponent(workspaceSlug)}&view=gallery`,
    [workspaceSlug],
  );

  const isLocked = row.brief_status === 'approved';

  if (loading) {
    return (
      <div className="flex h-32 items-center justify-center text-app-ink/50">
        <Loader2 size={16} className="animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="app-text-heading-2 text-app-ink">
            {t('ai.imageWizard.title')}
          </h1>
          <p className="app-text-caption text-app-ink/60">
            {t('ai.imageWizard.subtitle')}
          </p>
        </div>
        <Link
          to={galleryHref}
          className="flex items-center gap-1 app-text-control-sm text-app-ink/60 hover:text-app-accent"
        >
          <ChevronLeft size={14} />
          {t('ai.imageWizard.gallery.title')}
        </Link>
      </div>

      {error ? (
        <div
          role="alert"
          className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
        >
          {error}
        </div>
      ) : null}

      <StepCard
        index={1}
        title={t('ai.imageWizard.steps.useCase.title')}
        completed={Boolean(row.use_case)}
      >
        <UseCaseStep
          useCase={row.use_case}
          useCaseOther={row.use_case_other}
          disabled={isLocked}
          onChange={(patch) =>
            update({
              use_case: patch.useCase ?? row.use_case,
              use_case_other: patch.useCaseOther ?? row.use_case_other,
            })
          }
        />
      </StepCard>

      <StepCard
        index={2}
        title={t('ai.imageWizard.steps.style.title')}
        completed={row.style.chips.length > 0}
      >
        <StyleStep
          style={row.style}
          disabled={isLocked}
          onChange={(style) => update({ style })}
        />
      </StepCard>

      <StepCard
        index={3}
        title={t('ai.imageWizard.steps.layout.title')}
        completed={Boolean(row.layout.layout_id)}
      >
        <LayoutStep
          layout={row.layout}
          disabled={isLocked}
          onChange={(layout) => update({ layout })}
        />
      </StepCard>

      <StepCard
        index={4}
        title={t('ai.imageWizard.steps.referenceImages.title')}
        completed={row.reference_image_keys.length > 0}
        optional
      >
        <ReferenceImagesStep
          references={row.reference_image_keys}
          uploading={busyAction === 'uploading'}
          disabled={isLocked}
          onUpload={handleUploadReference}
          onDelete={handleDeleteReference}
        />
      </StepCard>

      <StepCard
        index={5}
        title={t('ai.imageWizard.steps.context.title')}
        completed={
          row.context_refs.length > 0
          || Boolean(row.details.audience)
          || Boolean(row.details.notes)
        }
        optional
      >
        <ContextStep
          workspaceSlug={workspaceSlug}
          details={row.details}
          contextRefs={row.context_refs}
          disabled={isLocked}
          onChangeDetails={(details) => update({ details })}
          onChangeContextRefs={(refs) => update({ context_refs: refs })}
        />
      </StepCard>

      <StepCard
        index={6}
        title={t('ai.imageWizard.steps.review.title')}
        completed={row.brief_status === 'approved' || row.brief_status === 'ready'}
      >
        <ReviewBriefStep
          briefVersions={row.brief_versions}
          briefStatus={row.brief_status}
          generating={busyAction === 'brief'}
          approving={busyAction === 'approve'}
          hasInput={hasInput}
          onGenerateBrief={handleGenerateBrief}
          onApprove={handleApprove}
        />
      </StepCard>

      {row.brief_status === 'approved' || row.image_status !== 'idle' ? (
        <StepCard
          index={7}
          title={t('ai.imageWizard.steps.generate.title')}
          completed={row.image_status === 'succeeded'}
        >
          <GenerateStatusPanel
            row={row}
            downloadUrl={downloadUrl}
            onClone={() => navigate(galleryHref)}
          />
        </StepCard>
      ) : null}
    </div>
  );
}

interface StepCardProps {
  index: number;
  title: string;
  completed?: boolean;
  optional?: boolean;
  children: React.ReactNode;
}

function StepCard({ index, title, completed, optional, children }: StepCardProps) {
  const { t } = useTranslation('apps');
  return (
    <section className="rounded-md border border-app-border bg-app-surface p-4">
      <header className="mb-3 flex items-center gap-2">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
            completed
              ? 'bg-app-accent text-white'
              : 'bg-app-surface-hover text-app-ink/60'
          }`}
        >
          {completed ? <CheckCircle2 size={12} /> : index}
        </span>
        <h2 className="app-text-heading-3 text-app-ink">{title}</h2>
        {optional ? (
          <span className="app-text-caption text-app-ink/40">
            {t('ai.imageWizard.steps.optional')}
          </span>
        ) : null}
      </header>
      {children}
    </section>
  );
}

interface GenerateStatusPanelProps {
  row: ImageGeneration;
  downloadUrl: string | null;
  onClone: () => void;
}

function GenerateStatusPanel({ row, downloadUrl, onClone }: GenerateStatusPanelProps) {
  const { t } = useTranslation('apps');
  if (row.image_status === 'failed') {
    return (
      <div className="space-y-2">
        <p className="app-text-body text-[var(--ui-color-danger)]">
          {t('ai.imageWizard.steps.generate.failed')}
        </p>
        {row.failure_reason ? (
          <pre className="app-text-caption whitespace-pre-wrap text-app-ink/60">
            {row.failure_reason}
          </pre>
        ) : null}
      </div>
    );
  }
  if (row.image_status === 'succeeded' && downloadUrl) {
    return (
      <div className="space-y-3">
        <img
          src={downloadUrl}
          alt={t('ai.imageWizard.steps.generate.altText')}
          className="max-h-[480px] w-full rounded-md border border-app-border object-contain"
        />
        <div className="flex flex-wrap gap-2">
          <a
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
          >
            <Download size={14} />
            {t('ai.imageWizard.steps.generate.download')}
          </a>
          <button
            type="button"
            onClick={onClone}
            className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
          >
            <RefreshCw size={14} />
            {t('ai.imageWizard.steps.generate.cloneAction')}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-app-ink/60">
      <Loader2 size={14} className="animate-spin" />
      <span className="app-text-control-sm">
        {row.image_status === 'queued'
          ? t('ai.imageWizard.steps.generate.queued')
          : t('ai.imageWizard.steps.generate.running')}
      </span>
    </div>
  );
}

export default ImageWizardView;
