import { useCallback, useEffect, useRef, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  AlertCircle,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Cloud,
  Download,
  Eye,
  ExternalLink,
  FileUp,
  FolderOpen,
  History,
  ImagePlus,
  LayoutGrid,
  Loader2,
  Lock,
  MessageSquare,
  Pencil,
  Projector,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from 'lucide-react';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  type PptFamily,
  type PptJobListItem,
  type PptJobStatus,
  type PptSlide,
  type PptSlidesSpec,
  PptGeneratorApiError,
  cancelPpt,
  downloadPptx,
  finalizePpt,
  generatePpt,
  getPptJobStatus,
  listPptFamilies,
  listPptJobs,
  sendPptChatEdit,
} from '../api/ppt-generator-api';
import { buildPptDownloadFilename } from './ppt-generator/download-filename';
import {
  buildPptAssistantJobPath,
  buildPptAssistantPath,
} from '../ppt-assistant-paths';
import { PptSlideRenderer } from './ppt-generator/PptSlideRenderer';
import {
  getTemplateSampleSlides,
  getTemplateStaticPreviews,
} from './ppt-generator/template-samples';

type Step = 'input' | 'progress' | 'result';
type PptInputSection = 'create' | 'templates' | 'materials' | 'guide';

const PPT_INPUT_SECTIONS: {
  id: PptInputSection;
  labelKey: string;
  descKey: string;
  icon: typeof Sparkles;
}[] = [
  {
    id: 'create',
    labelKey: 'ai.pptGenerator.sections.createLabel',
    descKey: 'ai.pptGenerator.sections.createDesc',
    icon: Sparkles,
  },
  {
    id: 'templates',
    labelKey: 'ai.pptGenerator.sections.templatesLabel',
    descKey: 'ai.pptGenerator.sections.templatesDesc',
    icon: LayoutGrid,
  },
  {
    id: 'materials',
    labelKey: 'ai.pptGenerator.sections.materialsLabel',
    descKey: 'ai.pptGenerator.sections.materialsDesc',
    icon: FolderOpen,
  },
  {
    id: 'guide',
    labelKey: 'ai.pptGenerator.sections.guideLabel',
    descKey: 'ai.pptGenerator.sections.guideDesc',
    icon: BookOpen,
  },
];

const PPT_JOB_STATUS_CLASS: Record<PptJobListItem['status'], string> = {
  pending: 'border-app-border bg-app-surface-sidebar text-app-ink/60',
  running: 'border-app-accent/30 bg-app-accent/10 text-app-accent',
  completed:
    'border-app-success-border bg-app-success-bg text-app-success-text',
  error: 'border-app-danger-border bg-app-danger-bg text-app-danger-text',
  cancelled: 'border-app-border bg-app-surface-sidebar text-app-ink/45',
};

function resolveInputSection(value: string | null): PptInputSection {
  if (value === 'templates' || value === 'materials' || value === 'guide') {
    return value;
  }
  return 'create';
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  intent?: 'edit' | 'chat' | null;
}

// 다중 본문 양식(자유/Open ALM)에서 사용자가 고르는 본문 페이지 수.
const PAGE_COUNTS = [1, 2, 3, 4, 5] as const;
const MAX_INSTRUCTIONS_CHARS = 2000;
const LANGUAGES: { value: string; labelKey: string }[] = [
  { value: 'Korean', labelKey: 'ai.pptGenerator.languages.korean' },
  { value: 'English', labelKey: 'ai.pptGenerator.languages.english' },
  { value: 'Japanese', labelKey: 'ai.pptGenerator.languages.japanese' },
  { value: 'Chinese', labelKey: 'ai.pptGenerator.languages.chinese' },
];
const TONES: { value: string; labelKey: string }[] = [
  { value: 'default', labelKey: 'ai.pptGenerator.tones.default' },
  { value: 'professional', labelKey: 'ai.pptGenerator.tones.professional' },
  { value: 'casual', labelKey: 'ai.pptGenerator.tones.casual' },
  { value: 'educational', labelKey: 'ai.pptGenerator.tones.educational' },
  { value: 'sales_pitch', labelKey: 'ai.pptGenerator.tones.salesPitch' },
];

const POLL_INTERVAL_MS = 2500;
// finalize 폴링 상한 (≈3분). 워커 다운/태스크 유실로 pptx_key·error 가 영영
// 채워지지 않을 때 'PPT 변환 중...' 에 무한정 머무는 것을 막는다.
const FINALIZE_POLL_MAX_ATTEMPTS = 72;
const FIELD_CLASS =
  'app-field-input h-11 bg-app-bg [font-size:var(--ui-text-body)]';
const LABEL_CLASS = 'app-text-body mb-1.5 block font-medium text-app-ink/65';
const SECTION_CLASS = 'space-y-1.5';

// 워커가 보내는 단계 메시지 → 진행률(%) 기준값. 단계 내에서는 천천히 차오르도록 처리.
// \uB9C8\uC9C0\uB9C9 \uC6CC\uCEE4 \uD65C\uB3D9(\uD558\uD2B8\uBE44\uD2B8)\uC774 \uC774 \uCD08 \uC774\uC0C1 \uB04A\uAE30\uBA74 '\uBA48\uCDA4 \uC758\uC2EC'\uC73C\uB85C \uD45C\uC2DC. \uD558\uD2B8\uBE44\uD2B8\uB294 ~12\uCD08\uB9C8\uB2E4
// updated_at \uC744 \uAC31\uC2E0\uD558\uBBC0\uB85C, \uC774 \uAC12\uC744 \uB118\uC73C\uBA74 \uB2E4\uC12F \uBC88 \uB118\uAC8C \uC2E0\uD638\uB97C \uB193\uCE5C \uAC83 = \uC6CC\uCEE4 \uC911\uB2E8 \uAC00\uB2A5\uC131 \uB192\uC74C.
const PROGRESS_STALE_SECONDS = 60;

function stageTargetPercent(message: string | undefined): number {
  const m = message ?? '';
  if (m.includes('\uC644\uB8CC')) return 100; // \uC644\uB8CC
  if (m.includes('\uBBF8\uB9AC\uBCF4\uAE30')) return 88; // \uBBF8\uB9AC\uBCF4\uAE30
  if (m.includes('\uBCC0\uD658') || m.includes('\uBE4C\uB4DC')) return 78; // \uBCC0\uD658/\uBE4C\uB4DC
  if (m.includes('\uC7AC\uC2DC\uB3C4')) return 72; // (LLM \uC751\uB2F5) \uC7AC\uC2DC\uB3C4
  if (m.includes('\uC555\uCD95')) return 68; // \uC555\uCD95(\uB611\uB531\uC774)
  if (m.includes('\uBCF4\uAC15') || m.includes('\uCC44\uC6C0')) return 55; // \uBE48 \uACF5\uAC04 \uBCF4\uAC15/\uCC44\uC6C0
  if (m.includes('\uD30C\uC2F1')) return 45; // \uAD6C\uC870 \uD30C\uC2F1
  if (m.includes('\uBCF8\uBB38')) return 38; // (Qwen) \uBCF8\uBB38 \uC791\uC131
  if (m.includes('\uAD6C\uC870')) return 28; // \uC2AC\uB77C\uC774\uB4DC \uAD6C\uC870 \uC0DD\uC131/\uC694\uCCAD
  if (m.includes('\uAC80\uC0C9')) return 14; // \uCD5C\uC2E0 \uC815\uBCF4 \uAC80\uC0C9
  if (m.includes('\uC694\uCCAD')) return 12; // \uC694\uCCAD
  return 8;
}

