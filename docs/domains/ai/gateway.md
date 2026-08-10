# AI Gateway

Open Work Hub의 생성형 모델 호출은 등록된 workload와 공용 실행 게이트웨이를 사용한다.
앱 코드는 provider SDK나 외부 HTTP endpoint를 직접 선택하지 않는다.

## 계약

- workload는 안정적인 ID, 소유 도메인, 허용 route, capability와 출력 토큰 한도를 등록한다.
- 관리자가 활성 provider와 모델을 선택하며 로컬 장애를 외부 provider로 자동 전환하지 않는다.
- 외부 전송은 데이터 분류, 마스킹, 승인 정책과 감사 이벤트를 통과해야 한다.
- 도구 실행은 workspace/app 권한과 discoverability를 검사하고 쓰기 작업은 승인 게이트를 사용한다.
- 모델 호출과 결과에는 actor, workspace, workload, provider/model, token 사용량과 trace ID를 남긴다.

구현 정본은 `apps/api/src/open_work_hub_api/domains/ai/`와 등록 bootstrap이다.
