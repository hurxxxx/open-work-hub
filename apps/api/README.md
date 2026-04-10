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

LLM 기본값은 로컬 Ollama의 OpenAI 호환 API를 우선 사용하고, 로컬 모델이 준비되지
않았거나 요청이 실패하면 OpenRouter를 fallback으로 사용한다. 품질 관리를 위해 로컬과
fallback 모두 같은 Qwen3.5-35B-A3B 모델군으로 고정한다.

```env
DOOWON_LLM_PROVIDER=ollama
DOOWON_LLM_BASE_URL=http://127.0.0.1:11434/v1
DOOWON_LLM_API_KEY=ollama
DOOWON_LLM_DEFAULT_MODEL=qwen3.5:35b-a3b-q4_K_M
DOOWON_LLM_CANONICAL_MODEL=qwen/qwen3.5-35b-a3b
DOOWON_LLM_FALLBACK_ENABLED=true
DOOWON_LLM_FALLBACK_PROVIDER=openrouter
DOOWON_LLM_FALLBACK_MODEL=qwen/qwen3.5-35b-a3b
DOOWON_OPENROUTER_API_KEY=
DOOWON_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

준비 상태 확인:

```bash
curl http://127.0.0.1:8000/readyz
```

챗봇 요청은 기본 `backend_mode=auto`로 로컬 Ollama를 먼저 사용하고 실패 시 OpenRouter로
넘어간다. UI 또는 API 요청에서 `backend_mode=local`이나 `backend_mode=openrouter`를
보내면 해당 backend만 사용한다.
