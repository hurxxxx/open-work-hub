# 문서 분류

이 저장소의 문서는 `실행 기준 문서` 와 `사람용 참고 문서` 를 분리해서 관리한다.

## 실행 기준 문서

- `docs/architecture/`: 시스템 구조, UI 거버넌스, 설계 기준
- `docs/agents/`: 에이전트 공통 규약, 컨텍스트 정책, helper 계약
- `docs/harness/`: scenario manifest, prompt bundle, eval, trace grading
- `docs/ops/`: release gate, sprint workflow, learn/checkpoint/retro
- `docs/ops/`: release gate, sprint workflow, learn/checkpoint/retro, 환경변수/시크릿 운영 기준

## 사람용 참고 문서

- `docs/planning/`: 킥오프, 과업범위, 제안/추진 계획
- `docs/product/`: 제품 방향, 기능 메모, 아이디어
- `docs/meetings/`: 발표 스크립트, 회의 준비 문서, 회의록

## 루트 원칙

- 루트에는 실행 진입점과 공통 에이전트 규칙만 남긴다.
- 공통 규칙 원본은 `agents.md` 다.
- `CLAUDE.md` 는 Claude Code 전용의 얇은 어댑터로만 유지한다.
