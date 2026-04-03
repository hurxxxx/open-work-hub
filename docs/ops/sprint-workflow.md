# 스프린트형 작업 흐름

## 목적

`gstack`의 `Think -> Plan -> Build -> Review -> Test -> Ship -> Reflect` 흐름에서 유효한 부분을 차용해, 이 저장소의 하네스 중심 작업 흐름으로 정리한다.

## 저장소용 흐름

1. 탐색
2. 시나리오 선택
3. 계약/계획 고정
4. 구현
5. 리뷰 및 평가
6. 문서 동기화
7. 릴리즈 판단
8. 회고 및 학습

## 단계별 규칙

### 1. 탐색

- 공식 문서, 기존 구현, 기존 eval 결과를 먼저 읽는다.
- 새로운 인프라나 라이브러리는 먼저 검색한다.

### 2. 시나리오 선택

- 작업은 정확히 하나의 `scenario_id`에 매핑한다.
- 시나리오 문서를 먼저 읽고 시작한다.

### 3. 계약/계획 고정

- `PromptContract`, `WorkflowProfile`, `ServiceGuardrailPolicy` 영향 범위를 적는다.
- release gate가 어떤 지표를 요구하는지 확인한다.

### 4. 구현

- 도메인 경계를 넘는 변경은 contract 또는 facade를 먼저 검토한다.
- prompt/workflow만 따로 바꾸지 않는다.

### 5. 리뷰 및 평가

- 관련 `golden`, `adversarial`, `shadow`, `drift` 중 무엇을 다시 볼지 정한다.
- scorecard 기준을 확인한다.

### 6. 문서 동기화

- 기능, API, 운영 플로우, eval 규칙이 바뀌었으면 관련 문서를 업데이트한다.
- 문서 원본은 `docs/*`, 도구별 파일은 어댑터로 취급한다.

### 7. 릴리즈 판단

- `ReleaseGateDecision`을 시나리오 단위로 본다.
- 안전성 실패는 바로 `hold`다.

### 8. 회고 및 학습

- durable learning은 반복 비용을 줄일 만큼 가치 있는 경우만 남긴다.
- checkpoint는 큰 작업의 상태 스냅샷으로 남긴다.
- retro는 다음 작업에서 반복 가능한 패턴과 병목을 정리한다.
