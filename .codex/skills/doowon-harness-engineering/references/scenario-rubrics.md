# Scenario Rubrics

## `documents-rag`

- Focus: retrieval relevance, citation completeness, groundedness, ACL correctness
- Required docs:
  - `docs/harness/manifests/scenarios/documents-rag.json`
  - `docs/harness/prompt-bundles/documents-rag/workflow.json`
  - `docs/harness/scenarios/documents-rag.md`
  - `docs/harness/manifests/eval-suites/documents-rag.json`

## `plm-query`

- Focus: unsafe SQL blocking, template routing, execution accuracy, summary fidelity
- Required docs:
  - `docs/harness/manifests/scenarios/plm-query.json`
  - `docs/harness/prompt-bundles/plm-query/workflow.json`
  - `docs/harness/scenarios/plm-query.md`
  - `docs/harness/manifests/eval-suites/plm-query.json`

## `draft-generation`

- Focus: field fill rate, citation block attachment, unsupported claim rate, export integrity
- Required docs:
  - `docs/harness/manifests/scenarios/draft-generation.json`
  - `docs/harness/prompt-bundles/draft-generation/workflow.json`
  - `docs/harness/scenarios/draft-generation.md`
  - `docs/harness/manifests/eval-suites/draft-generation.json`

## `ocr-pipeline`

- Focus: parse completeness, table extraction, layout preservation, catastrophic failures
- Required docs:
  - `docs/harness/manifests/scenarios/ocr-pipeline.json`
  - `docs/harness/prompt-bundles/ocr-pipeline/workflow.json`
  - `docs/harness/scenarios/ocr-pipeline.md`
  - `docs/harness/manifests/eval-suites/ocr-pipeline.json`

## `wiki-pms`

- Focus: action classification, schema validity, unauthorized mutation blocking, grounded summaries
- Required docs:
  - `docs/harness/manifests/scenarios/wiki-pms.json`
  - `docs/harness/prompt-bundles/wiki-pms/workflow.json`
  - `docs/harness/scenarios/wiki-pms.md`
  - `docs/harness/manifests/eval-suites/wiki-pms.json`
