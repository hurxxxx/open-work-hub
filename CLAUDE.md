# Claude Code Instructions

@AGENTS.md

`AGENTS.md`가 이 저장소의 공통 에이전트 지침 정본이다. Claude Code는 작업 전에 전체를 읽고,
현재 변경 표면에 해당하는 owner 문서와 project skill만 추가로 읽는다. 이 파일은 Claude Code
도구 실행 환경에 필요한 노트만 둔다.

## Skill Discovery

프로젝트 skill의 정본은 `.agents/skills/<name>/SKILL.md`다. Claude Code가 skill을 발견하려면
`.claude/skills`가 `.agents/skills`를 가리키는 symlink여야 한다.

```bash
test -L .claude/skills && test "$(readlink .claude/skills)" = ../.agents/skills
```

없거나 깨졌으면 정본을 복제하지 말고 symlink만 복구한다. `.claude/skills`는 머신 로컬 노출물이며
일반 지침 사본을 두지 않는다.

## GitLab MR Workflow

- GitLab `origin`이 사이트 변경의 canonical remote이고 GitHub `upstream`은 원본 코드 수신용이다.
- 기능 변경은 feature branch에서 `dev`로 GitLab MR을 만들고, 운영 승격은 `dev`에서 protected
  `main`으로 GitLab MR을 만든다.
- MR을 만들거나 ready 상태로 넘기기 전에는 구현과 focused 검증을 마치고 native `/review`를 실행한다.
- `/review` workflow가 보이지 않으면 `.agents/skills/open-work-hub-mr-review-validation/SKILL.md`
  절차를 직접 수행하고 fallback으로 수행했다는 사실과 남은 위험을 MR 본문 또는 최종 보고에 적는다.
- MR publisher, Codex CI runner와 release validation pipeline이 다음 단계에서 추가되기 전까지는
  해당 자동 gate가 통과했다고 주장하지 않는다. 직접 `glab`으로 외부 상태를 바꾸는 행동은 사용자가
  명시적으로 요청했을 때만 한다.

## Evidence Discipline

- MR evidence와 review는 latest source SHA와 target merge result에 결합한다.
- Source가 바뀌면 affected checks와 review를 다시 수행한다.
- Target head가 바뀌어 merged surface가 달라지면 merge-result diff와 관련 검증을 다시 본다.
- 시크릿, credentialed remote, `.env` 내용, raw prompt, 운영 데이터는 prompt, review comment,
  artifact 또는 diff에 넣지 않는다.
