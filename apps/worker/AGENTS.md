# Worker App Rules

- `apps/worker` 는 비동기 작업 조립 계층이다.
- Celery app, queue routing, background task registration 만 직접 소유한다.
- 문서 동기화, OCR, export 같은 작업은 task 모듈에서만 확장한다.
