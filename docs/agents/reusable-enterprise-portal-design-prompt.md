# 재사용용 프론트엔드 디자인 프롬프트

이 파일은 새 화면을 만들거나 기존 화면을 수정할 때, 현재 제품의 대표 화면과 공통 컴포넌트를 기준으로 일관성을 유지하게 하는 짧은 프롬프트다.

## 사용 방법

- 먼저 [enterprise-portal-design-direction.md](/Users/edward/projects/doowon/docs/architecture/enterprise-portal-design-direction.md)를 읽는다.
- 대표 화면과 공통 컴포넌트를 확인한 뒤 아래 프롬프트의 placeholder만 현재 작업에 맞게 바꾼다.

## Prompt

```text
You are updating an existing product surface.

Before designing or coding, inspect the representative screens and shared components in this repository.

Task:
- Product or area: <PRODUCT_OR_AREA>
- Screen or workflow: <SCREEN_OR_WORKFLOW>
- Primary user action: <PRIMARY_USER_ACTION>

Requirements:
- Keep the design consistent with the existing main dashboard, app shell, and shared UI components.
- Reuse shared components before creating a new local pattern.
- Match the current layout, spacing, typography, color, border, radius, shadow, and interaction style.
- Prefer small, consistent changes over a new visual direction.

What to deliver:
1. A short note on which representative components you matched.
2. Production-ready implementation that stays visually consistent with the current product.
```
