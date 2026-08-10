import { useTranslation } from 'react-i18next';

import type { MailAccountConnectionPayload } from '../api/mail-api';
import {
  applyAccountFormChange,
  fieldClassName,
  type MailAccountFormChange,
} from './mail-view-model';

export function AccountFields({
  copySharedCredentials = true,
  form,
  passwordPlaceholder,
  onChange,
}: {
  copySharedCredentials?: boolean;
  form: MailAccountConnectionPayload;
  passwordPlaceholder?: string;
  onChange: (next: MailAccountConnectionPayload) => void;
}) {
  const { t } = useTranslation('apps');
  const set = (change: MailAccountFormChange) => {
    onChange(
      applyAccountFormChange(form, change, { copySharedCredentials }),
    );
  };
  const labelClassName = 'app-text-caption font-medium text-app-ink/55';
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.email')}</span>
        <input className={fieldClassName} value={form.email_address} onChange={(event) => set({ field: 'email_address', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.displayName')}</span>
        <input className={fieldClassName} value={form.display_name} onChange={(event) => set({ field: 'display_name', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.protocol')}</span>
        <select className="app-field-input" value={form.protocol} onChange={(event) => set({ field: 'protocol', value: event.target.value as 'imap' | 'pop3' })}>
          <option value="imap">{t('mail.account.protocolImap')}</option>
          <option value="pop3">{t('mail.account.protocolPop3')}</option>
        </select>
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.username')}</span>
        <input className={fieldClassName} value={form.incoming_username} onChange={(event) => set({ field: 'incoming_username', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.incomingHost')}</span>
        <input className={fieldClassName} value={form.incoming_host} onChange={(event) => set({ field: 'incoming_host', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.incomingPort')}</span>
        <input className={fieldClassName} min={1} max={65535} type="number" value={form.incoming_port} onChange={(event) => set({ field: 'incoming_port', value: Number(event.target.value) })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.incomingSecurity')}</span>
        <select className="app-field-input" value={form.incoming_security} onChange={(event) => set({ field: 'incoming_security', value: event.target.value as 'ssl' | 'starttls' | 'none' })}>
          <option value="ssl">{t('mail.account.securitySsl')}</option>
          <option value="starttls">{t('mail.account.securityStarttls')}</option>
          <option value="none">{t('mail.account.securityNone')}</option>
        </select>
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.incomingPassword')}</span>
        <input className={fieldClassName} placeholder={passwordPlaceholder} type="password" value={form.incoming_password} onChange={(event) => set({ field: 'incoming_password', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.smtpUsername')}</span>
        <input className={fieldClassName} value={form.smtp_username} onChange={(event) => set({ field: 'smtp_username', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.smtpHost')}</span>
        <input className={fieldClassName} value={form.smtp_host} onChange={(event) => set({ field: 'smtp_host', value: event.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.smtpPort')}</span>
        <input className={fieldClassName} min={1} max={65535} type="number" value={form.smtp_port} onChange={(event) => set({ field: 'smtp_port', value: Number(event.target.value) })} />
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.smtpSecurity')}</span>
        <select className="app-field-input" value={form.smtp_security} onChange={(event) => set({ field: 'smtp_security', value: event.target.value as 'ssl' | 'starttls' | 'none' })}>
          <option value="starttls">{t('mail.account.securityStarttls')}</option>
          <option value="ssl">{t('mail.account.securitySsl')}</option>
          <option value="none">{t('mail.account.securityNone')}</option>
        </select>
      </label>
      <label className="grid gap-1">
        <span className={labelClassName}>{t('mail.account.smtpPassword')}</span>
        <input className={fieldClassName} placeholder={passwordPlaceholder} type="password" value={form.smtp_password} onChange={(event) => set({ field: 'smtp_password', value: event.target.value })} />
      </label>
    </div>
  );
}
