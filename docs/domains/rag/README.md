# RAG

RAG는 사용자가 읽을 수 있는 workspace 문서를 검색하고 근거가 포함된 답변을 만드는 범용 기능이다.

## 활성 소스

- Docs native documents
- Files sources activated through the Files operator gate

각 소스는 자체 ACL과 projection adapter를 소유한다. Backend의 workspace나 visibility metadata는
최종 권한 정본이 아니며, 응답·요약·인용 직전에 소스 ACL을 다시 확인한다.

문서 추출, chunking, embedding과 vector/keyword projection은 versioned outbox 계약을 따른다.
모델이나 index schema를 바꿀 때는 별도 generation을 구축·검증한 뒤 활성 generation을 전환한다.

현재 source 상태는 [Source Matrix](source-matrix.md)를 참고한다.
