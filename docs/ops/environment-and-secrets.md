# 환경변수 및 시크릿 관리

## 기본 원칙

- 저장소 기준 환경변수 템플릿은 루트 `.env.example` 이다.
- 실제 값은 루트 `.env` 또는 `.env.local` 에만 둔다.
- `.env`, `.env.local` 은 Git에 커밋하지 않는다.
- 앱별로 따로 흩어진 `.env` 를 만들기보다 루트 기준 파일 하나를 우선 사용한다.

## 현재 로딩 규칙

- API 앱은 루트 `.env.local` -> 루트 `.env` 순서로 읽는다.
- Worker 앱도 같은 순서로 읽는다.
- 향후 ops/tooling 도 같은 루트 기준을 따른다.

## 현재 템플릿에 포함한 범주

- `DOOWON_API_*`: FastAPI 앱 설정
- `DOOWON_WORKER_*`: Celery worker 설정
- `DOOWON_OPENROUTER_*`: OpenRouter 키와 base URL
- `DOOWON_REPLICATE_*`, `REPLICATE_API_TOKEN`: Replicate 키, base URL, Replicate 전용 모델 slug
- `DOOWON_LLM_DEFAULT_MODEL`, `DOOWON_EMBEDDING_MODEL`, `DOOWON_RERANKER_MODEL`, `DOOWON_OCR_*`: 모델/엔진 기준값
- `DOOWON_POSTGRES_*`, `DOOWON_REDIS_*`, `DOOWON_OPENSEARCH_*`, `DOOWON_QDRANT_*`, `DOOWON_MINIO_*`: 공용 인프라 연결값

## 권장 provider 라우팅

- `OpenRouter`: `Qwen3.5` 기본 생성, `Qwen3-Embedding-8B`, `Qwen3-VL-8B-Thinking`
- `Replicate`: `Qwen3-Reranker-8B`, `DeepSeek-OCR`
- `Custom hosting`: `PaddleOCR-VL-1.5`

`Custom hosting` 의 1차 후보는 다음 3가지다.

- `Hugging Face Inference Endpoints`: Hugging Face 모델 저장소 기반 배포가 자연스러울 때
- `Baseten`: OpenAI-compatible endpoint 와 관리형 배포가 필요할 때
- `Runpod Serverless`: 커스텀 worker 와 GPU 제어권이 더 중요할 때

현재 기본 템플릿은 위 기준을 그대로 반영한다.

- `DOOWON_LLM_PROVIDER=openrouter`
- `DOOWON_EMBEDDING_PROVIDER=openrouter`
- `DOOWON_RERANKER_PROVIDER=replicate`
- `DOOWON_OCR_PRIMARY_PROVIDER=openrouter`
- `DOOWON_OCR_FALLBACK_PROVIDER=replicate`
- `DOOWON_OCR_SECONDARY_PROVIDER=custom`

`REPLICATE_API_TOKEN` 은 Replicate SDK/CLI 호환용 선택 변수다. 앱 내부 표준 키는 `DOOWON_REPLICATE_API_TOKEN` 이고, 둘 다 사용할 때는 같은 값을 유지한다.

## 사용 방법

```bash
cp .env.example .env
```

그 다음 실제 환경에 맞게 값을 채운다.

## 주의사항

- 프로덕션 시크릿은 `.env` 대신 배포 환경의 secret manager 또는 CI/CD secret store를 우선한다.
- OpenRouter API 키, Replicate API 키, DB 비밀번호, MinIO secret key는 예시 값을 그대로 사용하지 않는다.
