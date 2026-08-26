# GitHub Copilot Instructions

이 저장소에서 코드나 문서를 제안·수정하기 전에 루트 `AGENTS.md` 전체를 읽고 따른다.
`AGENTS.md`가 공통 규칙의 유일한 정본이며, 현재 변경 표면에 연결된 owner 문서와 ADR만 추가로
읽는다.

프로젝트명, Python package와 환경변수는 현재 코드의 `Open Work Hub`, `open_work_hub_api`,
`OPEN_WORK_HUB_*`를 사용한다. GitHub는 원본 upstream으로만 취급하고, 이 사이트의 변경과 이슈·병합
흐름은 GitLab `origin`의 Issue/MR 계약을 따른다. 별도 요청 없이 commit, push, MR 생성 또는 merge를
하지 않으며, 검증은 `package.json`에 실제로 존재하는 script와 focused test를 사용한다.
