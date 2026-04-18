# Planning Log

완료된 실행 플랜의 요약 기록. 활성 플랜은 [`plans/`](../plans/) 디렉터리에 있다.

## 운영 규칙

- 플랜이 PR 머지로 완료되면 [`plans/`](../plans/)에서 해당 파일을 제거하고, **여기에 1개 엔트리 추가**.
- 세부 변경 내용은 GitHub PR/커밋에 있으니 이 로그는 **인덱스**로만 사용. 장황한 내용 금지.
- 엔트리 형식:

  ```markdown
  ## YYYY-MM-DD · 플랜 제목

  - **요약**: 1~2 문장.
  - **PR/커밋**: #123, abc1234
  - **영향 파일**: 주요 디렉터리/모듈
  - **남은 후속 작업**: (있다면)
  ```

- 최신 항목을 위로(descending).

---

## 엔트리

<!--
여기에 완료된 플랜을 추가하세요. 템플릿:

## 2026-04-20 · Phase 1 — LLM Pool Routing Foundation

- **요약**: 로컬/외부 풀 완전 분리, LlmPolicy DB 테이블 도입, PII 정규식 탐지, 감사 로그 통합.
- **PR/커밋**: #XX, ...
- **영향 파일**: `apps/api/src/aidoo_api/core/`, `apps/api/src/aidoo_api/domains/ai/`
- **남은 후속 작업**: 관리자 알람 채널 결정 (Phase 6 연계)
-->

_아직 완료된 플랜이 없다._
