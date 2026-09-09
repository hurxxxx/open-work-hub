import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useConfirm, useFeedback } from '@open-work-hub/ui';
import { Link2, Unlink, Users } from 'lucide-react';
import type { PmsSpace } from '@/src/app-modules/pms/public-api';
import {
  deleteDocTarget,
  updateDocsCompanySharing,
  updateDocTarget,
  type DocsHubItem,
} from '../api/docs-api';
import { LocationPicker } from './LocationPicker';
import type { LocationOption } from './docs-view-model';

interface DocsPublicationControlsProps {
  token: string;
  doc: DocsHubItem;
  spaces: readonly Pick<PmsSpace, 'id' | 'name'>[];
  onUpdated: (doc: DocsHubItem) => void;
}

function DocsPublicationControlsContent({
  token,
  doc,
  spaces,
  onUpdated,
}: DocsPublicationControlsProps) {
  const { t } = useTranslation('apps');
  const { confirm, confirmDialog } = useConfirm();
  const feedback = useFeedback();
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  async function change(
    operation: () => Promise<DocsHubItem>,
    publishes: boolean,
  ) {
    if (!doc.can_share || busy) return;
    setBusy(true);
    try {
      if (
        publishes &&
        !(await confirm({
          title: t('shell:contentPublication.title'),
          description: t('shell:contentPublication.confirm'),
          confirmLabel: t('common:actions.confirm'),
          cancelLabel: t('common:actions.cancel'),
        }))
      )
        return;
      if (!active.current) return;
      const updated = await operation();
      if (!active.current) return;
      onUpdated(updated);
      feedback.success(t('docs.share.publicationSaved'));
    } catch (error) {
      if (active.current) {
        feedback.error(
          error instanceof Error
            ? error.message
            : t('docs.share.publicationFailed'),
        );
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }

  const target = doc.primary_target;
  const currentTarget = target
    ? target.app === 'pms' && target.type === 'space'
      ? `space:${target.id}`
      : 'current-target'
    : 'none';
  const targetOptions: LocationOption[] = spaces.map((space) => ({
    value: `space:${space.id}`,
    icon: Users,
    title: space.name,
    desc: t('docs.share.targetAccessDescription'),
  }));
  if (
    target &&
    !targetOptions.some((option) => option.value === currentTarget)
  ) {
    targetOptions.unshift({
      value: currentTarget,
      icon: Link2,
      title: doc.target_label,
      desc: t('docs.share.currentPrimaryTarget'),
    });
  }
  targetOptions.push({
    value: 'none',
    icon: Unlink,
    title: t('docs.share.noPrimaryTarget'),
    desc: t('docs.share.noPrimaryTargetDescription'),
  });

  return (
    <section className="space-y-3 rounded-lg border border-app-border bg-app-bg p-4">
      {confirmDialog}
      <h3 className="app-text-control text-app-ink">
        {t('docs.share.whoCanAccess')}
      </h3>
      <p className="app-text-caption text-app-ink/55">
        {t('docs.share.visibilityDescription')}
      </p>
      <label className="flex items-center gap-2 app-text-control-sm">
        <input
          type="checkbox"
          checked={doc.company_visible}
          disabled={busy || !doc.can_share}
          onChange={(event) => {
            const enabled = event.target.checked;
            void change(
              () => updateDocsCompanySharing(token, doc.id, enabled, enabled),
              enabled,
            );
          }}
        />
        {t('docs.share.companyAudience')}
      </label>
      <p className="app-text-caption text-app-ink/55">
        {t('docs.location.companyDesc')}
      </p>
      <h4 className="app-text-control-sm text-app-ink">
        {t('docs.share.primaryTarget')}
      </h4>
      <LocationPicker
        value={currentTarget}
        options={targetOptions}
        busy={busy || !doc.can_share}
        onChange={(value) => {
          if (value === currentTarget) return;
          if (value === 'none') {
            void change(() => deleteDocTarget(token, doc.id), false);
          } else if (value.startsWith('space:')) {
            void change(
              () =>
                updateDocTarget(token, doc.id, {
                  app: 'pms',
                  type: 'space',
                  id: value.slice('space:'.length),
                  company_admin_read_acknowledged: true,
                }),
              true,
            );
          }
        }}
      />
      {!doc.can_share ? (
        <p className="app-text-caption text-app-ink/55">
          {t('docs.share.manageOnlyNotice')}
        </p>
      ) : null}
    </section>
  );
}

export function DocsPublicationControls(props: DocsPublicationControlsProps) {
  return (
    <DocsPublicationControlsContent
      key={JSON.stringify([props.token, props.doc.id, props.doc.can_share])}
      {...props}
    />
  );
}
