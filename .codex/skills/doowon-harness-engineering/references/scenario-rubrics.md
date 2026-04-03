# Scenario Rubrics

## `documents-rag`

- Focus: retrieval relevance, citation completeness, groundedness, ACL correctness
- Required docs:
  - `docs/harness/scenarios/documents-rag.md`
  - `docs/harness/eval-regression-spec.md`

## `plm-query`

- Focus: unsafe SQL blocking, template routing, execution accuracy, summary fidelity
- Required docs:
  - `docs/harness/scenarios/plm-query.md`
  - `docs/harness/eval-regression-spec.md`

## `draft-generation`

- Focus: field fill rate, citation block attachment, unsupported claim rate, export integrity
- Required docs:
  - `docs/harness/scenarios/draft-generation.md`
  - `docs/harness/service-runtime-harness.md`

## `ocr-pipeline`

- Focus: parse completeness, table extraction, layout preservation, catastrophic failures
- Required docs:
  - `docs/harness/scenarios/ocr-pipeline.md`
  - `docs/harness/service-runtime-harness.md`

## `wiki-pms`

- Focus: action classification, schema validity, unauthorized mutation blocking, grounded summaries
- Required docs:
  - `docs/harness/scenarios/wiki-pms.md`
  - `docs/harness/service-runtime-harness.md`
