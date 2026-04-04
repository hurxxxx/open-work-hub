# Eval Assets

이 디렉터리는 시나리오별 eval 입력과 `promptfoo` 실행 자산을 저장한다.

## 구성

- `datasets/<scenario-id>/`
  - `golden.jsonl`
  - `adversarial.jsonl`
  - `shadow.jsonl`
  - 필요 시 `drift.jsonl`
- `promptfoo/scenarios/<scenario-id>.yaml`
  - 선언형 eval 설정
  - 실제 provider 는 환경변수로 주입

## 원칙

- eval 입력은 문서 설명이 아니라 실행 가능한 데이터셋 형태로 유지한다.
- `ScenarioManifest`, `EvalSuite`, `TraceGradeSpec` 와 dataset 이름을 맞춘다.
- 샘플 케이스는 skeleton 이며, 실제 운영 데이터를 추가할 때도 같은 필드 구조를 유지한다.

## 실행 기본 예시

```bash
PROMPTFOO_PROVIDER=openai:responses:gpt-4.1-mini \
promptfoo eval -c docs/harness/evals/promptfoo/scenarios/documents-rag.yaml
```

실제 운영에서는 provider id 를 온프레미스 또는 승인된 서비스 런타임에 맞게 바꾼다.