export function PptGeneratorView({ appId }: { appId: string }) {
  const { t } = useTranslation('apps');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { jobId: routeJobId } = useParams<{ jobId?: string }>();
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [families, setFamilies] = useState<PptFamily[]>([]);
  const [step, setStep] = useState<Step>('input');
  const [error, setError] = useState<string | null>(null);

  // form state
  const [content, setContent] = useState('');
  // 좌측(외부/Claude) 비기밀 컨텍스트
  const [purpose, setPurpose] = useState('');
  const [audience, setAudience] = useState('');
  const [referenceUrl, setReferenceUrl] = useState('');
  // 우측(내부/VLLM) 기밀 컨텍스트
  const [extraNotes, setExtraNotes] = useState('');
  const [family, setFamily] = useState('corporate-house');
  const [pageCount, setPageCount] = useState<number | 'auto'>(3);
  const [language, setLanguage] = useState('Korean');
  const [tone, setTone] = useState('default');
  const [instructions, setInstructions] = useState('');
  const [includeTitleSlide, setIncludeTitleSlide] = useState(true);
  const [includeToc, setIncludeToc] = useState(false);
  const [files, setFiles] = useState<File[]>([]);

  // job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<PptJobStatus | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  // 생성 취소 진행 중(버튼 더블클릭/중복요청 방지)
  const [cancelling, setCancelling] = useState(false);
  // 진행 화면 경과/하트비트 표시용 1초 틱 + 기준 시각
  const [progressTick, setProgressTick] = useState(0);
  const progressStartRef = useRef<number>(0);
  // 마지막 폴링에서 받은 서버 계산 하트비트 경과초 + 받은 클라 시각(사이값은 클라에서 보간)
  const heartbeatRef = useRef<{ age: number; at: number } | null>(null);
  const jobRef = useRef<PptJobStatus | null>(null);
  const loadedRouteJobIdRef = useRef<string | null>(null);
  // HTML 미리보기 입력 — 구조화 슬라이드 데이터
  const [slidesSpec, setSlidesSpec] = useState<PptSlidesSpec | null>(null);

  // 'PPT로 전환'(finalize) 상태: idle | building | ready | error
  const [finalizeState, setFinalizeState] = useState<
    'idle' | 'building' | 'ready' | 'error'
  >('idle');
  const finalizePollCleanupRef = useRef<(() => void) | null>(null);

  // chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [chatConversationId, setChatConversationId] = useState<string | null>(
    null,
  );
  // 진행 중인 챗봇 폴링을 중단하는 cleanup. 언마운트/리셋/재요청 시 호출해 좀비 인터벌을 막는다.
  const chatPollCleanupRef = useRef<(() => void) | null>(null);

  const selectedFamily = families.find((f) => f.id === family);
  const isA4 = (selectedFamily?.aspect ?? '16:9') !== '16:9';
  const inputSection = resolveInputSection(searchParams.get('tab'));
  // 본문 슬라이드 수를 사용자가 정할 수 있는 양식(자유/Open ALM/corporate-v2). multi_body 미제공(구 API)이면
  // 16:9(corporate-v2)만 다중 본문으로 간주.
  const isMultiBody =
    selectedFamily?.multi_body ?? (selectedFamily?.aspect ?? '16:9') === '16:9';

  const navigateToBase = useCallback(() => {
    if (!workspaceSlug) return;
    navigate(buildPptAssistantPath(appId, workspaceSlug));
  }, [appId, navigate, workspaceSlug]);

  const navigateToHistory = useCallback(() => {
    if (!workspaceSlug) return;
    navigate(buildPptAssistantPath(appId, workspaceSlug, '/history'));
  }, [appId, navigate, workspaceSlug]);

  const navigateToJob = useCallback(
    (nextJobId: string) => {
      if (!workspaceSlug) return;
      navigate(buildPptAssistantJobPath(appId, workspaceSlug, nextJobId), {
        replace: true,
      });
    },
    [appId, navigate, workspaceSlug],
  );

  const setInputSection = useCallback(
    (section: PptInputSection) => {
      const next = new URLSearchParams(searchParams);
      if (section === 'create') {
        next.delete('tab');
      } else {
        next.set('tab', section);
      }
      setSearchParams(next, { replace: false });
    },
    [searchParams, setSearchParams],
  );

  useEffect(() => {
    if (!token) return;
    listPptFamilies({ token, workspaceSlug })
      .then((fams) => {
        setFamilies(fams);
        if (fams.length && !fams.some((f) => f.id === family)) {
          setFamily(fams[0].id);
        }
      })
      .catch(() => {
        /* 양식 목록 실패 시 기본 5종은 백엔드 검증으로 대체됨 */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, workspaceSlug]);

  // TEST(corporate-house)는 '긴 자료를 짧게 요약'하는 용도라 페이지 수 기본값을 '자유'로 둔다.
  // (양식을 house 로 바꿀 때만 적용 — 이후 사용자가 직접 고른 값은 유지된다.)
  useEffect(() => {
    if (family === 'corporate-house') setPageCount('auto');
  }, [family]);

  // 진행 중인 폴링 중단 (언마운트/리셋/재요청 시 호출)
  const stopChatPoll = useCallback(() => {
    chatPollCleanupRef.current?.();
    chatPollCleanupRef.current = null;
  }, []);
  const stopFinalizePoll = useCallback(() => {
    finalizePollCleanupRef.current?.();
    finalizePollCleanupRef.current = null;
  }, []);

  // 언마운트 시 폴링 정리
  useEffect(
    () => () => {
      stopChatPoll();
      stopFinalizePoll();
    },
    [stopChatPoll, stopFinalizePoll],
  );

  useEffect(() => {
    if (!routeJobId) {
      if (loadedRouteJobIdRef.current !== null) {
        stopChatPoll();
        stopFinalizePoll();
        setSlidesSpec(null);
        setFinalizeState('idle');
        setJob(null);
        jobRef.current = null;
        setJobId(null);
        setChatMessages([]);
        setChatConversationId(null);
        setContent('');
        // handleReset 와 동일하게 기밀 포함 입력값을 모두 비운다(잔존 방지).
        setPurpose('');
        setAudience('');
        setReferenceUrl('');
        setExtraNotes('');
        setStep('input');
      }
      loadedRouteJobIdRef.current = null;
      return;
    }
    if (!token || loadedRouteJobIdRef.current === routeJobId) return;

    let active = true;
    loadedRouteJobIdRef.current = routeJobId;
    stopChatPoll();
    stopFinalizePoll();
    setError(null);
    setJob(null);
    jobRef.current = null;
    setSlidesSpec(null);
    setChatMessages([]);
    setChatConversationId(null);
    setChatInput('');
    setChatBusy(false);
    setJobId(routeJobId);
    setProgressPct(8);
    setStep('progress');

    void getPptJobStatus({ token, workspaceSlug, jobId: routeJobId })
      .then((status) => {
        if (!active) return;
        setJob(status);
        jobRef.current = status;
        setJobId(status.job_id);
        setContent(status.title ?? '');
        setFamily(status.family || 'corporate-house');
        setSlidesSpec(status.slides_spec ?? null);
        setChatConversationId(status.chat_result?.conversation_id ?? null);
        setFinalizeState(status.pptx_ready ? 'ready' : 'idle');
        if (status.status === 'completed') {
          setProgressPct(100);
          setStep('result');
          return;
        }
        if (status.status === 'error') {
          setError(status.error || t('ai.pptGenerator.errors.generateFailed'));
          setStep('input');
          return;
        }
        if (status.status === 'cancelled') {
          setJobId(null);
          jobRef.current = null;
          setStep('input');
          return;
        }
        setProgressPct(stageTargetPercent(status.message));
        setStep('progress');
      })
      .catch((e) => {
        if (!active) return;
        loadedRouteJobIdRef.current = null;
        setJobId(null);
        setJob(null);
        jobRef.current = null;
        setSlidesSpec(null);
        setFinalizeState('idle');
        setStep('input');
        setError(
          e instanceof PptGeneratorApiError
            ? e.message
            : t('ai.pptGenerator.errors.requestFailed', { status: 0 }),
        );
      });

    return () => {
      active = false;
    };
  }, [routeJobId, stopChatPoll, stopFinalizePoll, t, token, workspaceSlug]);

  // 생성 진행 폴링
  useEffect(() => {
    if (step !== 'progress' || !jobId || !token) return;
    let active = true;
    const tick = async () => {
      try {
        const status = await getPptJobStatus({ token, workspaceSlug, jobId });
        if (!active) return;
        setJob(status);
        jobRef.current = status;
        if (typeof status.heartbeat_age_seconds === 'number') {
          heartbeatRef.current = {
            age: status.heartbeat_age_seconds,
            at: Date.now(),
          };
        }
        if (status.chat_result?.conversation_id) {
          setChatConversationId(status.chat_result.conversation_id);
        }
        if (status.status === 'completed') {
          setProgressPct(100);
          setSlidesSpec(status.slides_spec ?? null);
          setFinalizeState(status.pptx_ready ? 'ready' : 'idle');
          if (active) setStep('result');
        } else if (status.status === 'error') {
          setError(status.error || t('ai.pptGenerator.errors.generateFailed'));
          setStep('input');
        } else if (status.status === 'cancelled') {
          // 취소됨 — 폴링 중단하고 입력 화면으로(입력값은 유지해 바로 재시도 가능).
          setJobId(null);
          jobRef.current = null;
          setCancelling(false);
          setStep('input');
        }
      } catch {
        /* 일시 오류 — 다음 폴링에서 재시도 */
      }
    };
    void tick();
    const timer = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [step, jobId, token, workspaceSlug, t]);

  // 진행 화면 경과 시간/하트비트 표시용 1초 틱(+ 진입 시 기준 시각 초기화/정리)
  useEffect(() => {
    if (step !== 'progress') {
      progressStartRef.current = 0;
      heartbeatRef.current = null;
      return;
    }
    if (!progressStartRef.current) progressStartRef.current = Date.now();
    const timer = window.setInterval(() => setProgressTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [step]);

  // 진행률 게이지 애니메이션: 단계 기준값으로 빠르게 따라가고, 단계 내에서는 천천히 차오름
  useEffect(() => {
    if (step !== 'progress') return;
    const timer = window.setInterval(() => {
      setProgressPct((prev) => {
        const target = stageTargetPercent(jobRef.current?.message);
        if (target >= 100) return 100;
        if (prev < target) return Math.min(target, prev + 7);
        const softCap = Math.min(95, target + 10);
        return Math.min(softCap, prev + 0.4);
      });
    }, 350);
    return () => window.clearInterval(timer);
  }, [step]);

  const handleGenerate = async () => {
    if (!token) return;
    // 백엔드 merged 와 동일 기준: content/purpose/audience/extraNotes/첨부 중 하나라도
    // 있으면 생성 가능(referenceUrl 은 merged 에 안 들어가므로 단독으론 무효).
    if (
      !content.trim() &&
      !purpose.trim() &&
      !audience.trim() &&
      !extraNotes.trim() &&
      files.length === 0
    ) {
      setError(t('ai.pptGenerator.errors.noInput'));
      return;
    }
    setError(null);
    setJob(null);
    jobRef.current = null;
    setProgressPct(5);
    setChatMessages([]);
    setChatConversationId(null);
    try {
      const res = await generatePpt({
        token,
        workspaceSlug,
        content,
        family,
        purpose: purpose.trim() || undefined,
        audience: audience.trim() || undefined,
        referenceUrl: referenceUrl.trim() || undefined,
        extraNotes: extraNotes.trim() || undefined,
        slideRange: isMultiBody ? String(pageCount) : undefined,
        language,
        tone,
        instructions: instructions.trim() || undefined,
        includeTitleSlide,
        includeToc,
        files,
      });
      setJobId(res.job_id);
      setStep('progress');
      navigateToJob(res.job_id);
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.errors.requestGenerateFailed'),
      );
    }
  };

  const handleCancel = async () => {
    if (!token || !jobId || cancelling) return;
    setCancelling(true);
    try {
      await cancelPpt({ token, workspaceSlug, jobId });
    } catch {
      // 취소 요청이 실패(409/503/네트워크 등)하면 백엔드 작업은 계속 running/completed 될 수 있다.
      // 화면을 정리하면 사용자는 취소된 줄 알지만 실제로는 진행 중 — 진행 화면과 폴링을 유지하고
      // 오류를 표시한다. 실제 정리는 폴링이 cancelled 상태를 관측하면 그때 수행된다.
      setError(t('ai.pptGenerator.errors.cancelFailed'));
      setCancelling(false);
      return;
    }
    // 취소 요청 성공 → 화면을 입력으로 복귀(입력값 유지). 폴링 effect 도 cancelled 를 받으면 같이 정리.
    setJobId(null);
    setJob(null);
    jobRef.current = null;
    setProgressPct(0);
    setCancelling(false);
    setStep('input');
    navigateToBase();
  };

  const handleReset = () => {
    stopChatPoll();
    stopFinalizePoll();
    setSlidesSpec(null);
    setFinalizeState('idle');
    setJob(null);
    setJobId(null);
    jobRef.current = null;
    setChatMessages([]);
    setChatConversationId(null);
    setContent('');
    setPurpose('');
    setAudience('');
    setReferenceUrl('');
    setExtraNotes('');
    setFiles([]);
    setStep('input');
    navigateToBase();
  };

  const handleDownload = async () => {
    if (!token || !jobId) return;
    try {
      await downloadPptx({
        token,
        workspaceSlug,
        jobId,
        filename: buildPptDownloadFilename(job?.title ?? content, jobId),
      });
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.errors.download'),
      );
    }
  };

  // 'PPT로 전환' — slides_spec → .pptx 빌드 요청 후 완료까지 폴링, 완료되면 자동 다운로드.
  const handleFinalize = useCallback(() => {
    // 편집 진행 중에는 변환 금지 — 위와 대칭으로 편집/변환을 상호 배제한다.
    if (!token || !jobId || chatBusy) return;
    stopFinalizePoll();
    setError(null);
    setFinalizeState('building');

    // active/timer/cleanup 을 await 이전에 동기로 등록한다. finalize POST 가
    // 진행되는 동안 언마운트/리셋되면 cleanup 이 active=false 로 바꿔, await 이후
    // 인터벌이 생성되는 것 자체를 막는다(좀비 폴링·언마운트 후 setState 방지).
    let active = true;
    let attempts = 0;
    let timer: number | null = null;
    const stop = () => {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
      finalizePollCleanupRef.current = null;
    };
    const fail = (msg: string) => {
      stop();
      setFinalizeState('error');
      setError(msg);
    };
    finalizePollCleanupRef.current = () => {
      active = false;
      stop();
    };

    void (async () => {
      try {
        await finalizePpt({ token, workspaceSlug, jobId });
      } catch (e) {
        if (!active) return;
        fail(
          e instanceof PptGeneratorApiError
            ? e.message
            : t('ai.pptGenerator.errors.finalizeRequestFailed'),
        );
        return;
      }
      if (!active) return; // POST 도중 언마운트/리셋됨 — 폴링 시작하지 않음
      timer = window.setInterval(async () => {
        attempts += 1;
        try {
          const status = await getPptJobStatus({ token, workspaceSlug, jobId });
          if (!active) return;
          if (status.pptx_ready) {
            stop();
            setFinalizeState('ready');
            void downloadPptx({
              token,
              workspaceSlug,
              jobId,
              filename: buildPptDownloadFilename(job?.title ?? content, jobId),
            }).catch(() => {
              /* download errors are surfaced through finalize polling state */
            });
            return;
          }
          if (status.error && status.status === 'completed') {
            fail(status.error || t('ai.pptGenerator.errors.finalizeFailed'));
            return;
          }
        } catch {
          /* 일시 오류 — 아래 타임아웃 검사로만 종료 판단, 그 외엔 다음 폴링 재시도 */
        }
        if (active && attempts >= FINALIZE_POLL_MAX_ATTEMPTS) {
          fail(t('ai.pptGenerator.errors.finalizeTimeout'));
        }
      }, POLL_INTERVAL_MS);
    })();
  }, [
    token,
    workspaceSlug,
    jobId,
    chatBusy,
    stopFinalizePoll,
    job?.title,
    content,
    t,
  ]);

  // 챗봇 수정 폴링
  const pollChatResult = useCallback(() => {
    if (!token || !jobId) return;
    stopChatPoll(); // 이전 폴링이 남아 있으면 중단 (중복 인터벌 방지)
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const status = await getPptJobStatus({ token, workspaceSlug, jobId });
        if (!active) return;
        const cr = status.chat_result;
        if (!cr || cr.status === 'processing') return;
        if (cr.conversation_id) {
          setChatConversationId(cr.conversation_id);
        }
        window.clearInterval(timer);
        chatPollCleanupRef.current = null;
        setChatBusy(false);
        if (cr.status === 'done') {
          setChatMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: cr.answer || t('ai.pptGenerator.chat.received'),
              intent: cr.intent,
            },
          ]);
          // 수정 반영: 갱신된 slides_spec 으로 HTML 재렌더. 편집이 있었으면 기존 .pptx 는
          // 더 이상 최신이 아니므로 전환 상태를 idle 로 되돌려 재전환을 유도한다.
          if (status.slides_spec) setSlidesSpec(status.slides_spec);
          if (cr.intent === 'edit') setFinalizeState('idle');
        } else {
          setChatMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: cr.answer || t('ai.pptGenerator.errors.editFailed'),
              intent: 'chat',
            },
          ]);
        }
      } catch {
        /* 다음 폴링 재시도 */
      }
    }, POLL_INTERVAL_MS);
    chatPollCleanupRef.current = () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [token, workspaceSlug, jobId, stopChatPoll, t]);

  const handleSendChat = async () => {
    // 변환(빌드) 중에는 편집 금지 — finalize 워커가 읽는 slides_spec 이 바뀌어
    // stale 덱이 빌드되거나 두 폴링이 finalizeState 를 두고 경쟁하는 것을 막는다.
    if (
      !token ||
      !jobId ||
      !chatInput.trim() ||
      chatBusy ||
      finalizeState === 'building'
    )
      return;
    const message = chatInput.trim();
    const history = chatMessages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
    setChatMessages((prev) => [...prev, { role: 'user', content: message }]);
    setChatInput('');
    setChatBusy(true);
    try {
      const response = await sendPptChatEdit({
        token,
        workspaceSlug,
        jobId,
        message,
        history,
        conversationId: chatConversationId,
      });
      setChatConversationId(
        response.conversation_id ?? chatConversationId ?? null,
      );
      pollChatResult();
    } catch (e) {
      setChatBusy(false);
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            e instanceof PptGeneratorApiError
              ? e.message
              : t('ai.pptGenerator.errors.requestEditFailed'),
          intent: 'chat',
        },
      ]);
    }
  };

  // ── 렌더 ─────────────────────────────────────────────
  return (
    <div className="flex h-full flex-col overflow-hidden bg-app-bg text-app-ink">
      <header className="flex items-center gap-3 border-b border-app-border bg-app-bg px-8 pb-4 pt-6">
        <div className="flex size-9 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-accent">
          <Projector className="h-5 w-5" />
        </div>
        <div>
          <h1 className="app-text-title-lg text-app-ink">
            {t('ai.pptGenerator.title')}
          </h1>
          <p className="app-text-body mt-1 text-app-ink/55">
            {t('ai.pptGenerator.subtitle')}
          </p>
        </div>
        {step === 'result' && (
          <button
            type="button"
            onClick={handleReset}
            className="app-control ml-auto h-8 px-3"
          >
            <RefreshCw className="h-4 w-4" /> {t('ai.pptGenerator.newPpt')}
          </button>
        )}
      </header>

      {error && (
        <div className="app-text-body-sm flex items-center gap-2 border-b border-app-danger-border bg-app-danger-bg px-8 py-2 text-app-danger-text">
          <AlertCircle className="h-4 w-4" />
          {error}
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-auto rounded-md p-1 text-app-danger transition-colors hover:bg-red-100 hover:text-app-danger-text"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="custom-scrollbar min-h-0 flex-1 overflow-auto">
        {step === 'input' && (
          <InputForm
            inputSection={inputSection}
            onInputSectionChange={setInputSection}
            families={families}
            content={content}
            setContent={setContent}
            purpose={purpose}
            setPurpose={setPurpose}
            audience={audience}
            setAudience={setAudience}
            referenceUrl={referenceUrl}
            setReferenceUrl={setReferenceUrl}
            extraNotes={extraNotes}
            setExtraNotes={setExtraNotes}
            family={family}
            setFamily={setFamily}
            isA4={isA4}
            isMultiBody={isMultiBody}
            pageCount={pageCount}
            setPageCount={setPageCount}
            language={language}
            setLanguage={setLanguage}
            tone={tone}
            setTone={setTone}
            instructions={instructions}
            setInstructions={setInstructions}
            includeTitleSlide={includeTitleSlide}
            setIncludeTitleSlide={setIncludeTitleSlide}
            includeToc={includeToc}
            setIncludeToc={setIncludeToc}
            files={files}
            setFiles={setFiles}
            token={token}
            workspaceSlug={workspaceSlug}
            onOpenJob={navigateToJob}
            onOpenHistory={navigateToHistory}
            onGenerate={handleGenerate}
          />
        )}

        {step === 'progress' &&
          (() => {
            void progressTick; // 1초 틱마다 재계산
            const elapsedSeconds = progressStartRef.current
              ? Math.floor((Date.now() - progressStartRef.current) / 1000)
              : 0;
            const hb = heartbeatRef.current;
            const heartbeatAgeSeconds = hb
              ? hb.age + Math.floor((Date.now() - hb.at) / 1000)
              : null;
            return (
              <ProgressPanel
                message={job?.message ?? t('ai.pptGenerator.progress.starting')}
                percent={progressPct}
                elapsedSeconds={elapsedSeconds}
                heartbeatAgeSeconds={heartbeatAgeSeconds}
                staleThresholdSeconds={PROGRESS_STALE_SECONDS}
                queued={job?.status === 'pending'}
                onCancel={handleCancel}
                cancelling={cancelling}
              />
            );
          })()}

        {step === 'result' && (
          <ResultPanel
            slides={slidesSpec?.slides ?? []}
            htmlDeck={
              slidesSpec?.format === 'html' && slidesSpec.html
                ? { html: slidesSpec.html, slideW: slidesSpec.slide_w ?? 1280 }
                : null
            }
            embedPreview={
              slidesSpec?.embed_preview?.html
                ? {
                    html: slidesSpec.embed_preview.html,
                    slideW: slidesSpec.embed_preview.slide_w ?? 1280,
                    title:
                      slidesSpec.embed_preview.title ??
                      t('ai.pptGenerator.embedDefaultTitle'),
                  }
                : null
            }
            slideCount={job?.n_slides ?? slidesSpec?.slides?.length ?? 0}
            chatMessages={chatMessages}
            chatInput={chatInput}
            setChatInput={setChatInput}
            chatBusy={chatBusy}
            onSendChat={handleSendChat}
            onFinalize={handleFinalize}
            onDownload={handleDownload}
            finalizeState={finalizeState}
            researchSources={job?.research_sources ?? []}
          />
        )}
      </div>
    </div>
  );
}

// ============================================================
// Step 1 — 입력 폼
// ============================================================
function InputForm(props: {
  inputSection: PptInputSection;
  onInputSectionChange: (section: PptInputSection) => void;
  families: PptFamily[];
  content: string;
  setContent: (v: string) => void;
  purpose: string;
  setPurpose: (v: string) => void;
  audience: string;
  setAudience: (v: string) => void;
  referenceUrl: string;
  setReferenceUrl: (v: string) => void;
  extraNotes: string;
  setExtraNotes: (v: string) => void;
  family: string;
  setFamily: (v: string) => void;
  isA4: boolean;
  isMultiBody: boolean;
  pageCount: number | 'auto';
  setPageCount: (v: number | 'auto') => void;
  language: string;
  setLanguage: (v: string) => void;
  tone: string;
  setTone: (v: string) => void;
  instructions: string;
  setInstructions: (v: string) => void;
  includeTitleSlide: boolean;
  setIncludeTitleSlide: (v: boolean) => void;
  includeToc: boolean;
  setIncludeToc: (v: boolean) => void;
  files: File[];
  setFiles: (v: File[]) => void;
  token: string | null;
  workspaceSlug: string | null;
  onOpenJob: (jobId: string) => void;
  onOpenHistory: () => void;
  onGenerate: () => void;
}) {
  const { t } = useTranslation('apps');
  // 입력 단계 = 설정(2단 카드+언어/톤) → 템플릿 선택. step!=='input' 이면 InputForm 이
  // 언마운트되므로 생성/리셋 후 자연히 'settings' 로 초기화된다.
  const [createPhase, setCreatePhase] = useState<'settings' | 'template'>(
    'settings',
  );
  // 입력 섹션(create/guide 등) 전환 시엔 InputForm 이 언마운트되지 않으므로,
  // create 로 돌아올 때 항상 설정 단계부터 보이도록 명시적으로 초기화한다.
  useEffect(() => {
    setCreatePhase('settings');
  }, [props.inputSection]);
  const [previewModal, setPreviewModal] = useState<{
    familyId: string;
  } | null>(null);
  const [previewIdx, setPreviewIdx] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const previewFamily = previewModal?.familyId ?? null;
  const previewFamilyInfo = props.families.find((f) => f.id === previewFamily);
  const previewItems = previewFamilyInfo?.preview_images ?? [];
  // 미리보기 이미지 우선순위: 관리자 업로드 → 번들 정적 이미지(표지+본문 여러 장).
  // 정적 이미지는 HTML 경로(corporate-*) 양식의 본문까지 보여줘 좌우 화살표로 넘겨볼 수 있게 한다.
  const previewImages =
    previewItems.length > 0
      ? previewItems.map((item) => item.url)
      : getTemplateStaticPreviews(previewFamily);
  const previewName = previewFamilyInfo?.name ?? '';
  // 업로드/정적 미리보기 이미지가 없으면 양식 샘플을 실시간 렌더해 보여준다.
  const sampleSlides = getTemplateSampleSlides(previewFamily);
  const showLiveSample = previewImages.length === 0 && sampleSlides.length > 0;
  const sampleIdx = Math.min(previewIdx, Math.max(0, sampleSlides.length - 1));

  useEffect(() => {
    if (!previewFamily) return;
    // 업로드 이미지도, 샘플도 없을 때만 닫는다.
    if (previewImages.length === 0 && sampleSlides.length === 0) {
      setPreviewModal(null);
      setPreviewIdx(0);
      return;
    }
    if (previewImages.length > 0 && previewIdx >= previewImages.length) {
      setPreviewIdx(Math.max(0, previewImages.length - 1));
    }
  }, [previewFamily, previewImages.length, sampleSlides.length, previewIdx]);

  const onPickFiles = (list: FileList | null) => {
    if (!list) return;
    props.setFiles([...props.files, ...Array.from(list)].slice(0, 10));
  };

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-8 py-6">
      <InputSectionTabs
        activeSection={props.inputSection}
        onSelect={props.onInputSectionChange}
      />

      {props.inputSection === 'templates' ? (
        <section className="space-y-3">
          <div>
            <h2 className="app-text-title-md text-app-ink">
              {t('ai.pptGenerator.templates.title')}
            </h2>
            <p className="app-text-body-sm mt-1 text-app-ink/50">
              {t('ai.pptGenerator.templates.subtitle')}
            </p>
          </div>
          <TemplateGrid
            families={props.families}
            selectedFamilyId={props.family}
            onSelectFamily={props.setFamily}
            onPreview={(familyId) => {
              setPreviewModal({ familyId });
              setPreviewIdx(0);
            }}
          />
        </section>
      ) : null}

      {props.inputSection === 'materials' ? (
        <RecentMaterialsPanel
          token={props.token}
          workspaceSlug={props.workspaceSlug}
          onOpenJob={props.onOpenJob}
          onOpenHistory={props.onOpenHistory}
        />
      ) : null}

      {props.inputSection === 'guide' ? (
        <PptGuide families={props.families} />
      ) : null}

      {props.inputSection === 'create' && createPhase === 'settings' ? (
        <>
          <section className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
            <div className="grid grid-cols-1 lg:grid-cols-2">
              {/* 좌측 — 외부 참고 정보 (Claude API 로 전송 가능한 비기밀 입력) */}
              <div className="flex flex-col gap-4 p-5">
                <div className="flex items-start gap-2.5">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                    <Cloud className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="app-text-title-md text-app-ink">
                      {t('ai.pptGenerator.form.externalTitle')}
                    </h3>
                    <p className="app-text-body mt-0.5 text-app-ink/45">
                      {t('ai.pptGenerator.form.externalCaption')}
                    </p>
                  </div>
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.contentLabel')}
                  </label>
                  <textarea
                    value={props.content}
                    onChange={(e) =>
                      props.setContent(e.target.value.slice(0, 100))
                    }
                    rows={3}
                    maxLength={100}
                    placeholder={t('ai.pptGenerator.form.contentPlaceholder')}
                    className="app-field-input min-h-24 resize-y bg-app-bg py-2 [font-size:var(--ui-text-body)]"
                  />
                  <div className="app-text-body mt-1 text-right text-app-ink/40">
                    {t('ai.pptGenerator.form.charCounter', {
                      count: props.content.length,
                    })}
                  </div>
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.purposeLabel')}
                  </label>
                  <input
                    type="text"
                    value={props.purpose}
                    onChange={(e) =>
                      props.setPurpose(e.target.value.slice(0, 100))
                    }
                    maxLength={100}
                    placeholder={t('ai.pptGenerator.form.purposePlaceholder')}
                    className={FIELD_CLASS}
                  />
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.audienceLabel')}
                  </label>
                  <input
                    type="text"
                    value={props.audience}
                    onChange={(e) =>
                      props.setAudience(e.target.value.slice(0, 100))
                    }
                    maxLength={100}
                    placeholder={t('ai.pptGenerator.form.audiencePlaceholder')}
                    className={FIELD_CLASS}
                  />
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.referenceUrlLabel')}
                  </label>
                  <input
                    type="url"
                    value={props.referenceUrl}
                    onChange={(e) =>
                      props.setReferenceUrl(e.target.value.slice(0, 500))
                    }
                    maxLength={500}
                    placeholder={t(
                      'ai.pptGenerator.form.referenceUrlPlaceholder',
                    )}
                    className={FIELD_CLASS}
                  />
                </div>
              </div>

              {/* 우측 — 내부 자료 (외부로 전송되지 않고 내부 AI 만 사용) */}
              <div className="flex flex-col gap-4 border-t border-app-border bg-app-surface-sidebar p-5 lg:border-l lg:border-t-0">
                <div className="flex items-start gap-2.5">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink/70">
                    <Lock className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="app-text-title-md text-app-ink">
                      {t('ai.pptGenerator.form.internalTitle')}
                    </h3>
                    <p className="app-text-body mt-0.5 text-app-ink/45">
                      {t('ai.pptGenerator.form.internalCaption')}
                    </p>
                  </div>
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.attachLabel')}
                  </label>
                  <label
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragActive(true);
                    }}
                    onDragEnter={(e) => {
                      e.preventDefault();
                      setDragActive(true);
                    }}
                    onDragLeave={(e) => {
                      e.preventDefault();
                      setDragActive(false);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragActive(false);
                      onPickFiles(e.dataTransfer.files);
                    }}
                    className={cn(
                      'app-text-body-sm flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed px-4 py-5 transition-colors',
                      dragActive
                        ? 'border-app-accent bg-app-accent/10 text-app-accent'
                        : 'border-app-border bg-app-bg text-app-ink/55 hover:border-app-accent/50 hover:bg-app-surface-hover hover:text-app-ink',
                    )}
                  >
                    <FileUp className="h-5 w-5" />
                    {dragActive
                      ? t('ai.pptGenerator.form.dropHere')
                      : t('ai.pptGenerator.form.dropHint')}
                    <input
                      type="file"
                      multiple
                      className="hidden"
                      onChange={(e) => onPickFiles(e.target.files)}
                    />
                  </label>
                  {props.files.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {props.files.map((f, i) => (
                        <li
                          key={`${f.name}-${i}`}
                          className="app-text-caption flex items-center justify-between gap-3 rounded-md border border-app-border bg-app-bg px-3 py-1.5 text-app-ink/65"
                        >
                          <span className="truncate">{f.name}</span>
                          <button
                            type="button"
                            onClick={() =>
                              props.setFiles(
                                props.files.filter((_, idx) => idx !== i),
                              )
                            }
                            className="shrink-0 rounded p-0.5 text-app-ink/40 transition-colors hover:bg-app-danger-bg hover:text-app-danger-text"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.extraNotesLabel')}
                  </label>
                  <textarea
                    value={props.extraNotes}
                    onChange={(e) =>
                      props.setExtraNotes(
                        e.target.value.slice(0, MAX_INSTRUCTIONS_CHARS),
                      )
                    }
                    rows={3}
                    maxLength={MAX_INSTRUCTIONS_CHARS}
                    placeholder={t(
                      'ai.pptGenerator.form.extraNotesPlaceholder',
                    )}
                    className="app-field-input min-h-24 resize-y bg-app-bg py-2 [font-size:var(--ui-text-body)]"
                  />
                </div>

                <div className={SECTION_CLASS}>
                  <label className={LABEL_CLASS}>
                    {t('ai.pptGenerator.form.instructionsLabel')}
                  </label>
                  <input
                    type="text"
                    value={props.instructions}
                    onChange={(e) => props.setInstructions(e.target.value)}
                    maxLength={MAX_INSTRUCTIONS_CHARS}
                    placeholder={t(
                      'ai.pptGenerator.form.instructionsPlaceholder',
                    )}
                    className={FIELD_CLASS}
                  />
                </div>
              </div>
            </div>
          </section>

          {/* 설정 단계 마무리 — 언어/톤은 양식과 무관하므로 여기서 고른다. */}
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className={SECTION_CLASS}>
              <label className={LABEL_CLASS}>
                {t('ai.pptGenerator.form.languageLabel')}
              </label>
              <select
                value={props.language}
                onChange={(e) => props.setLanguage(e.target.value)}
                className="app-field-input"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>
                    {t(l.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <div className={SECTION_CLASS}>
              <label className={LABEL_CLASS}>
                {t('ai.pptGenerator.form.toneLabel')}
              </label>
              <select
                value={props.tone}
                onChange={(e) => props.setTone(e.target.value)}
                className="app-field-input"
              >
                {TONES.map((tn) => (
                  <option key={tn.value} value={tn.value}>
                    {t(tn.labelKey)}
                  </option>
                ))}
              </select>
            </div>
          </section>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setCreatePhase('template')}
              className="app-control-primary h-10 px-5"
            >
              {t('ai.pptGenerator.form.nextTemplate')}
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </>
      ) : null}

      {props.inputSection === 'create' && createPhase === 'template' ? (
        <>
          <section className={SECTION_CLASS}>
            <label className={LABEL_CLASS}>
              {t('ai.pptGenerator.form.templateLabel')}
            </label>
            <TemplateGrid
              families={props.families}
              selectedFamilyId={props.family}
              onSelectFamily={props.setFamily}
              onPreview={(familyId) => {
                setPreviewModal({ familyId });
                setPreviewIdx(0);
              }}
            />
          </section>

          {props.isMultiBody && (
            <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className={SECTION_CLASS}>
                <label className={LABEL_CLASS}>
                  {t('ai.pptGenerator.form.pageCountLabel')}
                </label>
                <select
                  value={String(props.pageCount)}
                  onChange={(e) => {
                    const v = e.target.value;
                    props.setPageCount(v === 'auto' ? 'auto' : Number(v));
                  }}
                  className="app-field-input"
                >
                  <option value="auto">
                    {t('ai.pptGenerator.form.pageCountFree')}
                  </option>
                  {PAGE_COUNTS.map((n) => (
                    <option key={n} value={n}>
                      {t('ai.pptGenerator.form.pageCountOption', { count: n })}
                    </option>
                  ))}
                </select>
                <span className="app-text-caption mt-1 block text-app-ink/40">
                  {t('ai.pptGenerator.form.titleSlideNote')}
                </span>
              </div>
            </section>
          )}

          {!props.isA4 && (
            <section className="flex flex-wrap gap-4">
              <label className="app-text-body-sm flex items-center gap-2 text-app-ink/70">
                <input
                  type="checkbox"
                  checked={props.includeTitleSlide}
                  onChange={(e) => props.setIncludeTitleSlide(e.target.checked)}
                  className="size-4 accent-[var(--ui-color-accent)]"
                />
                {t('ai.pptGenerator.form.includeTitleSlide')}
              </label>
              <label className="app-text-body-sm flex items-center gap-2 text-app-ink/70">
                <input
                  type="checkbox"
                  checked={props.includeToc}
                  onChange={(e) => props.setIncludeToc(e.target.checked)}
                  className="size-4 accent-[var(--ui-color-accent)]"
                />
                {t('ai.pptGenerator.form.includeToc')}
              </label>
            </section>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setCreatePhase('settings')}
              className="app-control h-10 px-4"
            >
              <ChevronLeft className="h-4 w-4" />
              {t('ai.pptGenerator.form.back')}
            </button>
            <button
              type="button"
              onClick={() => {
                // 입력이 전혀 없으면 생성이 거부되는데(상단 noInput 배너), 입력 필드는
                // 설정 단계에 있으므로 사용자가 고칠 수 있게 그 단계로 되돌린다.
                if (
                  !props.content.trim() &&
                  !props.purpose.trim() &&
                  !props.audience.trim() &&
                  !props.extraNotes.trim() &&
                  props.files.length === 0
                ) {
                  setCreatePhase('settings');
                }
                props.onGenerate();
              }}
              className="app-control-primary h-10 flex-1 px-4"
            >
              <Sparkles className="h-4 w-4" />{' '}
              {t('ai.pptGenerator.form.generate')}
            </button>
          </div>
        </>
      ) : null}

      {previewFamily &&
        (previewImages.length > 0 || sampleSlides.length > 0) && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
            onClick={() => setPreviewModal(null)}
          >
            <div
              className="flex max-h-[94vh] w-full max-w-7xl flex-col overflow-hidden rounded-lg border border-app-border bg-app-bg shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-app-border px-5 py-3">
                <h3 className="app-text-title-lg truncate font-bold text-app-ink">
                  {previewName}
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPreviewModal(null)}
                    aria-label={t('ai.pptGenerator.preview.close')}
                    title={t('ai.pptGenerator.preview.close')}
                    className="flex size-10 items-center justify-center rounded-full border border-app-border bg-app-bg text-app-ink shadow-sm transition hover:bg-app-danger hover:text-white"
                  >
                    <X className="h-6 w-6" strokeWidth={2.5} />
                  </button>
                </div>
              </div>

              <div className="grid min-h-0 flex-1 grid-cols-1 bg-app-surface-sidebar">
                <div className="relative flex min-h-[360px] items-center justify-center p-1.5">
                  {previewImages.length > 0 ? (
                    <>
                      <img
                        src={previewImages[previewIdx]}
                        alt={`${previewName} ${t(
                          'ai.pptGenerator.preview.counter',
                          {
                            current: previewIdx + 1,
                            total: previewImages.length,
                          },
                        )}`}
                        className="max-h-[84vh] max-w-full rounded-md border border-app-border bg-app-bg object-contain shadow-lg"
                      />
                      {previewImages.length > 1 && (
                        <>
                          <button
                            type="button"
                            aria-label={t('ai.pptGenerator.preview.prev')}
                            onClick={() =>
                              setPreviewIdx(
                                (i) =>
                                  (i - 1 + previewImages.length) %
                                  previewImages.length,
                              )
                            }
                            className="absolute left-4 top-1/2 z-20 flex size-14 -translate-y-1/2 items-center justify-center rounded-full border border-app-border bg-app-bg/95 text-app-ink shadow-lg transition hover:bg-app-accent hover:text-app-accent-fg"
                          >
                            <ChevronLeft
                              className="h-8 w-8"
                              strokeWidth={2.5}
                            />
                          </button>
                          <button
                            type="button"
                            aria-label={t('ai.pptGenerator.preview.next')}
                            onClick={() =>
                              setPreviewIdx(
                                (i) => (i + 1) % previewImages.length,
                              )
                            }
                            className="absolute right-4 top-1/2 z-20 flex size-14 -translate-y-1/2 items-center justify-center rounded-full border border-app-border bg-app-bg/95 text-app-ink shadow-lg transition hover:bg-app-accent hover:text-app-accent-fg"
                          >
                            <ChevronRight
                              className="h-8 w-8"
                              strokeWidth={2.5}
                            />
                          </button>
                          <span className="app-text-body-sm absolute bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-full border border-app-border bg-app-ink/85 px-3.5 py-1 font-semibold text-white shadow-lg">
                            {previewIdx + 1} / {previewImages.length}
                          </span>
                        </>
                      )}
                    </>
                  ) : showLiveSample ? (
                    <div
                      className="relative flex flex-col items-center"
                      // 큰 화면에선 폭을 꽉, 작은 화면에선 높이에 맞춰(가로세로비 ~1.44) 잘림 방지.
                      style={{ width: 'min(100%, calc(80vh * 1.44))' }}
                    >
                      <PptSlideRenderer slide={sampleSlides[sampleIdx]} />
                      {sampleSlides.length > 1 && (
                        <>
                          <button
                            type="button"
                            aria-label={t('ai.pptGenerator.preview.prev')}
                            onClick={() =>
                              setPreviewIdx(
                                (i) =>
                                  (i - 1 + sampleSlides.length) %
                                  sampleSlides.length,
                              )
                            }
                            className="absolute left-4 top-1/2 z-20 flex size-14 -translate-y-1/2 items-center justify-center rounded-full border border-app-border bg-app-bg/95 text-app-ink shadow-lg transition hover:bg-app-accent hover:text-app-accent-fg"
                          >
                            <ChevronLeft
                              className="h-8 w-8"
                              strokeWidth={2.5}
                            />
                          </button>
                          <button
                            type="button"
                            aria-label={t('ai.pptGenerator.preview.next')}
                            onClick={() =>
                              setPreviewIdx(
                                (i) => (i + 1) % sampleSlides.length,
                              )
                            }
                            className="absolute right-4 top-1/2 z-20 flex size-14 -translate-y-1/2 items-center justify-center rounded-full border border-app-border bg-app-bg/95 text-app-ink shadow-lg transition hover:bg-app-accent hover:text-app-accent-fg"
                          >
                            <ChevronRight
                              className="h-8 w-8"
                              strokeWidth={2.5}
                            />
                          </button>
                          <span className="app-text-body-sm absolute bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-full border border-app-border bg-app-ink/85 px-3.5 py-1 font-semibold text-white shadow-lg">
                            {sampleIdx + 1} / {sampleSlides.length}
                          </span>
                        </>
                      )}
                    </div>
                  ) : (
                    <div className="flex min-h-64 w-full max-w-lg flex-col items-center justify-center rounded-md border border-dashed border-app-border bg-app-bg px-6 py-10 text-center">
                      <ImagePlus className="mb-3 h-8 w-8 text-app-ink/35" />
                      <p className="app-text-body-sm font-medium text-app-ink/70">
                        {t('ai.pptGenerator.preview.emptyTitle')}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-app-border px-5 py-3">
                <div className="flex gap-1.5">
                  {previewImages.map((url, i) => (
                    <button
                      key={url}
                      type="button"
                      onClick={() => setPreviewIdx(i)}
                      className={cn(
                        'h-1.5 w-6 rounded-full transition',
                        i === previewIdx
                          ? 'bg-app-accent'
                          : 'bg-app-border hover:bg-app-accent/30',
                      )}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (previewFamily) props.setFamily(previewFamily);
                      setPreviewModal(null);
                    }}
                    className="app-control-primary h-8 px-3"
                  >
                    <Sparkles className="h-4 w-4" />{' '}
                    {t('ai.pptGenerator.preview.select')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
    </div>
  );
}

function InputSectionTabs(props: {
  activeSection: PptInputSection;
  onSelect: (section: PptInputSection) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {PPT_INPUT_SECTIONS.map((section) => {
        const Icon = section.icon;
        const active = props.activeSection === section.id;
        return (
          <button
            key={section.id}
            type="button"
            aria-pressed={active}
            onClick={() => props.onSelect(section.id)}
            className={cn(
              'flex min-h-16 items-start gap-3 rounded-md border px-3 py-2.5 text-left transition-colors',
              active
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-bg text-app-ink hover:border-app-accent/50 hover:bg-app-surface-hover',
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0">
              <span className="app-text-body block font-semibold">
                {t(section.labelKey)}
              </span>
              <span className="app-text-body-sm mt-0.5 block text-app-ink/45">
                {t(section.descKey)}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function RecentMaterialsPanel(props: {
  token: string | null;
  workspaceSlug: string | null;
  onOpenJob: (jobId: string) => void;
  onOpenHistory: () => void;
}) {
  const { t } = useTranslation('apps');
  const [items, setItems] = useState<PptJobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyJobId, setBusyJobId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!props.token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await listPptJobs({
        token: props.token,
        workspaceSlug: props.workspaceSlug,
        limit: 8,
      });
      setItems(response.items);
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.history.errors.load'),
      );
    } finally {
      setLoading(false);
    }
  }, [props.token, props.workspaceSlug, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDownload = async (item: PptJobListItem) => {
    if (!props.token || !item.pptx_ready) return;
    setBusyJobId(item.job_id);
    setError(null);
    try {
      await downloadPptx({
        token: props.token,
        workspaceSlug: props.workspaceSlug,
        jobId: item.job_id,
        filename: buildPptDownloadFilename(item.title ?? '', item.job_id),
      });
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.errors.download'),
      );
    } finally {
      setBusyJobId(null);
    }
  };

  return (
    <section className="space-y-3">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-accent">
          <History className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h2 className="app-text-title-md text-app-ink">
            {t('ai.pptGenerator.materials.title')}
          </h2>
          <p className="app-text-body-sm mt-1 text-app-ink/50">
            {t('ai.pptGenerator.materials.subtitle')}
          </p>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="app-control h-8 px-3"
          >
            <RefreshCw className="h-4 w-4" />
            {t('ai.pptGenerator.history.refresh')}
          </button>
          <button
            type="button"
            onClick={props.onOpenHistory}
            className="app-control-primary h-8 px-3"
          >
            <ExternalLink className="h-4 w-4" />
            {t('ai.pptGenerator.materials.openFull')}
          </button>
        </div>
      </div>

      {error ? (
        <div className="app-text-body-sm flex items-center gap-2 rounded-md border border-app-danger-border bg-app-danger-bg px-3 py-2 text-app-danger-text">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex min-h-52 items-center justify-center gap-2 text-app-ink/55">
          <Loader2 className="h-5 w-5 animate-spin text-app-accent" />
          <span className="app-text-body-sm">
            {t('ai.pptGenerator.history.loading')}
          </span>
        </div>
      ) : items.length === 0 ? (
        <div className="flex min-h-52 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-6 py-8 text-center">
          <History className="h-8 w-8 text-app-ink/30" />
          <div>
            <p className="app-text-body-sm font-medium text-app-ink">
              {t('ai.pptGenerator.history.emptyTitle')}
            </p>
            <p className="app-text-caption mt-1 text-app-ink/45">
              {t('ai.pptGenerator.history.emptyDescription')}
            </p>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[720px]">
            <div className="grid grid-cols-[minmax(220px,1fr)_110px_120px_150px_120px] border-b border-app-border px-2 py-2">
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.title')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.status')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.slides')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.createdAt')}
              </span>
              <span className="app-text-overline text-right text-app-ink/40">
                {t('ai.pptGenerator.history.columns.actions')}
              </span>
            </div>
            {items.map((item) => {
              const busy = busyJobId === item.job_id;
              return (
                <div
                  key={item.job_id}
                  className="grid grid-cols-[minmax(220px,1fr)_110px_120px_150px_120px] items-center border-b border-app-border px-2 py-3 transition-colors hover:bg-app-surface-hover"
                >
                  <button
                    type="button"
                    onClick={() => props.onOpenJob(item.job_id)}
                    className="min-w-0 text-left"
                  >
                    <span className="app-text-body-sm block truncate font-medium text-app-ink hover:text-app-accent">
                      {item.title || t('ai.pptGenerator.history.untitled')}
                    </span>
                    <span className="app-text-caption mt-0.5 block truncate text-app-ink/40">
                      {item.job_id}
                    </span>
                  </button>
                  <span
                    className={cn(
                      'app-text-caption inline-flex w-fit items-center rounded-full border px-2 py-0.5 font-medium',
                      PPT_JOB_STATUS_CLASS[item.status],
                    )}
                  >
                    {t(`ai.pptGenerator.history.status.${item.status}`)}
                  </span>
                  <span className="app-text-body-sm text-app-ink/60">
                    {t('ai.pptGenerator.history.slideCount', {
                      count: item.n_slides,
                    })}
                  </span>
                  <span className="app-text-body-sm text-app-ink/60">
                    <UserDateTime value={item.created_at} />
                  </span>
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => props.onOpenJob(item.job_id)}
                      className="app-control-ghost h-8 px-2"
                    >
                      <ExternalLink className="h-4 w-4" />
                      {t('ai.pptGenerator.history.open')}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDownload(item)}
                      disabled={!item.pptx_ready || busy}
                      className="app-control-ghost h-8 px-2"
                      title={
                        item.pptx_ready
                          ? t('ai.pptGenerator.result.downloadPptx')
                          : t('ai.pptGenerator.history.notReady')
                      }
                    >
                      {busy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function PptGuide(props: { families: PptFamily[] }) {
  const { t } = useTranslation('apps');
  const steps = [
    t('ai.pptGenerator.guide.step1'),
    t('ai.pptGenerator.guide.step2'),
    t('ai.pptGenerator.guide.step3'),
    t('ai.pptGenerator.guide.step4'),
  ];
  return (
    <section className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-accent">
          <BookOpen className="h-5 w-5" />
        </div>
        <div>
          <h2 className="app-text-title-md text-app-ink">
            {t('ai.pptGenerator.guide.title')}
          </h2>
          <p className="app-text-body-sm mt-1 text-app-ink/50">
            {t('ai.pptGenerator.guide.subtitle')}
          </p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-app-border bg-app-bg p-4">
          <h3 className="app-text-control-sm text-app-ink">
            {t('ai.pptGenerator.guide.workflowTitle')}
          </h3>
          <ol className="mt-3 space-y-2">
            {steps.map((step, index) => (
              <li key={step} className="flex gap-3">
                <span className="app-text-caption flex size-6 shrink-0 items-center justify-center rounded-full bg-app-accent/10 font-semibold text-app-accent">
                  {index + 1}
                </span>
                <span className="app-text-body-sm text-app-ink/70">{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="rounded-md border border-app-border bg-app-bg p-4">
          <h3 className="app-text-control-sm text-app-ink">
            {t('ai.pptGenerator.guide.resultTitle')}
          </h3>
          <div className="mt-3 space-y-3">
            <div className="flex gap-3">
              <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-app-accent" />
              <p className="app-text-body-sm text-app-ink/70">
                {t('ai.pptGenerator.guide.editBody')}
              </p>
            </div>
            <div className="flex gap-3">
              <Download className="mt-0.5 h-4 w-4 shrink-0 text-app-accent" />
              <p className="app-text-body-sm text-app-ink/70">
                {t('ai.pptGenerator.guide.downloadBody')}
              </p>
            </div>
            <div className="flex gap-3">
              <History className="mt-0.5 h-4 w-4 shrink-0 text-app-accent" />
              <p className="app-text-body-sm text-app-ink/70">
                {t('ai.pptGenerator.guide.materialsBody')}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-app-border bg-app-bg p-4">
        <h3 className="app-text-control-sm text-app-ink">
          {t('ai.pptGenerator.guide.templatesTitle')}
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {props.families.map((family) => (
            <span
              key={family.id}
              className="app-text-caption rounded-full border border-app-border bg-app-surface-sidebar px-2.5 py-1 text-app-ink/65"
            >
              {family.name}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function TemplateGrid(props: {
  families: PptFamily[];
  selectedFamilyId: string;
  onSelectFamily: (familyId: string) => void;
  onPreview: (familyId: string) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {props.families.map((family) => {
        const hasPreviewImages = (family.preview_images ?? []).length > 0;
        const hasStaticPreview =
          getTemplateStaticPreviews(family.id).length > 0;
        const hasSample = getTemplateSampleSlides(family.id).length > 0;
        const canPreview = hasPreviewImages || hasStaticPreview || hasSample;
        return (
          <div
            key={family.id}
            role="button"
            tabIndex={0}
            onClick={() => props.onSelectFamily(family.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                props.onSelectFamily(family.id);
              }
            }}
            className={cn(
              'group relative min-h-20 cursor-pointer rounded-md border px-3 py-2.5 text-left transition-colors',
              props.selectedFamilyId === family.id
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-bg text-app-ink hover:border-app-accent/50 hover:bg-app-surface-hover',
            )}
          >
            <div className="flex items-center gap-2 pr-28">
              <Sparkles className="h-4 w-4 shrink-0 text-app-accent" />
              <span className="app-text-body-sm min-w-0 truncate font-medium">
                {family.name}
              </span>
            </div>
            <span className="app-text-caption mt-1 block text-app-ink/40">
              {family.aspect}
            </span>
            {canPreview && (
              <div className="absolute right-2 top-2 flex gap-1">
                <button
                  type="button"
                  title={t('ai.pptGenerator.preview.button')}
                  onClick={(e) => {
                    e.stopPropagation();
                    props.onPreview(family.id);
                  }}
                  className="app-control h-7 px-2 shadow-sm hover:text-app-accent"
                >
                  <Eye className="h-3.5 w-3.5" />
                  <span className="app-text-caption">
                    {t('ai.pptGenerator.preview.button')}
                  </span>
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ============================================================
// Step 2 — 진행
// ============================================================
function formatDurationKo(
  t: (k: string, o?: Record<string, unknown>) => string,
  seconds: number,
): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 60) {
    return t('ai.pptGenerator.progress.elapsedMin', {
      minutes: Math.floor(s / 60),
      seconds: s % 60,
    });
  }
  return t('ai.pptGenerator.progress.elapsedSec', { seconds: s });
}

function ProgressPanel({
  message,
  percent,
  elapsedSeconds,
  heartbeatAgeSeconds,
  staleThresholdSeconds = 60,
  queued,
  onCancel,
  cancelling,
}: {
  message: string;
  percent: number;
  elapsedSeconds?: number;
  heartbeatAgeSeconds?: number | null;
  staleThresholdSeconds?: number;
  queued?: boolean;
  onCancel?: () => void;
  cancelling?: boolean;
}) {
  const { t } = useTranslation('apps');
  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  // 멈춤 경고는 '실행 중'인데 하트비트가 끊긴 경우에만. 큐 대기(pending)는 앞선 작업 때문에
  // 진행이 없을 뿐 뻑난 게 아니므로 경고 대신 '대기 중' 안내를 보인다.
  const stale =
    !queued &&
    typeof heartbeatAgeSeconds === 'number' &&
    heartbeatAgeSeconds > staleThresholdSeconds;
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-app-bg p-10 text-app-ink">
      <Loader2 className="h-10 w-10 animate-spin text-app-accent" />
      <p className="app-text-body-sm font-medium text-app-ink/75">{message}</p>
      <div className="w-full max-w-md">
        <div className="app-text-caption mb-1 flex justify-between text-app-ink/50">
          <span>{t('ai.pptGenerator.progress.label')}</span>
          <span className="font-semibold text-app-accent">{pct}%</span>
        </div>
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-app-surface-sidebar">
          <div
            className="h-full rounded-full bg-app-accent transition-all duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      {/* 경과 시간 — 항상 1초마다 증가해 '멈춤'으로 오해하지 않게 한다. */}
      {typeof elapsedSeconds === 'number' ? (
        <p className="app-text-caption text-app-ink/50">
          {formatDurationKo(t, elapsedSeconds)}
        </p>
      ) : null}
      {/* 큐 대기 중: 앞선 작업이 끝나길 기다리는 상태(뻑난 것 아님). */}
      {queued ? (
        <p className="app-text-caption max-w-md text-center text-app-ink/50">
          {t('ai.pptGenerator.progress.queued')}
        </p>
      ) : typeof heartbeatAgeSeconds === 'number' ? (
        stale ? (
          <p className="app-text-caption max-w-md text-center font-medium text-app-warning-text">
            {t('ai.pptGenerator.progress.stalled', {
              seconds: heartbeatAgeSeconds,
            })}
          </p>
        ) : (
          <p className="app-text-caption flex items-center gap-1.5 text-app-success-text">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-app-success" />
            {t('ai.pptGenerator.progress.alive', {
              seconds: heartbeatAgeSeconds,
            })}
          </p>
        )
      ) : (
        <p className="app-text-caption text-app-ink/40">
          {t('ai.pptGenerator.progress.estimate')}
        </p>
      )}
      {onCancel ? (
        <button
          type="button"
          onClick={onCancel}
          disabled={cancelling}
          className="app-control-ghost mt-1 h-9 px-4 text-app-ink/70 disabled:opacity-50"
        >
          {cancelling ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <X className="h-4 w-4" />
          )}
          {cancelling
            ? t('ai.pptGenerator.progress.cancelling')
            : t('ai.pptGenerator.progress.cancel')}
        </button>
      ) : null}
    </div>
  );
}

// ============================================================
// Step 3 — 결과 (미리보기 + 챗봇 수정)
// ============================================================
// 자유 양식 HTML 덱 미리보기 — sandboxed srcDoc iframe 을 컨테이너 폭에 맞게 스케일.
function HtmlDeckPreview({ html, slideW }: { html: string; slideW: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const frameHeight = Math.round(slideW * 0.72);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const update = () => setScale(el.clientWidth / slideW);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [slideW]);

  return (
    <div
      ref={wrapRef}
      className="mx-auto w-full max-w-5xl"
      style={{ height: frameHeight * scale }}
    >
      <iframe
        title="ppt-preview"
        srcDoc={html}
        sandbox=""
        scrolling="auto"
        style={{
          width: slideW,
          height: frameHeight,
          border: 0,
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
        }}
      />
    </div>
  );
}

function ResultPanel(props: {
  slides: PptSlide[];
  htmlDeck?: { html: string; slideW: number } | null;
  embedPreview?: { html: string; slideW: number; title: string } | null;
  slideCount: number;
  chatMessages: ChatMessage[];
  chatInput: string;
  setChatInput: (v: string) => void;
  chatBusy: boolean;
  onSendChat: () => void;
  onFinalize: () => void;
  onDownload: () => void;
  finalizeState: 'idle' | 'building' | 'ready' | 'error';
  researchSources?: {
    url: string;
    title?: string;
    query?: string;
    snippet?: string;
    page?: number;
    section?: string;
    block_kind?: string;
    used_in?: string;
  }[];
}) {
  const { t } = useTranslation('apps');
  const hasContent = props.slides.length > 0 || !!props.htmlDeck;
  const sources = props.researchSources ?? [];
  const sourceHost = (url: string): string => {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  };
  return (
    <div className="flex h-full min-h-0 bg-app-bg text-app-ink">
      {/* 챗봇 패널 */}
      <aside className="flex w-[340px] shrink-0 flex-col border-r border-app-border bg-app-bg">
        <div className="border-b border-app-border px-4 py-3">
          <span className="inline-flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-app-accent" />
            <span className="app-text-control-sm text-app-ink">
              {t('ai.pptGenerator.chat.title')}
            </span>
          </span>
        </div>
        <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-auto p-4">
          {props.chatMessages.length === 0 && (
            <p className="app-text-caption text-app-ink/40">
              {t('ai.pptGenerator.chat.placeholderHint')}
            </p>
          )}
          {props.chatMessages.map((m, i) => (
            <div
              key={i}
              className={cn(
                'app-text-body-sm rounded-md px-3 py-2',
                m.role === 'user'
                  ? 'ml-6 bg-app-accent text-app-accent-fg'
                  : 'mr-6 bg-app-surface-sidebar text-app-ink/75',
              )}
            >
              {m.role === 'assistant' && m.intent === 'edit' && (
                <span className="app-text-micro mb-1 inline-flex items-center gap-1 font-semibold text-app-accent">
                  <Pencil className="h-3 w-3" />
                  {t('ai.pptGenerator.chat.slideEdited')}
                </span>
              )}
              {m.content}
            </div>
          ))}
          {props.chatBusy && (
            <div className="app-text-body-sm mr-6 flex items-center gap-2 rounded-md bg-app-surface-sidebar px-3 py-2 text-app-ink/55">
              <Loader2 className="h-4 w-4 animate-spin" />{' '}
              {t('ai.pptGenerator.chat.editing')}
            </div>
          )}
        </div>
        <div className="border-t border-app-border p-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={props.chatInput}
              onChange={(e) => props.setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  props.onSendChat();
                }
              }}
              disabled={props.finalizeState === 'building'}
              placeholder={
                props.finalizeState === 'building'
                  ? t('ai.pptGenerator.chat.disabledPlaceholder')
                  : t('ai.pptGenerator.chat.inputPlaceholder')
              }
              className="app-field-input-sm h-9 flex-1 bg-app-bg disabled:bg-app-surface-sidebar disabled:text-app-ink/40"
            />
            <button
              type="button"
              onClick={props.onSendChat}
              disabled={props.chatBusy || props.finalizeState === 'building'}
              className="app-control-primary h-9 w-9 p-0"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* HTML 미리보기 갤러리 */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-app-border bg-app-bg px-6 py-2">
          <span className="app-text-body-sm text-app-ink/60">
            {t('ai.pptGenerator.result.slideCount', {
              count: props.slideCount || props.slides.length,
            })}
          </span>
          {props.finalizeState === 'ready' ? (
            <button
              type="button"
              onClick={props.onDownload}
              className="app-control-primary h-8 px-3"
            >
              <Download className="h-4 w-4" />{' '}
              {t('ai.pptGenerator.result.downloadPptx')}
            </button>
          ) : (
            <button
              type="button"
              onClick={props.onFinalize}
              disabled={
                props.finalizeState === 'building' ||
                props.chatBusy ||
                !hasContent
              }
              className="app-control-primary h-8 px-3"
            >
              {props.finalizeState === 'building' ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />{' '}
                  {t('ai.pptGenerator.result.finalizing')}
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />{' '}
                  {t('ai.pptGenerator.result.finalize')}
                </>
              )}
            </button>
          )}
        </div>
        <div className="custom-scrollbar min-h-0 flex-1 space-y-6 overflow-auto bg-app-surface-sidebar/30 p-6">
          {!hasContent && (
            <div className="app-text-body-sm rounded-md border border-app-warning-border bg-app-warning-bg p-4 text-app-warning-text">
              {t('ai.pptGenerator.chat.noSlides')}
            </div>
          )}
          {props.htmlDeck ? (
            <HtmlDeckPreview
              html={props.htmlDeck.html}
              slideW={props.htmlDeck.slideW}
            />
          ) : (
            props.slides.map((slide, i) => (
              <div key={i} className="mx-auto w-full max-w-4xl">
                <div className="app-text-overline mb-1.5 text-app-ink/40">
                  {t('ai.pptGenerator.result.slideLabel', { index: i + 1 })}
                </div>
                <PptSlideRenderer slide={slide} />
              </div>
            ))
          )}

          {/* 똑딱이(OLE 임베드) 내용 미리보기 — 데스크톱 PPT 에서 더블클릭 시 열리는 결과보고서 덱 */}
          {props.embedPreview && (
            <div className="mx-auto w-full max-w-5xl">
              <div className="app-text-body-sm mb-3 flex items-center gap-2 rounded-md border border-app-accent/30 bg-app-accent/10 px-4 py-2.5 text-app-accent">
                <Projector className="h-4 w-4 shrink-0" />
                <span>
                  <span className="font-semibold">
                    {t('ai.pptGenerator.embed.title', {
                      title: props.embedPreview.title,
                    })}
                  </span>
                  <span className="app-text-caption ml-1.5 text-app-accent/75">
                    {t('ai.pptGenerator.embed.note')}
                  </span>
                </span>
              </div>
              <HtmlDeckPreview
                html={props.embedPreview.html}
                slideW={props.embedPreview.slideW}
              />
            </div>
          )}
        </div>
      </div>

      {/* 참고 출처 패널 — 외부 웹 검색(Claude)으로 기초 정보 수집 시 참고한 출처 */}
      {sources.length > 0 ? (
        <aside className="flex w-[400px] shrink-0 flex-col border-l border-app-border bg-app-bg">
          <div className="border-b border-app-border px-5 py-3">
            <span className="app-text-body font-semibold text-app-ink">
              {t('ai.pptGenerator.result.sources')}
              <span className="ml-1.5 text-app-ink/40">({sources.length})</span>
            </span>
            <p className="app-text-body-sm mt-1 text-app-ink/50">
              {t('ai.pptGenerator.result.sourcesHint')}
            </p>
          </div>
          <div className="custom-scrollbar min-h-0 flex-1 space-y-2.5 overflow-auto p-4">
            {sources.map((s, i) => (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-lg border border-app-border bg-app-surface px-3.5 py-2.5 transition-colors hover:border-app-accent/50 hover:bg-app-accent/5"
              >
                <span className="app-text-body-sm block font-medium text-app-ink/90">
                  {s.title || s.url}
                </span>
                <span className="app-text-caption mt-1 block truncate text-app-accent/70">
                  {sourceHost(s.url)}
                </span>
                {s.page ? (
                  <span className="app-text-caption mt-1.5 inline-flex items-center gap-1 rounded-full border border-app-accent/30 bg-app-accent/10 px-2 py-0.5 font-medium text-app-accent">
                    {t('ai.pptGenerator.result.sourcePage', { page: s.page })}
                    {s.block_kind ? ` · ${s.block_kind}` : ''}
                    {s.section ? ` · ${s.section}` : ''}
                  </span>
                ) : null}
                {s.page && s.used_in ? (
                  <span className="app-text-caption mt-1 block text-app-ink/45">
                    {t('ai.pptGenerator.result.sourceUsedIn', {
                      excerpt: s.used_in,
                    })}
                  </span>
                ) : null}
                {s.snippet ? (
                  <span className="app-text-caption mt-1.5 block border-l-2 border-app-border pl-2 italic text-app-ink/55">
                    “{s.snippet}”
                  </span>
                ) : s.query ? (
                  <span className="app-text-caption mt-1.5 block text-app-ink/45">
                    {t('ai.pptGenerator.result.sourceQuery', {
                      query: s.query,
                    })}
                  </span>
                ) : null}
              </a>
            ))}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
