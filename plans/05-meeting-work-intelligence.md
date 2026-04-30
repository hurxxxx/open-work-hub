# Meeting Work Intelligence MVP

## Context

현재 AI 레이어는 LLM routing, streaming envelope, MCP-shaped capability bridge, approval flow, meeting insight extraction, local/external model routing의 기반을 갖고 있다. 최근 장문 논문과 `Talk_2026.4.29 17:39-1.txt` 카카오톡/회의형 원문으로 local model과 external reviewer를 비교한 결과, local model은 장문 내부 문서를 읽고 구조화하는 데 충분히 쓸 수 있지만 `확정/예정/논의/추정`을 섞어 단정하는 위험이 있었다. External model은 최종 문장 품질과 안전성에서 우위였지만 raw internal data egress 문제가 있다.

따라서 다음 실행 단위는 범용 챗봇 또는 manager runtime 확장이 아니라 **회의록/채팅 원문을 업무 항목으로 바꾸는 제품 vertical slice**다. 목표는 사용자가 자연어로 모든 일을 지시하게 만드는 것이 아니라, 정해진 wizard를 통해 원문을 안전하게 분석하고 PMS/Planner에 반영 가능한 초안으로 만드는 것이다.

## Architecture / Principles

1. **Local-first raw data processing**
   - 회의록, 전사, 카카오톡 export, 내부 문서 원문은 기본적으로 configured local model profile만 읽는다.
   - 외부 모델은 사용자가 명시적으로 외부 전송을 허용한 경우에만 reviewer/writer 역할로 사용한다.
   - 외부 전송 허용 시에도 기본 payload는 raw 원문이 아니라 structured extraction result와 필요한 최소 source quote다.

2. **Structured extraction before free-form summary**
   - 산출물은 자유 요약보다 업무화 가능한 구조를 우선한다.
   - 모든 의미 있는 항목은 `kind`, `title/statement`, `description`, `certainty`, `source_quote`, `source_date`, `source_speaker`, `confidence`, `target_app`, `proposed_write_payload`를 가진다.
   - `certainty`는 `confirmed`, `planned`, `discussed`, `inferred`, `needs_confirmation` 중 하나로 제한한다.

3. **Evidence and approval stay internal**
   - PMS/Planner 반영은 기존 approval-gated capability를 사용한다.
   - AI는 write payload 초안만 만들고, 실제 생성/수정은 사용자 승인 후 실행한다.
   - Docs는 v1에서 read-only로 유지한다.

4. **Wizard-first UX**
   - `/w/:workspace/ai`는 순수 챗봇 시작보다 작업 카드 중심으로 전환한다.
   - v1 카드: `회의록 업무화`, `액션아이템 만들기`, `결정사항 정리`, `PMS 태스크 초안 생성`.
   - 챗은 제거하지 않고, wizard 결과를 더 다듬는 보조 경로로 둔다.

## Implementation Stages

### Stage 1 - Backend extraction contract

- 기존 `MeetingInsight`와 호환되는 meeting work intelligence DTO를 정의한다.
- 긴 transcript/text는 현재 12,000자 excerpt 방식이 아니라 `chunk extract -> merge -> verifier` 흐름으로 처리한다.
- local-only mode에서 external adapter 호출이 절대 일어나지 않도록 policy test를 추가한다.
- malformed model output은 partial result 또는 clear failure로 저장한다.

### Stage 2 - Golden sample quality gate

- `Talk_2026.4.29 17:39-1.txt`를 golden sample로 사용한다. 파일 자체는 repo-tracked fixture로 즉시 편입하지 않고, 필요 시 별도 sanitized fixture를 만든다.
- acceptance 기준:
  - 2024.9.26 중토위 승인, 2024.12.19 본지구 지정, 2025.8.1 매매 허용, 2025.8.7 총회, 2026.4 시행령/일정 논의를 누락하지 않는다.
  - `확정`, `예정`, `논의`, `확인 필요`를 구분한다.
  - 감사/축하/중복 공유/잡담은 주요 action item으로 만들지 않는다.
  - PMS/Planner write payload는 승인 전 실행되지 않는다.

### Stage 3 - AI work wizard UI

- AI 홈에 작업 카드 영역을 추가하고 `회의록 업무화` wizard를 우선 구현한다.
- wizard 단계:
  1. 입력 선택: meeting recording, text file, paste.
  2. 처리 정책 선택: 기본 `로컬만 사용`, optional `외부 리뷰 허용`.
  3. 분석 실행: 진행률, 청크 수, model route 표시.
  4. 결과 검토: 요약, 결정사항, 액션아이템, 리스크, 확인 필요 탭.
  5. 업무 반영: 선택 항목을 PMS task 또는 Planner event approval preview로 전달.

### Stage 4 - Optional external review

- 외부 리뷰는 raw 원문 전송이 아니라 local structured extraction result 기반으로 먼저 붙인다.
- 사용자가 raw 원문 외부 전송을 명시 허용한 경우에만 raw text review를 별도 옵션으로 제공한다.
- external reviewer는 local extraction의 `certainty`를 임의로 강화할 수 없고, 변경 제안은 diff/review comment로만 표시한다.

## Verification

- Backend unit:
  - 긴 transcript가 청크로 나뉘고 모든 청크가 merge 입력에 포함된다.
  - `certainty` 없는 항목은 `needs_confirmation`으로 강등된다.
  - local-only policy에서 external adapter가 호출되지 않는다.
  - malformed JSON/model output은 clear failure 또는 partial result로 남는다.
- Backend integration:
  - meeting recording 기반 extraction refresh.
  - text file/paste 기반 extraction job.
  - action item을 PMS task approval preview로 변환.
  - schedule item을 Planner event approval preview로 변환.
- Web:
  - AI 카드 화면에서 `회의록 업무화` wizard 진입.
  - local-only 기본 선택.
  - 결과 탭 렌더링.
  - 선택한 action item만 approval modal로 전달.
- E2E:
  - 서버 + 브라우저에서 텍스트 회의록 업로드.
  - 분석 완료 후 결정사항/액션아이템 확인.
  - 하나의 PMS task 초안을 승인하고 생성 확인.
  - 외부 전송 허용/비허용 모드의 routing 차이를 확인.

## Decision Log

| 항목 | 결정 |
|---|---|
| 현재 실행 우선순위 | Meeting Work Intelligence vertical slice |
| 기본 raw data 처리 | configured local model profile |
| 외부 모델 역할 | 명시 허용된 reviewer/writer |
| 기본 UX | 작업 카드 + wizard |
| 챗봇 역할 | wizard 결과 후속 보조 경로 |
| Docs write | v1 제외, read-only |
| PMS/Planner write | 기존 approval-gated capability 사용 |
| Golden sample | `Talk_2026.4.29 17:39-1.txt` 기반 장문 카톡/회의록 품질 회귀 |
| Manager runtime expansion | 후속 후보로 보류 |

## Rollback Plan

- UI 변경이 불안정하면 AI 홈의 작업 카드/wizard만 feature flag로 끄고 기존 AI chat 화면으로 되돌린다.
- Backend extraction 계약 변경이 불안정하면 기존 `meeting.extract_actions`, `meeting.extract_decisions` read tool 동작을 유지하고 새 structured extraction path만 비활성화한다.
- External review가 품질 또는 egress 정책 문제를 만들면 local-only mode만 남기고 external reviewer option을 숨긴다.
