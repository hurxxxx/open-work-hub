# Inference Gateway Domain

Inference Gateway 도메인 문서는 AI-DO 메인 API/worker와 분리된 로컬 추론 백엔드 운영 기준을 둔다.
LLM 호출 정책, audit, 사용량/비용 귀속, throttling 계획은 [AI Gateway 계약과 로드맵](../ai/gateway.md)을
정본으로 본다.

## 문서

- [Inference Gateway 운영 문서](backend-operations.md): embedding, reranker, Docling, ASR 풀로드 백엔드 운영과 DGX Spark 배치.
- [DGX Spark Local LLM 운영 계약](dgx-spark-servers.md): 모델 전환, served name, endpoint, 진단 대상 선언.

RAG 모델 선정 검토 문서는 저장소 정본 문서로 유지하지 않는다.
