# Worker App

Celery 기반 background worker다.

주요 task 영역:

- 문서/RAG 동기화
- OCR/문서 추출
- 회의/녹음 처리
- 메일 동기화
- 검색 색인
- 초안 export

저장소 루트에서 실행:

```bash
./dev.sh --with-worker
```

로컬 환경은 루트 `.env.example`을 기준으로 별도의 `.env`를 구성한다.
비밀값과 운영 데이터는 저장소에 커밋하지 않는다.
