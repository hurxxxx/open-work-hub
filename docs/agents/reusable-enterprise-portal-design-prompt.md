# 재사용용 엔터프라이즈 포털 디자인 프롬프트

이 파일은 새 화면이나 새 프로젝트에서 `좌측 사이드바 중심`, `엔터프라이즈 포털`, `AI스럽지 않은 시각 언어`를 요구할 때 재사용하는 프롬프트다.

## 사용 방법

- 아래 프롬프트의 placeholder만 현재 작업에 맞게 바꾼다.
- 먼저 [enterprise-portal-design-direction.md](/Users/edward/projects/doowon/docs/architecture/enterprise-portal-design-direction.md)를 읽고 사용한다.
- 디자인 지시는 루트 메모리에 넣지 않고 프론트엔드 작업에서만 선택적으로 로드한다.

## Prompt

```text
You are designing and implementing an authenticated enterprise portal screen.

Product context:
- Product: <PRODUCT_NAME>
- Screen or workflow: <SCREEN_OR_WORKFLOW>
- Primary users: <PRIMARY_USERS>
- Primary task: <PRIMARY_TASK>
- Secondary tasks: <SECONDARY_TASKS>
- Device priority: desktop first, responsive to tablet/mobile

Non-negotiable design direction:
- This is an internal or enterprise-grade product surface, not a marketing landing page.
- Use a persistent left sidebar on desktop as the primary navigation surface.
- Use a compact top utility/header area for context, status, and cross-cutting actions.
- Use the center area as the main work surface.
- Use the right side only for contextual details, evidence, or short actions.
- Search can be prominent, but it must not replace information architecture.

Visual style:
- Calm, modern, product-grade, and durable.
- Neutral surfaces, crisp borders, restrained radius, minimal shadows.
- Moderate-to-high information density.
- Strong hierarchy through spacing, typography, selection state, and borders before color.
- Prefer technically credible typography over trendy default AI-generated choices.
- Use a limited palette with one clear accent and disciplined status colors.

Preferred UI patterns:
- sidebar navigation
- toolbar / filter bar
- table or list-detail layout
- split panes
- right-side drawer for supplemental info

Component governance:
- Before creating a new UI pattern, check whether a shared component already exists.
- If it does not exist, add it to the shared UI package first instead of implementing a local one-off version.
- Do not directly import low-level third-party UI libraries from feature or page code; use the shared UI wrapper layer.
- badges, breadcrumbs, saved views, inline states

Avoid these patterns:
- hero-first landing page layout
- oversized marketing headline blocks
- bento grids or decorative metric cards as the main structure
- purple gradients on white backgrounds
- glassmorphism, neon glow, excessive blur
- card soup
- vague “AI magic” styling
- decorative motion that does not support task flow

Interaction expectations:
- Navigation labels should be short, plain, and stable.
- The user should always know: where they are, what is selected, what evidence supports the current answer, and what the next action is.
- Drawers should support short contextual tasks only.
- If a workflow is complex, keep it in the main content area instead of hiding it in a drawer.

Design references to borrow interaction patterns from:
- GitHub Primer
- GitLab Pajamas
- Microsoft Fluent 2
- IBM Carbon

What to deliver:
1. A short explanation of the layout and why it fits an enterprise portal.
2. A concrete screen structure with sidebar, header, content zones, and optional right pane.
3. A restrained visual direction with reusable tokens.
4. Accessible, realistic labels and UI copy.
5. Production-grade implementation, not a mock hero page.

Before coding, briefly explain how your proposal avoids generic AI-generated UI patterns.
```

## 메모

- 이 프롬프트는 `보기 좋은 AI 데모` 보다 `실제로 오래 쓰는 업무 툴`을 만들기 위한 프롬프트다.
- 필요하면 도메인별로 `documents-rag`, `plm-query`, `draft-generation`, `wiki-pms` 맥락을 추가한다.
