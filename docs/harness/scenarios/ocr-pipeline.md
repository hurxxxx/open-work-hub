# Scenario: ocr-pipeline

## goal

스캔 문서, 이미지, 복잡 레이아웃 PDF에서 텍스트와 구조를 안정적으로 추출해 검색/초안 생성 파이프라인에 넘길 수 있는 표준 출력으로 정규화한다.

## input schema

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `asset_uri` | string | yes | 원문 위치 |
| `mime_type` | string | yes | 파일 타입 |
| `language_hint` | string | no | 언어 추정 |
| `layout_mode` | enum | no | `plain`, `table-heavy`, `mixed` |
| `priority` | enum | no | `interactive`, `batch` |

## allowed tools

- Native extractor
- OCR need classifier
- OCR engine router
- Qwen3-VL-8B-Thinking
- DeepSeek-OCR
- PaddleOCR-VL-1.5
- Normalizer
- Quality judge

## prompt contract

- OCR 출력은 항상 `plain_text`, `markdown`, `layout_blocks`, `tables`, `confidence`, `artifacts`를 포함한다.
- 엔진 선택 이유와 fallback 여부를 메타데이터에 남긴다.
- 품질이 낮으면 성공으로 표시하지 않고 fallback 또는 human review로 넘긴다.

## retrieval policy

- native extractor 결과가 충분하면 OCR을 생략한다.
- OCR 필요 판정 후 페이지 유형에 따라 엔진을 선택한다.
- 기본 정책은 품질 우선이며, 실패 시 대체 엔진으로 1회 재시도한다.

## failure modes

- 페이지 전체 공백 추출
- 표 구조 붕괴
- 섹션 순서 뒤바뀜
- 매우 느린 페이지 처리

## expected output

- 후속 검색/색인에 투입 가능한 정규화 텍스트
- 레이아웃과 표 구조 메타데이터
- 품질 점수와 fallback 이력

## eval rubric

- `parse_completeness`
- `table_extraction_f1`
- `layout_preservation`
- `catastrophic_failure_rate`
- `page_latency_p95`
