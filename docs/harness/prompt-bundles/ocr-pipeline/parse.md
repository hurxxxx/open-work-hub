# ocr-pipeline parse

역할: 선택된 엔진의 표준 출력 형식을 정의한다.

- 출력은 항상 아래 필드를 포함한다.
  - `plain_text`
  - `markdown`
  - `layout_blocks`
  - `tables`
  - `confidence`
  - `artifacts`

구조가 불충분하면 성공으로 표시하지 않는다.
