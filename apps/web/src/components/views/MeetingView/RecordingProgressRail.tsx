import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';

import type { MeetingRecording } from '@/src/domains/meeting/meeting-api';

const STAGES = [
  { key: 'pending', label: '업로드' },
  { key: 'transcribing', label: '음성인식' },
  { key: 'summarizing', label: '회의록 정리' },
  { key: 'generating_doc', label: '문서 생성' },
  { key: 'done', label: '완료' },
] as const;

function stageIndex(status: string): number {
  const index = STAGES.findIndex((stage) => stage.key === status);
  if (index >= 0) return index;
  if (status === 'failed') return 3;
  return 0;
}

export function RecordingProgressRail({
  recording,
  onRetry,
}: {
  recording: MeetingRecording;
  onRetry?: () => void;
}) {
  const currentIndex = stageIndex(recording.transcription_status);
  const active = recording.transcription_status !== 'failed' && recording.transcription_status !== 'done';
  return (
    <div className="space-y-2" aria-live="polite">
      <div className="flex items-center gap-2">
        {STAGES.map((stage, index) => {
          const done = index < currentIndex || recording.transcription_status === 'done';
          const current = index === currentIndex && active;
          return (
            <div key={stage.key} className="flex flex-1 items-center gap-2">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] ${
                  done
                    ? 'border-app-accent bg-app-accent text-white'
                    : current
                      ? 'border-app-accent text-app-accent'
                      : 'border-app-border text-app-ink/40'
                }`}
              >
                {done ? <CheckCircle2 size={12} /> : current ? <Loader2 size={12} className="animate-spin" /> : index + 1}
              </div>
              {index < STAGES.length - 1 ? (
                <div className={`h-px flex-1 ${done ? 'bg-app-accent' : 'bg-app-border'}`} />
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/60">
          {recording.transcription_status === 'failed'
            ? '회의록 생성에 실패했습니다. 원본 음성은 그대로 유지됩니다.'
            : `진행률 ${recording.progress_pct}% · 이 페이지를 닫아도 됩니다.`}
        </p>
        {recording.transcription_status === 'failed' && onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="app-text-caption inline-flex items-center gap-1 text-[var(--ui-color-danger)] hover:underline"
          >
            <AlertTriangle size={12} />
            다시 시도
          </button>
        ) : null}
      </div>
      {recording.failure_reason ? (
        <p className="app-text-caption text-[var(--ui-color-danger)]">{recording.failure_reason}</p>
      ) : null}
    </div>
  );
}
