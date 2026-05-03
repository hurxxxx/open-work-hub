import { useRef, useState } from 'react';
import { Loader2, Trash2, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  ReferenceImageRef,
  ReferenceImageRole,
} from '../../../api/image-wizard-api';
import {
  MAX_REFERENCE_IMAGES,
  REFERENCE_ROLE_OPTIONS,
  type ReferenceRoleId,
} from '../wizard-options';

interface ReferenceImagesStepProps {
  references: ReferenceImageRef[];
  uploading: boolean;
  disabled?: boolean;
  onUpload: (file: File, role: ReferenceImageRole) => Promise<void>;
  onDelete: (storageKey: string) => Promise<void>;
}

export function ReferenceImagesStep({
  references,
  uploading,
  disabled = false,
  onUpload,
  onDelete,
}: ReferenceImagesStepProps) {
  const { t } = useTranslation('apps');
  const [pendingRole, setPendingRole] = useState<ReferenceRoleId>('style');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function handlePickFile() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await onUpload(file, pendingRole);
  }

  const isAtCap = references.length >= MAX_REFERENCE_IMAGES;

  return (
    <div className="space-y-3">
      <p className="app-text-caption text-app-ink/60">
        {t('ai.imageWizard.steps.referenceImages.description', {
          count: MAX_REFERENCE_IMAGES,
        })}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.referenceImages.roleLabel')}
          </label>
          <select
            value={pendingRole}
            disabled={disabled}
            onChange={(event) => setPendingRole(event.target.value as ReferenceRoleId)}
            className="app-text-body rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
          >
            {REFERENCE_ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {t(`ai.imageWizard.referenceImages.roles.${role}`)}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={handlePickFile}
          disabled={disabled || uploading || isAtCap}
          className="flex items-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-4 py-2 app-text-control-sm text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
        >
          {uploading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Upload size={14} />
          )}
          {isAtCap
            ? t('ai.imageWizard.referenceImages.fullHint')
            : t('ai.imageWizard.referenceImages.uploadAction')}
        </button>
        <input
          type="file"
          ref={fileInputRef}
          accept="image/*"
          disabled={disabled}
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

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
                disabled={disabled}
                onClick={() => onDelete(ref.storage_key)}
                className="flex items-center gap-1 app-text-caption text-app-ink/40 hover:text-[var(--ui-color-danger)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Trash2 size={12} />
                {t('common:actions.delete')}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ReferenceImagesStep;
