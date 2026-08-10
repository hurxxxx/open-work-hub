# Open Work Hub LLM/RAG 운영 전문 교육

> **한 줄 요약.** 이 폴더는 기존 `vibe-coding-foundations`, `database-storage-basics`, `service-launch-journey` 교재를 다시 요약하는 곳이 아니라, Open Work Hub PoC에 필요한 LLM/RAG 운영 지식을 프로젝트 중심으로 보강하는 전문 교육 자료다.

## 정리 원칙

Open Work Hub 12주 PoC의 주간교육은 기존 교재와 신규 교재를 섞어 운영한다. 이미 충분히 만들어진 기본 교재는 원본 코스를 그대로 쓰고, 이 폴더는 기존 코스에 없는 LLM/RAG 운영 교육만 맡는다.

하루 교육 시간이 1시간 이상 확보된다는 전제로, 이 폴더의 각 회차는 단순 개념 소개가 아니라 “설계 판단 → 운영 기준 → 실습 산출물”까지 이어지게 구성한다. 특정 프레임워크 사용법만 익히는 교육이 아니라, AI 엔지니어가 모델·검색·데이터·보안·평가를 함께 볼 수 있도록 만드는 것이 목표다.

| PoC 주차 | 교육 주제 | 사용할 교재 |
| --- | --- | --- |
| W2 | AI 시대 협업과 좋은 요청 | `learning/vibe-coding-foundations/01-오리엔테이션.md`, `12-AI시대의-개발과-바이브코딩.md`, `14-프롬프트-워크북.md` |
| W3 | 작업 분해와 프롬프트 설계 | `learning/vibe-coding-foundations/14-프롬프트-워크북.md`, `17-기획과-요구사항-정의.md`, `35-바이브코딩-실전워크플로.md` |
| W4 | AI 결과 검수와 변경 관리 | `learning/vibe-coding-foundations/04-버전관리-Git.md`, `13-검증과-테스트.md`, `35-바이브코딩-실전워크플로.md` |
| W5 | LLM 모델 지형과 RAG 기초 | 이 폴더의 `04`, `05` |
| W6 | 문서 인덱싱 파이프라인 | 이 폴더의 `06` |
| W7 | 검색 품질: 키워드·벡터·재정렬 | 이 폴더의 `07` |
| W8 | AI 도구 호출과 승인 게이트 | 이 폴더의 `08` |
| W9 | 평가·관측·운영 품질 | 이 폴더의 `09` |
| W10 | 데이터베이스와 저장소 선택 | `learning/database-storage-basics/08-Search-Vector-Object-Storage.md`, `09-처음-서비스에서-DB를-고르는-체크리스트.md` |
| W11 | 아이디어에서 출시까지 | `learning/service-launch-journey/02-서비스개발-한눈에보기.md`, `05-MVP의-진짜의미.md`, `10-데이터설계-ERD.md`, `11-API설계.md` |
| W12 | 회고와 운영 인계 | `learning/service-launch-journey/26-운영-유지보수.md`, `27-장애대응-모니터링.md` |

## 수강자와 선수 지식

이 과정의 수강자는 Open Work Hub PoC에 참여하는 개발자, 데이터/업무 시스템 담당자, 현업 기획자, 운영 담당자를 함께 가정한다. 모든 수강자가 모델 학습 코드를 직접 작성할 필요는 없지만, 다음 판단은 할 수 있어야 한다.

| 영역 | 알아야 하는 이유 |
| --- | --- |
| LLM 모델 지형 | 외부 API, 사내 LLM, open-weight 모델을 업무 위험도와 비용에 맞춰 나누기 위해 |
| RAG와 검색 | “모델이 틀렸다”와 “검색이 틀렸다”를 분리해서 개선하기 위해 |
| 문서 파이프라인 | 원본, 파싱 결과, chunk, metadata, ACL, index 버전이 모두 답변 품질에 영향을 주기 때문에 |
| 보안과 승인 | AI가 도구를 호출하거나 문서를 읽을 때 권한·감사·승인 절차가 필요하기 때문에 |
| 평가와 관측 | 모델·prompt·embedding·index 변경을 감으로 배포하지 않기 위해 |

## 이 폴더의 범위

