import { useId, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Lightbulb, Loader2, Trash2, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  deleteReferenceImage,
  uploadReferenceImage,
  type LayoutPayload,
  type ReferenceImageRef,
  type ReferenceImageRole,
  type StylePayload,
} from '../../../api/image-wizard-api';
import {
  AspectThumb,
  LAYOUT_OPTIONS,
  LayoutWireframe,
  ASPECT_OPTIONS,
  type AspectId,
  type LayoutId,
} from '../layout-wireframes';
import { StylePickerSheet } from '../pickers/StylePickerSheet';

const ROLE_OPTIONS: ReferenceImageRole[] = ['style', 'composition', 'content'];
const PALETTE_OPTIONS = ['auto', 'brand', 'warm', 'cool', 'monochrome', 'vivid'] as const;
const BACKGROUND_OPTIONS = ['auto', 'transparent', 'white', 'dark'] as const;
const QUALITY_OPTIONS = ['auto', 'low', 'medium', 'high'] as const;
const MAX_REFS = 4;

interface Step3RefineProps {
  workspaceSlug: string;
  generationId: string;
  style: StylePayload;
  layout: LayoutPayload;
  references: ReferenceImageRef[];
  onChangeStyle: (next: StylePayload) => void;
  onChangeLayout: (next: LayoutPayload) => void;
  onReferencesChange: (next: ReferenceImageRef[]) => void;
}

