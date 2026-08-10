import { CheckCircle2, MailPlus, RefreshCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  MailAccount,
  MailAccountConnectionPayload,
} from '../api/mail-api';
import { AccountFields } from './AccountFields';
import { accountToForm, actionButtonClassName } from './mail-view-model';

export function MailSettingsView({
  accounts,
  accountEditForms,
  accountForm,
  busy,
  onChangeAccountForm,
  onChangeAccountEditForm,
  onCreateAccount,
  onSyncAccount,
  onUpdateAccount,
}: {
  accounts: MailAccount[];
  accountEditForms: Record<string, MailAccountConnectionPayload>;
  accountForm: MailAccountConnectionPayload;
  busy: boolean;
  onChangeAccountForm: (next: MailAccountConnectionPayload) => void;
  onChangeAccountEditForm: (
    accountId: string,
    next: MailAccountConnectionPayload,
  ) => void;
  onCreateAccount: () => void;
  onSyncAccount: (accountId: string) => Promise<void>;
  onUpdateAccount: (accountId: string) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <main className="min-h-0 flex-1 overflow-auto p-5">
      <div className="mx-auto grid max-w-5xl gap-5">
        <div>
          <h2 className="app-text-title-md">
            {t('mail.account.settingsTitle')}
          </h2>
          <p className="app-text-body mt-1 text-app-ink/60">
            {t('mail.account.settingsOverview')}
          </p>
        </div>
        <section className="grid gap-3">
          <h3 className="app-text-title-sm">{t('mail.accounts')}</h3>
          {accounts.length === 0 ? (
            <div className="rounded-md border border-dashed border-app-border bg-app-surface p-4">
              <p className="app-text-body text-app-ink/60">
                {t('mail.account.setupDescription')}
              </p>
            </div>
          ) : (
            accounts.map((account) => {
              const editForm =
                accountEditForms[account.id] ?? accountToForm(account);
              return (
                <section
                  className="rounded-md border border-app-border bg-app-surface p-4"
                  key={account.id}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="truncate app-text-control">
                        {account.account_label || account.email_address}
                      </h4>
                      {account.account_label ? (
                        <p className="truncate app-text-caption text-app-ink/50">
                          {account.email_address}
                        </p>
                      ) : null}
                      <div className="mt-1 flex flex-wrap items-center gap-2 app-text-caption text-app-ink/50">
                        <span>
                          {t(`mail.status.${account.status}`, {
                            defaultValue: account.status,
                          })}
                        </span>
                        {account.last_sync_at ? (
                          <span>
                            +{account.last_sync_new_count} / ~
                            {account.last_sync_updated_count} / -
                            {account.last_sync_deleted_count}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <button
                      className={actionButtonClassName}
                      disabled={busy}
                      onClick={() => void onSyncAccount(account.id)}
                      title={t('mail.actions.sync')}
                      type="button"
                    >
                      <RefreshCcw size={15} />
                      <span>{t('mail.actions.sync')}</span>
                    </button>
                  </div>
                  {account.last_error ? (
                    <p className="mt-3 app-text-caption text-app-danger">
                      {account.last_error}
                    </p>
                  ) : null}
                  <p className="mt-3 app-text-caption text-app-ink/55">
                    {t('mail.account.settingsDescription')}
                  </p>
                  <div className="mt-4">
                    <AccountFields
                      copySharedCredentials={false}
                      form={editForm}
                      passwordPlaceholder={t(
                        'mail.account.keepExistingPassword',
                      )}
                      onChange={(next) =>
                        onChangeAccountEditForm(account.id, next)
                      }
                    />
                  </div>
                  <button
                    className={`${actionButtonClassName} mt-3`}
                    disabled={busy}
                    onClick={() => onUpdateAccount(account.id)}
                    type="button"
                  >
                    <CheckCircle2 size={16} />
                    <span>{t('mail.actions.save')}</span>
                  </button>
                </section>
              );
            })
          )}
        </section>
        <section className="rounded-md border border-app-border bg-app-surface p-4">
          <h3 className="app-text-title-sm">{t('mail.account.setupTitle')}</h3>
          <p className="app-text-caption mt-1 text-app-ink/55">
            {t('mail.account.setupDescription')}
          </p>
          <div className="mt-4">
            <AccountFields form={accountForm} onChange={onChangeAccountForm} />
          </div>
          <button
            className={`${actionButtonClassName} mt-3`}
            disabled={busy}
            onClick={onCreateAccount}
            type="button"
          >
            <MailPlus size={16} />
            <span>{t('mail.account.connect')}</span>
          </button>
        </section>
      </div>
    </main>
  );
}