| 파일 | PoC 주차 | 역할 |
| --- | --- | --- |
| `04-LLM기초와-모델라우팅.md` | W5 | LLM 모델 지형을 읽는 법, Dense/MoE, 멀티모달 모델, 내부/외부 라우팅 기준 |
| `05-RAG와-근거기반답변.md` | W5 | RAG 패턴, 근거 기반 답변 설계, Open Work Hub 문서/업무 시스템 질의 흐름 |
| `06-문서인덱싱-파이프라인.md` | W6 | 원본 저장, OCR/파싱, 청킹, 메타데이터, ACL, 증분 색인 |
| `07-검색품질-키워드-벡터-재정렬.md` | W7 | BM25, 벡터 검색, 하이브리드 검색, reranking, 멀티모달 검색 품질 |
| `08-AI도구호출과-승인게이트.md` | W8 | capability 설계, read/write 구분, 승인 게이트, 감사 로그, 프롬프트 인젝션 방어 |
| `09-평가관측-운영품질.md` | W9 | 평가셋, retrieval/generation metric, trace, 모델 비교, 운영 대시보드 |

## 차시별 산출물

각 회차는 수업 뒤 바로 PoC 산출물로 이어져야 한다.

| PoC 주차 | 차시 | 수업 후 산출물 |
| --- | --- | --- |
| W5 | `04`, `05` | Open Work Hub 모델 라우팅 표, RAG 질문 유형 20개, 근거 기반 답변 카드 초안 |
| W6 | `06` | 샘플 문서 1개에 대한 인덱싱 계약서, metadata/ACL 설계, 재색인 조건 |
| W7 | `07` | 대표 질문별 keyword/vector/hybrid/rerank 전략 비교표, 검색 실패 진단표 |
| W8 | `08` | capability 명세서, read/write 승인 정책, prompt injection 방어 체크리스트 |
| W9 | `09` | 50문항 평가셋 스키마, trace 필드 목록, 모델·인덱스 릴리즈 게이트 |

## 교육 목표

수강자는 이 과정을 마친 뒤 다음 질문에 답할 수 있어야 한다.

| 질문 | 기대 답변 방향 |
| --- | --- |
| LLM 계열은 무엇이 다른가? | reasoning, multimodal, tool use, long context, open-weight, Dense/MoE 구조 차이를 설명한다. |
| 내부 LLM과 외부 API는 어떻게 나누나? | 데이터 등급, 업무 위험도, 품질, 비용, 지연시간, 감사 요구를 기준으로 라우팅한다. |
| RAG는 왜 단순 벡터 검색이 아닌가? | 문서 수집, 권한, 검색, reranking, 답변 생성, 출처 표시, 평가가 모두 품질에 영향을 준다. |
| 업무 시스템 데이터는 RAG로만 풀면 되는가? | 품번/BOM 같은 구조화 데이터는 SQL/API 검색, 변경 사유/회의록 같은 비정형 데이터는 RAG로 분리한다. |
| 모델이 좋아지면 운영 문제가 사라지나? | 모델 품질과 별도로 데이터 품질, 권한, 평가셋, trace, 승인 절차가 필요하다. |

## AI 엔지니어 필수 역량으로 보강할 내용

Open Work Hub의 현재 기술 스택에 당장 없더라도, AI 엔지니어 양성 관점에서는 아래 내용을 최소한의 판단 언어로 익혀야 한다.

| 역량 | 이 과정에서 다루는 방식 |
| --- | --- |
| Token/context engineering | 긴 문서를 그대로 넣지 않고, 질문에 맞는 근거를 고르고 압축하는 기준을 익힌다. |
| Structured output | JSON schema, tool input, citation contract처럼 후속 시스템이 읽을 수 있는 출력 설계를 익힌다. |
| Model serving | GPU 메모리, quantization, KV cache, batching, timeout, fallback을 모델 선택 기준에 넣는다. |
| Fine-tuning vs RAG | prompt, RAG, fine-tuning, distillation, classifier를 언제 쓰는지 구분한다. |
| Data governance | 원본 보존, lineage, PII masking, ACL propagation, audit log를 RAG 설계에 포함한다. |
| Agent/tool safety | MCP/API/tool 호출에서 권한, sandbox, dry-run, approval gate를 분리한다. |
| LLMOps | 평가셋, trace, 비용, latency, release gate, incident response를 운영 루프로 묶는다. |

## 참고 원천

- 공급사 공식 모델 문서: OpenAI, Anthropic, Google Gemini 등.
- Open-weight model card와 release note: Llama, Qwen, Mistral, DeepSeek 등.
- RAG 연구와 운영: Lewis et al. 2020 RAG, Self-RAG, RAG 평가 survey, ColBERT/late interaction, Ragas, OpenTelemetry GenAI, OWASP LLM Top 10, MCP specification.

모델 이름과 가격, 컨텍스트 길이, 제공 방식은 빠르게 바뀐다. 실제 도입 전에는 반드시 공급사 공식 문서와 사내 보안 정책을 최신 기준으로 다시 확인한다.
