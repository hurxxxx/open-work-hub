# Inference Gateway Domain

Inference Gateway는 Open Work Hub API와 worker가 embedding, reranking, 문서 파싱 및 음성
인식 백엔드를 동일한 HTTP 계약으로 호출하게 한다. 실제 모델과 하드웨어 배치는 배포 환경이
선택하며 애플리케이션 코드는 특정 호스트나 장비를 전제로 하지 않는다.

LLM 호출 정책, 감사, 사용량과 비용 귀속은 [AI Gateway 계약](../ai/gateway.md)을 따른다.
