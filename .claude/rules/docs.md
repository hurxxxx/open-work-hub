---
paths:
  - "docs/**/*"
  - ".claude/**/*"
  - ".codex/skills/doowon-harness-engineering/**/*"
  - "CLAUDE.md"
  - "agents.md"
---

# Documentation Rules

- 문서 언어는 한국어를 기본으로 하고, 시나리오/타입/버전 키는 영어 식별자로 쓴다.
- 도구별 어댑터는 규칙을 새로 만들지 않고 `docs/*` 원본을 참조해야 한다.
- 하네스 문서는 설명뿐 아니라 입력/출력 계약, manifest, prompt bundle, gate 기준까지 포함해야 한다.
- 에이전트 규약 문서를 수정하면 `CLAUDE.md`, `.claude/rules`, `.claude/commands`, repo-owned skill projection 일관성도 함께 점검한다.
- 기능/운영/하네스가 바뀌면 `document-release` 관점으로 문서 최신성을 점검한다.
- 루트 메모리에 들어갈 문서는 최소화하고, 상세 규칙은 선택적으로 읽게 설계한다.
