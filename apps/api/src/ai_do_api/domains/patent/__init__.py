"""AI 특허 작성 (patent compose) domain.

Stateless, synchronous tool ported from the legacy Flask ``patent-compose``
feature: KIPRIS (Korean patent office) search + LLM-assisted summaries,
reports, and search-formula generation. Each request makes at most one KIPRIS
call and one LLM call, so there is no job/worker/DB machinery here.
"""
