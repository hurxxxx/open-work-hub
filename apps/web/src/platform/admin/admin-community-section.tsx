import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Hash, Plus, Trash2 } from 'lucide-react';

import { Button } from '@open-work-hub/ui';

import { CommunityMarkdownEditor } from '@/src/platform/community/CommunityMarkdownEditor';

import {
  createCommunityAdminChannel,
  deleteCommunityAdminChannel,
  listCommunityAdminChannels,
  updateCommunityAdminChannel,
  type AdminCommunityChannelItem,
} from './admin-api';
import {
  buildCommunityChannelPayload,
  sanitizeCommunityChannelKeyInput,
  type CommunityChannelDraft,
} from './community-channel-form-model';
import {
  FORM_FIELD_CLASS as fieldClassName,
  SectionMessage,
  getErrorMessage,
} from './admin-shared';

const EMPTY_COMMUNITY_CHANNEL_DRAFT: CommunityChannelDraft = {
  key: '',
  name: '',
  description: '',
  position: '0',
  active: true,
  readOnly: false,
  forceAnonymous: false,
  adminOnlyContent: false,
  templateTitle: '',
  templateBody: '',
};

function communityChannelDraftFrom(
  channel: AdminCommunityChannelItem,
): CommunityChannelDraft {
  return {
    key: channel.key,
    name: channel.name,
    description: channel.description,
    position: String(channel.position),
    active: channel.active,
    readOnly: channel.readOnly,
    forceAnonymous: channel.forceAnonymous,
    adminOnlyContent: channel.adminOnlyContent,
    templateTitle: channel.templateTitle,
    templateBody: channel.templateBody,
  };
}
export function CommunitySection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const [channels, setChannels] = useState<AdminCommunityChannelItem[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<CommunityChannelDraft>(
    EMPTY_COMMUNITY_CHANNEL_DRAFT,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);

  const selectedChannel = useMemo(
    () => channels.find((channel) => channel.key === selectedKey) ?? null,
    [channels, selectedKey],
  );

  const flashSuccess = useCallback((text: string) => {
    setError(null);
    setMessage(text);
    window.setTimeout(() => setMessage(null), 3500);
  }, []);

  const flashError = useCallback((text: string) => {
    setMessage(null);
    setError(text);
  }, []);

  const loadChannels = useCallback(
    async (preserveKey?: string | null) => {
      setLoading(true);
      try {
        const response = await listCommunityAdminChannels(token);
        setChannels(response.channels);
        const nextKey =
          preserveKey &&
          response.channels.some((channel) => channel.key === preserveKey)
            ? preserveKey
            : (response.channels[0]?.key ?? null);
        setSelectedKey(nextKey);
        const nextChannel =
          response.channels.find((channel) => channel.key === nextKey) ?? null;
        setDraft(
          nextChannel
            ? communityChannelDraftFrom(nextChannel)
            : EMPTY_COMMUNITY_CHANNEL_DRAFT,
        );
      } catch (caughtError) {
        flashError(
          getErrorMessage(caughtError, t('admin.console.community.loadFailed')),
        );
      } finally {
        setLoading(false);
      }
    },
    [flashError, t, token],
  );

  useEffect(() => {
    void loadChannels();
  }, [loadChannels]);

  const startCreate = useCallback(() => {
    setSelectedKey(null);
    setDraft({
      ...EMPTY_COMMUNITY_CHANNEL_DRAFT,
      position: String(channels.length),
    });
    setError(null);
    setMessage(null);
  }, [channels.length]);

  const selectChannel = useCallback((channel: AdminCommunityChannelItem) => {
    setSelectedKey(channel.key);
    setDraft(communityChannelDraftFrom(channel));
    setError(null);
    setMessage(null);
  }, []);

  const saveChannel = useCallback(async () => {
    const payload = buildCommunityChannelPayload(draft);
    if (!payload) {
      flashError(t('admin.console.community.required'));
      return;
    }
    setSaving(true);
    try {
      const saved = selectedKey
        ? await updateCommunityAdminChannel(token, selectedKey, payload)
        : await createCommunityAdminChannel(token, payload);
      await loadChannels(saved.key);
      flashSuccess(
        selectedKey
          ? t('admin.console.community.saved', { name: saved.name })
          : t('admin.console.community.created', { name: saved.name }),
      );
    } catch (caughtError) {
      flashError(
        getErrorMessage(caughtError, t('admin.console.community.saveFailed')),
      );
    } finally {
      setSaving(false);
    }
  }, [draft, flashError, flashSuccess, loadChannels, selectedKey, t, token]);

  const deleteChannel = useCallback(
    async (channel: AdminCommunityChannelItem) => {
      if (
        !window.confirm(
          t('admin.console.community.confirmDelete', { name: channel.name }),
        )
      ) {
        return;
      }
      setDeletingKey(channel.key);
      try {
        await deleteCommunityAdminChannel(token, channel.key);
        await loadChannels(null);
        flashSuccess(
          t('admin.console.community.deleted', { name: channel.name }),
        );
      } catch (caughtError) {
        flashError(
          getErrorMessage(
            caughtError,
            t('admin.console.community.deleteFailed'),
          ),
        );
      } finally {
        setDeletingKey(null);
      }
    },
    [flashError, flashSuccess, loadChannels, t, token],
  );

  return (
    <div className="space-y-3">
      <SectionMessage error={error} message={message} />

      <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
        <aside className="overflow-hidden rounded-md border border-app-border bg-app-bg">
          <div className="flex items-center justify-between gap-2 border-b border-app-border px-3 py-2">
            <h2 className="app-text-overline uppercase text-app-ink/60">
              {t('admin.console.community.channels')} · {channels.length}
            </h2>
            <button
              aria-label={t('admin.console.community.newChannel')}
              className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
              onClick={startCreate}
              type="button"
            >
              <Plus size={14} />
            </button>
          </div>
          <div className="min-h-[320px]">
            {loading ? (
              <div className="px-3 py-8 text-center app-text-body-sm text-app-ink/45">
                {t('admin.console.community.loading')}
              </div>
            ) : channels.length === 0 ? (
              <div className="px-3 py-8 text-center app-text-body-sm text-app-ink/45">
                {t('admin.console.community.empty')}
              </div>
            ) : (
              channels.map((channel) => (
                <button
                  className={`flex w-full items-center justify-between gap-2 border-b border-app-border/70 px-3 py-2 text-left transition-colors ${
                    selectedKey === channel.key
                      ? 'bg-app-accent/10 text-app-ink'
                      : 'text-app-ink/75 hover:bg-app-surface-sidebar'
                  }`}
                  key={channel.key}
                  onClick={() => selectChannel(channel)}
                  type="button"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Hash size={14} className="shrink-0 text-app-ink/45" />
                    <span className="min-w-0 truncate app-text-body-sm font-medium">
                      {channel.name}
                    </span>
                  </span>
                  <span className="shrink-0 app-text-micro text-app-ink/45">
                    {channel.readOnly
                      ? t('admin.console.community.readOnly')
                      : channel.active
                        ? t('admin.console.community.active')
                        : t('admin.console.community.inactive')}
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="rounded-md border border-app-border bg-app-bg p-4">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="app-text-body font-semibold text-app-ink">
                {selectedChannel
                  ? t('admin.console.community.editTitle')
                  : t('admin.console.community.createTitle')}
              </h2>
              <p className="mt-1 app-text-body-sm text-app-ink/55">
                {t('admin.console.community.formDescription')}
              </p>
            </div>
            <Button onClick={startCreate} variant="secondary">
              <Plus size={15} />
              {t('admin.console.community.newChannel')}
            </Button>
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_120px]">
            <label className="space-y-1">
              <span className="app-text-caption text-app-ink/60">
                {t('admin.console.community.key')}
              </span>
              <input
                className={fieldClassName}
                placeholder={t('admin.console.community.keyPlaceholder')}
                value={draft.key}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    key: sanitizeCommunityChannelKeyInput(event.target.value),
                  }))
                }
              />
            </label>
            <label className="space-y-1">
              <span className="app-text-caption text-app-ink/60">
                {t('admin.console.community.name')}
              </span>
              <input
                className={fieldClassName}
                placeholder={t('admin.console.community.namePlaceholder')}
                value={draft.name}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
              />
            </label>
            <label className="space-y-1">
              <span className="app-text-caption text-app-ink/60">
                {t('admin.console.community.position')}
              </span>
              <input
                className={fieldClassName}
                inputMode="numeric"
                min={0}
                type="number"
                value={draft.position}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    position: event.target.value,
                  }))
                }
              />
            </label>
          </div>

          <label className="mt-3 block space-y-1">
            <span className="app-text-caption text-app-ink/60">
              {t('admin.console.community.descriptionLabel')}
            </span>
            <textarea
              className={`${fieldClassName} min-h-[88px] resize-y`}
              placeholder={t('admin.console.community.descriptionPlaceholder')}
              value={draft.description}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
            />
          </label>

          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <label className="inline-flex items-center gap-2 app-text-body-sm text-app-ink/70">
              <input
                checked={draft.readOnly}
                className="h-4 w-4 accent-app-accent"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    readOnly: event.target.checked,
                  }))
                }
                type="checkbox"
              />
              {t('admin.console.community.readOnly')}
            </label>
            <label className="inline-flex items-center gap-2 app-text-body-sm text-app-ink/70">
              <input
                checked={draft.forceAnonymous}
                className="h-4 w-4 accent-app-accent"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    forceAnonymous: event.target.checked,
                  }))
                }
                type="checkbox"
              />
              {t('admin.console.community.forceAnonymous')}
            </label>
            <label className="inline-flex items-center gap-2 app-text-body-sm text-app-ink/70">
              <input
                checked={draft.adminOnlyContent}
                className="h-4 w-4 accent-app-accent"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    adminOnlyContent: event.target.checked,
                  }))
                }
                type="checkbox"
              />
              {t('admin.console.community.adminOnlyContent')}
            </label>
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
            <label className="space-y-1">
              <span className="app-text-caption text-app-ink/60">
                {t('admin.console.community.templateTitle')}
              </span>
              <input
                className={fieldClassName}
                maxLength={240}
                placeholder={t(
                  'admin.console.community.templateTitlePlaceholder',
                )}
                value={draft.templateTitle}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    templateTitle: event.target.value,
                  }))
                }
              />
            </label>
            <div className="space-y-1">
              <span className="app-text-caption text-app-ink/60">
                {t('admin.console.community.templateBody')}
              </span>
              <CommunityMarkdownEditor
                ariaLabel={t('admin.console.community.templateBody')}
                compact
                minHeight={220}
                onChange={(templateBody) =>
                  setDraft((current) => ({
                    ...current,
                    templateBody,
                  }))
                }
                placeholder={t(
                  'admin.console.community.templateBodyPlaceholder',
                )}
                value={draft.templateBody}
              />
            </div>
          </div>

          <label className="mt-3 inline-flex items-center gap-2 app-text-body-sm text-app-ink/70">
            <input
              checked={draft.active}
              className="h-4 w-4 accent-app-accent"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  active: event.target.checked,
                }))
              }
              type="checkbox"
            />
            {t('admin.console.community.activeToggle')}
          </label>

          <div className="mt-5 flex items-center justify-between gap-3">
            {selectedChannel ? (
              <Button
                className="text-app-danger-text hover:bg-app-danger-bg"
                disabled={Boolean(deletingKey) || saving}
                onClick={() => void deleteChannel(selectedChannel)}
                variant="ghost"
              >
                <Trash2 size={15} />
                {deletingKey === selectedChannel.key
                  ? t('admin.console.community.deleting')
                  : t('admin.console.community.delete')}
              </Button>
            ) : (
              <span />
            )}
            <Button
              disabled={saving}
              onClick={() => void saveChannel()}
              variant="primary"
            >
              {saving
                ? t('admin.console.community.saving')
                : t('admin.console.community.save')}
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
