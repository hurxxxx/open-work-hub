# API App

FastAPI 기반의 조립 계층이다. 현재 스캐폴드는 아래를 제공한다.

- 앱 팩토리와 설정 로딩
- health endpoint
- Ollama/OpenAI 호환 LLM 연결과 readiness endpoint
- 문서 검색, PLM 조회, 템플릿/초안, 위키 페이지의 최소 placeholder endpoint
- 도메인 루트와 local rule 파일

실행:

```bash
cp .env.example .env
pnpm nx dev api
```

LLM 기본값은 로컬 Ollama의 OpenAI 호환 API를 사용한다.

```env
DOOWON_LLM_PROVIDER=ollama
DOOWON_LLM_BASE_URL=http://127.0.0.1:11434/v1
DOOWON_LLM_API_KEY=ollama
DOOWON_LLM_DEFAULT_MODEL=qwen3.5:35b-a3b-q4_K_M
```

준비 상태 확인:

```bash
curl http://127.0.0.1:8000/readyz
```
