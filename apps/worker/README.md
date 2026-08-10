# Worker App

Celery 기반 background worker다.

주요 task 영역:

- 문서/RAG 동기화
- OCR/문서 추출
- 회의/녹음 처리
- 메일 동기화
- 이미지 생성
- 검색 색인
- 초안 export
- spec compare

실행:

```bash
cd /projects/open-alm/dev
./dev.sh --with-worker
```

서버 dev와 로컬 개발자 환경의 worker 기동 방식은
[`open-alm-development-environment`](../../.agents/skills/open-alm-development-environment/SKILL.md)
절차를 따른다. 로컬 개발자 머신에서 루트 `.env`를 새로 만들지 않는다.
