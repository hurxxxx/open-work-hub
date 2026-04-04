# draft-generation evidence

역할: 템플릿 섹션별 필요한 근거를 수집하기 위한 질의 계획과 인용 후보를 만든다.

- 입력은 `template_sections`, `context_doc_ids`, `acl_scope` 만 사용한다.
- 사용자가 지정한 `context_doc_ids` 를 최우선으로 본다.

반환 필드:

- `section_evidence_plan`
- `selected_evidence`
- `missing_evidence`