export function Step3Refine({
  workspaceSlug,
  generationId,
  style,
  layout,
  references,
  onChangeStyle,
  onChangeLayout,
  onReferencesChange,
}: Step3RefineProps) {
  const { t } = useTranslation('apps');
  const roleSelectId = useId();
  const { token } = useAuth();
  const [openPanel, setOpenPanel] = useState<'style' | 'layout' | 'refs' | 'advanced' | null>(
    'style',
  );
  const [styleSheetOpen, setStyleSheetOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [pendingRole, setPendingRole] = useState<ReferenceImageRole>('style');

  function togglePanel(panel: 'style' | 'layout' | 'refs' | 'advanced') {
    setOpenPanel((current) => (current === panel ? null : panel));
  }

  const styleSummary =
    style.chips.length === 0
      ? t('ai.imageWizard.style.empty')
      : style.chips
          .slice(0, 3)
          .map((chip) =>
            t(`ai.imageWizard.style.chips.${chip}`, { defaultValue: chip }),
          )
          .join(' · ') + (style.chips.length > 3 ? ` +${style.chips.length - 3}` : '');

  const layoutSummary = `${
    layout.layout_id
      ? t(`ai.imageWizard.layout.layouts.${layout.layout_id}.label`, {
          defaultValue: layout.layout_id,
        })
      : t('ai.imageWizard.layout.unset')
  } · ${t(`ai.imageWizard.layout.aspect.${layout.aspect}`, { defaultValue: layout.aspect })}`;

  async function handleUpload(file: File) {
    if (!token) return;
    if (references.length >= MAX_REFS) return;
    setUploading(true);
    setUploadError(null);
    try {
      const ref = await uploadReferenceImage(
        token,
        workspaceSlug,
        generationId,
        file,
        pendingRole,
      );
      onReferencesChange([...references, ref]);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : t('ai.imageWizard.errors.uploadFailed'));
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(storageKey: string) {
    if (!token) return;
    try {
      await deleteReferenceImage(token, workspaceSlug, generationId, storageKey);
      onReferencesChange(references.filter((ref) => ref.storage_key !== storageKey));
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : t('ai.imageWizard.errors.deleteFailed'));
    }
  }

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h2 className="app-text-heading-2 text-app-ink">
          {t('ai.imageWizard.steps.step3.heading')}
        </h2>
        <p className="app-text-body text-app-ink/60">
          {t('ai.imageWizard.steps.step3.description')}
        </p>
      </header>

      <DisclosurePanel
        open={openPanel === 'style'}
        onToggle={() => togglePanel('style')}
        title={t('ai.imageWizard.steps.step3.stylePanel')}
        summary={styleSummary}
      >
        <button
          type="button"
          onClick={() => setStyleSheetOpen(true)}
          className="rounded-md border border-app-border bg-app-surface-sidebar px-4 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
        >
          {t('ai.imageWizard.style.openSheet')}
        </button>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SelectField
            label={t('ai.imageWizard.style.paletteLabel')}
            value={style.palette || 'auto'}
            options={PALETTE_OPTIONS}
            renderOption={(v) =>
              t(`ai.imageWizard.style.palette.${v}`, { defaultValue: v })
            }
            onChange={(value) => onChangeStyle({ ...style, palette: value })}
          />
        </div>
      </DisclosurePanel>

      <DisclosurePanel
        open={openPanel === 'layout'}
        onToggle={() => togglePanel('layout')}
        title={t('ai.imageWizard.steps.step3.layoutPanel')}
        summary={layoutSummary}
      >
        <div className="space-y-3">
          <div>
            <p className="mb-2 app-text-control-sm text-app-ink/60">
              {t('ai.imageWizard.layout.layoutLabel')}
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
              {LAYOUT_OPTIONS.map((id) => {
                const isSelected = layout.layout_id === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => onChangeLayout({ ...layout, layout_id: id as LayoutId })}
                    className={`flex flex-col items-center gap-1 rounded-md border p-2 transition-colors ${
                      isSelected
                        ? 'border-app-accent bg-app-accent/10 text-app-accent'
                        : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
                    }`}
                  >
                    <LayoutWireframe id={id as LayoutId} />
                    <span className="line-clamp-1 app-text-caption">
                      {t(`ai.imageWizard.layout.layouts.${id}.label`, { defaultValue: id })}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <p className="mb-2 app-text-control-sm text-app-ink/60">
              {t('ai.imageWizard.layout.aspectLabel')}
            </p>
            <div className="flex flex-wrap gap-2">
              {ASPECT_OPTIONS.map((aspect) => {
                const isSelected = layout.aspect === aspect;
                return (
                  <button
                    key={aspect}
                    type="button"
                    onClick={() => onChangeLayout({ ...layout, aspect: aspect as AspectId })}
                    className={`flex items-center gap-3 rounded-md border px-3 py-2 transition-colors ${
                      isSelected
                        ? 'border-app-accent bg-app-accent/10 text-app-accent'
                        : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
                    }`}
                  >
                    <AspectThumb id={aspect as AspectId} />
                    <span className="app-text-control-sm">
                      {t(`ai.imageWizard.layout.aspect.${aspect}`, { defaultValue: aspect })}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </DisclosurePanel>

      <DisclosurePanel
        open={openPanel === 'refs'}
        onToggle={() => togglePanel('refs')}
        title={t('ai.imageWizard.steps.step3.refsPanel')}
        summary={t('ai.imageWizard.referenceImages.countSummary', {
          count: references.length,
          max: MAX_REFS,
        })}
      >
        {!generationId ? (
          <p className="app-text-caption text-app-ink/40">
            {t('ai.imageWizard.referenceImages.requiresGeneration')}
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="space-y-1">
                <label htmlFor={roleSelectId} className="app-text-control-sm text-app-ink/70">
                  {t('ai.imageWizard.referenceImages.roleLabel')}
                </label>
                <select
                  id={roleSelectId}
                  value={pendingRole}
                  onChange={(event) => setPendingRole(event.target.value as ReferenceImageRole)}
                  className="app-text-body rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                >
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>
                      {t(`ai.imageWizard.referenceImages.roles.${role}`)}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || references.length >= MAX_REFS}
                className="flex items-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-4 py-2 app-text-control-sm text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
              >
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                {references.length >= MAX_REFS
                  ? t('ai.imageWizard.referenceImages.fullHint')
                  : t('ai.imageWizard.referenceImages.uploadAction')}
              </button>
              <input
                type="file"
                ref={fileInputRef}
                accept="image/*"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = '';
                  if (file) void handleUpload(file);
                }}
                className="hidden"
              />
            </div>
            {uploadError ? (
              <p className="app-text-caption text-[var(--ui-color-danger)]">{uploadError}</p>
            ) : null}
            {references.length === 0 ? (
              <p className="app-text-caption text-app-ink/40">
                {t('ai.imageWizard.referenceImages.empty')}
              </p>
            ) : (
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {references.map((ref) => (
                  <li
                    key={ref.storage_key}
                    className="space-y-1 rounded-md border border-app-border bg-app-surface-sidebar p-2 text-app-ink"
                  >
                    <div className="flex h-20 items-center justify-center rounded bg-app-surface-hover text-app-ink/40">
                      <span className="app-text-control-sm">
                        {t(`ai.imageWizard.referenceImages.roles.${ref.role}`)}
                      </span>
                    </div>
                    <p
                      className="app-text-caption truncate text-app-ink/70"
                      title={ref.original_name}
                    >
                      {ref.original_name || ref.storage_key.split('/').pop()}
                    </p>
                    <button
                      type="button"
                      onClick={() => handleDelete(ref.storage_key)}
                      className="flex items-center gap-1 app-text-caption text-app-ink/40 hover:text-[var(--ui-color-danger)]"
                    >
                      <Trash2 size={12} />
                      {t('common:actions.delete')}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DisclosurePanel>

      <DisclosurePanel
        open={openPanel === 'advanced'}
        onToggle={() => togglePanel('advanced')}
        title={t('ai.imageWizard.steps.step3.advancedPanel')}
        summary={`${t(`ai.imageWizard.style.background.${style.background || 'auto'}`)} · ${t(
          `ai.imageWizard.style.quality.${style.quality || 'auto'}`,
        )}`}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SelectField
            label={t('ai.imageWizard.style.backgroundLabel')}
            value={style.background || 'auto'}
            options={BACKGROUND_OPTIONS}
            renderOption={(v) =>
              t(`ai.imageWizard.style.background.${v}`, { defaultValue: v })
            }
            onChange={(value) => onChangeStyle({ ...style, background: value })}
          />
          <SelectField
            label={t('ai.imageWizard.style.qualityLabel')}
            value={style.quality || 'auto'}
            options={QUALITY_OPTIONS}
            renderOption={(v) =>
              t(`ai.imageWizard.style.quality.${v}`, { defaultValue: v })
            }
            onChange={(value) => onChangeStyle({ ...style, quality: value })}
          />
        </div>
      </DisclosurePanel>

      <p className="flex items-start gap-2 rounded-md bg-app-accent/10 px-3 py-2 app-text-caption text-app-ink/70">
        <Lightbulb size={13} className="mt-0.5 shrink-0 text-app-accent" />
        <span>{t('ai.imageWizard.steps.step3.reassurance')}</span>
      </p>

      <StylePickerSheet
        open={styleSheetOpen}
        onClose={() => setStyleSheetOpen(false)}
        selectedChips={style.chips}
        onChange={(chips) => onChangeStyle({ ...style, chips })}
      />
    </div>
  );
}

interface DisclosurePanelProps {
  open: boolean;
  title: string;
  summary: string;
  onToggle: () => void;
  children: React.ReactNode;
}

function DisclosurePanel({ open, title, summary, onToggle, children }: DisclosurePanelProps) {
  return (
    <section className="rounded-md border border-app-border bg-app-surface">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2 min-w-0 text-app-ink">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="app-text-control-sm font-medium">{title}</span>
          <span className="app-text-caption text-app-ink/40 truncate">{summary}</span>
        </div>
      </button>
      {open ? <div className="border-t border-app-border px-4 py-3">{children}</div> : null}
    </section>
  );
}

interface SelectFieldProps {
  label: string;
  value: string;
  options: readonly string[];
  renderOption: (value: string) => string;
  onChange: (next: string) => void;
}

function SelectField({ label, value, options, renderOption, onChange }: SelectFieldProps) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="app-text-control-sm text-app-ink/70">{label}</label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {renderOption(option)}
          </option>
        ))}
      </select>
    </div>
  );
}

export default Step3Refine;
