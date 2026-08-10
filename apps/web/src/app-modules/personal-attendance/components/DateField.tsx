import { useRef } from 'react';
import { CalendarDays } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * 날짜 입력 — 테두리는 입력 칸에서 끝나고, 달력 아이콘은 그 바깥에 크게 놓는다.
 * 브라우저 기본 달력 아이콘은 숨기고 옆 버튼이 showPicker() 로 대신 연다.
 */
export function DateField({
  id,
  label,
  value,
  onChange,
  min,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  min?: string;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const ref = useRef<HTMLInputElement>(null);

  const openPicker = () => {
    const el = ref.current;
    if (!el) return;
    // showPicker 미지원 브라우저는 포커스만
    if (typeof el.showPicker === 'function') el.showPicker();
    else el.focus();
  };

  return (
    <div>
      <style>{`.pa-date::-webkit-calendar-picker-indicator{display:none}.pa-date::-webkit-inner-spin-button{display:none}`}</style>
      <label className="mb-1 block text-xs font-medium text-app-ink-muted" htmlFor={id}>
        {label}
      </label>
      <div className="flex items-center gap-1.5">
        <input
          ref={ref}
          id={id}
          type="date"
          value={value}
          min={min}
          onChange={(e) => onChange(e.target.value)}
          className="pa-date min-w-0 flex-1 rounded-lg border border-app-border bg-app-bg px-3 py-2 text-sm tabular-nums text-app-ink outline-none transition focus:ring-2 focus:ring-app-accent/40"
        />
        <button
          type="button"
          onClick={openPicker}
          aria-label={t('apps:personalAttendance.field.openCalendar', { label })}
          className="shrink-0 rounded-lg p-1 text-app-ink-muted transition hover:bg-app-surface-hover hover:text-app-accent"
        >
          <CalendarDays className="size-7" />
        </button>
      </div>
    </div>
  );
}
