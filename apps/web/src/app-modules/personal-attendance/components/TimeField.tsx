import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { from12h, to12h, type Meridiem } from '../lib/attendance-format';
import { useAttendanceLabels } from '../lib/attendance-labels';

/**
 * 시각 입력 — [오전/오후] [시 : 분] 두 칸 구성.
 * 뒤 칸을 누르면 시/분 스크롤 휠이 열리고, 가운데 줄이 선택값이다.
 * 값은 항상 24시간제 "HH:mm" 으로 주고받는다.
 */

const ITEM_PX = 32; // 휠 항목 높이 (h-8)
const WHEEL_PX = 128; // 휠 보이는 높이 — 열려도 한 화면을 넘지 않도록 4줄
const PAD_PX = (WHEEL_PX - ITEM_PX) / 2; // 첫/마지막 항목도 가운데 올 수 있도록

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1);

function WheelColumn({
  items,
  value,
  onSelect,
  ariaLabel,
}: {
  items: number[];
  value: number;
  onSelect: (v: number) => void;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  // 열릴 때 선택값을 가운데로
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const idx = items.indexOf(value);
    if (idx >= 0) el.scrollTop = idx * ITEM_PX;
  }, [items, value]);

  return (
    <div
      ref={ref}
      role="listbox"
      aria-label={ariaLabel}
      className="pa-noscrollbar w-14 snap-y snap-mandatory overflow-y-auto"
      style={{ height: WHEEL_PX, paddingTop: PAD_PX, paddingBottom: PAD_PX }}
    >
      {items.map((n) => {
        const selected = n === value;
        return (
          <button
            key={n}
            type="button"
            role="option"
            aria-selected={selected}
            onClick={() => onSelect(n)}
            className={`flex h-8 w-full snap-center items-center justify-center text-base tabular-nums transition ${
              selected ? 'font-bold text-app-ink' : 'text-app-ink/25 hover:text-app-ink/60'
            }`}
          >
            {String(n).padStart(2, '0')}
          </button>
        );
      })}
    </div>
  );
}

export function TimeField({
  id,
  label,
  value,
  onChange,
  minuteStep = 10,
}: {
  id: string;
  label: string;
  value: string; // "HH:mm"
  onChange: (next: string) => void;
  minuteStep?: number;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const labels = useAttendanceLabels();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const { meridiem, hour12, minute } = to12h(value);

  const minutes = Array.from({ length: Math.ceil(60 / minuteStep) }, (_, i) => i * minuteStep);
  // 저장된 값이 step 에 안 맞으면(과거 데이터 등) 그 값도 선택 가능하도록 끼워 넣는다
  if (!minutes.includes(minute)) minutes.push(minute);
  minutes.sort((a, b) => a - b);

  // 바깥 클릭 / ESC 로 닫기
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const set = (next: { m?: Meridiem; h?: number; min?: number }) => {
    onChange(from12h(next.m ?? meridiem, next.h ?? hour12, next.min ?? minute));
  };

  return (
    <div ref={wrapRef} className="relative">
      <span className="mb-1 block text-xs font-medium text-app-ink-muted">{label}</span>
      <div className="flex gap-2">
        {/* 앞 칸 — 오전/오후 */}
        <select
          id={`${id}-meridiem`}
          aria-label={t('apps:personalAttendance.field.meridiemSelect', { label })}
          value={meridiem}
          onChange={(e) => set({ m: e.target.value as Meridiem })}
          className="w-20 rounded-lg border border-app-border bg-app-bg px-2 py-2 text-sm text-app-ink outline-none transition focus:ring-2 focus:ring-app-accent/40"
        >
          <option value="AM">{labels.meridiem('AM')}</option>
          <option value="PM">{labels.meridiem('PM')}</option>
        </select>

        {/* 뒤 칸 — 시 : 분 */}
        <button
          id={id}
          type="button"
          aria-label={t('apps:personalAttendance.field.timeSelect', { label })}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border bg-app-bg px-3 py-2 tabular-nums transition ${
            open ? 'border-app-accent ring-2 ring-app-accent/40' : 'border-app-border hover:bg-app-surface-hover'
          }`}
        >
          <span className="text-base font-semibold text-app-ink">{String(hour12).padStart(2, '0')}</span>
          <span className="text-base text-app-ink-muted">:</span>
          <span className="text-base font-semibold text-app-ink">{String(minute).padStart(2, '0')}</span>
        </button>
      </div>

      {/* 휠은 인라인으로 펼친다 — 폼이 스크롤 컨테이너라 absolute 패널은 잘린다 */}
      {open ? (
        <div className="mt-1 rounded-xl border border-app-border bg-app-surface p-1 shadow-sm">
          <style>{`.pa-noscrollbar::-webkit-scrollbar{display:none}.pa-noscrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
          <div className="relative flex items-center justify-center">
            {/* 가운데 선택 밴드 */}
            <span
              className="pointer-events-none absolute inset-x-1 z-0 rounded-md bg-app-accent-weak"
              style={{ top: PAD_PX, height: ITEM_PX }}
            />
            <div className="relative z-10 flex items-center gap-1">
              <WheelColumn
                items={HOURS}
                value={hour12}
                onSelect={(h) => set({ h })}
                ariaLabel={t('apps:personalAttendance.field.hourWheel', { label })}
              />
              <span className="text-base text-app-ink-muted">:</span>
              <WheelColumn
                items={minutes}
                value={minute}
                onSelect={(min) => set({ min })}
                ariaLabel={t('apps:personalAttendance.field.minuteWheel', { label })}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="mt-1 w-full rounded-md py-1.5 text-xs font-semibold text-app-accent transition hover:bg-app-surface-hover"
          >
            {t('common:actions.confirm')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
