import { Paperclip } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * 증빙 첨부 자리표시자.
 *
 * 신청 API와 commute-owned media link/cleanup 계약이 준비되기 전에는 공용 이미지
 * 업로드 API로 파일을 먼저 올리지 않는다. 앱은 기본 숨김 상태이며 실제 연동 MR에서
 * 허용 MIME, 용량, 개수와 실패 cleanup을 함께 구현한다.
 */
export function AttachmentField({
  label,
  hint,
}: {
  label?: string;
  hint?: string;
}) {
  const { t } = useTranslation('apps');

  return (
    <div>
      <span className="mb-1 block text-xs font-medium text-app-ink-muted">
        {label ?? t('personalAttendance.attachment.label')}
      </span>
      <button
        type="button"
        disabled
        className="flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-lg border border-dashed border-app-border bg-app-bg py-2 text-xs font-medium text-app-ink-muted opacity-60"
      >
        <Paperclip className="size-3.5" />
        {t('personalAttendance.attachment.unavailable')}
      </button>
      {hint ? <p className="mt-1 text-[11px] text-app-ink-muted">{hint}</p> : null}
    </div>
  );
}
