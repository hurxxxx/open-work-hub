# Learnings 및 Checkpoints

## 목적

`gstack`의 `learn`, `checkpoint`, `retro`, `document-release` 흐름 중 이 프로젝트에 맞는 부분을 문서화한다. 목표는 세 가지다.

- 반복되는 함정과 결정을 durable knowledge로 남긴다.
- 큰 작업의 중간 상태를 짧게 저장한다.
- 문서 최신화와 회고를 별도 작업으로 취급한다.

## 구분

### `learning`

앞으로 시간을 아껴줄 비직관적 인사이트다.

남겨야 하는 예:

- 특정 시나리오에서 잘 깨지는 fallback 규칙
- OCR 엔진별 품질 특성
- PLM validator의 중요한 경계 조건
- UI에서 반드시 지켜야 하는 밀도/패널 구조

남기지 말아야 하는 예:

- 너무 당연한 코딩 상식
- 일회성 실수
- 이미 문서에 충분히 적힌 사실

### `checkpoint`

큰 작업의 중간 상태와 다음 리스크를 남기는 짧은 스냅샷이다.

포함 항목:

- 현재 작업 범위
- 완료된 표면
- 아직 남은 위험
- 다음 추천 액션

### `document-release`

변경된 기능/규칙/API/운영 흐름과 문서의 최신성을 다시 맞추는 단계다.

### `retro`

완료 후 무엇이 잘 됐고 무엇을 표준화할지 정리하는 단계다.

## 저장 위치

- durable learning: [project-learnings.md](/Users/edward/projects/doowon/docs/ops/project-learnings.md)
- checkpoint: [project-checkpoints.md](/Users/edward/projects/doowon/docs/ops/project-checkpoints.md)

## 기록 형식

### learning

```text
date:
scenario_id:
type:
insight:
evidence:
impact:
```

### checkpoint

```text
date:
workstream:
scenario_id:
completed:
open_risks:
next_action:
```

## 사용 시점

- 설계나 운영에서 비직관적 결정을 발견했을 때 `learn`
- 작업이 커져서 중간 정리가 필요할 때 `checkpoint`
- 구현과 평가가 끝나고 문서가 뒤따라야 할 때 `document-release`
- 큰 단위 작업이나 스프린트가 끝났을 때 `retro`
