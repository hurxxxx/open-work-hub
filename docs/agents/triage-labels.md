# Triage Labels

현재 GitHub 저장소는 GitHub 기본 라벨 집합을 사용한다. 존재하지 않는 workflow 상태 라벨을
추정하거나 자동으로 만들지 않는다.

| 역할 | GitHub 라벨 | 규칙 |
| --- | --- | --- |
| 결함 | `bug` | 보고된 동작이 확인됐거나 그럴듯한 결함일 때만 사용한다. |
| 기능 요청 | `enhancement` | 새 기능이나 기존 동작 확장을 요청할 때 사용한다. |
| 문서 | `documentation` | 주된 결과물이 문서 개선일 때 사용한다. |
| 정보 필요 | `question` | 재현 정보, 범위 또는 maintainer 판단이 더 필요할 때 사용한다. |
| 종결 사유 | `duplicate`, `invalid`, `wontfix` | 이유를 댓글로 남긴 뒤 해당 사유로 닫을 때 사용한다. |
| 기여 안내 | `good first issue`, `help wanted` | maintainer가 외부 기여에 적합하다고 판단할 때만 사용한다. |

현재 `needs-triage`, `ready-for-agent` 같은 상태 라벨은 없다. 자동 작업 준비 상태는 이슈 본문에
완전하고 테스트 가능한 brief와 미결정 사항이 없음을 체크리스트로 남긴다. 향후 상태 라벨을
도입하면 한 이슈에 상충하는 상태 라벨을 동시에 두지 않는 별도 계약을 먼저 정한다.

라벨을 읽거나 바꾸기 전에 live vocabulary를 확인한다.

```bash
gh label list --limit 100
```

라벨 생성·수정·삭제는 저장소 외부 상태를 바꾸므로 사용자가 요청한 경우에만 수행한다.
