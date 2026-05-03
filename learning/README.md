# Learning Content

`/w/<workspace>/learning` 앱이 이 디렉터리의 markdown 을 읽어 렌더합니다.
콘텐츠는 **코스 단위** 로 관리합니다. 코스 하나 = 폴더 하나.

## 디렉터리 규칙

```
learning/
├── README.md                         ← 이 문서
└── <course-slug>/                    ← 코스 = 폴더
    ├── 00-index.md                   ← 코스 서문·읽기 순서 (선택)
    ├── 01-<lesson-title>.md          ← 레슨 (번호로 정렬 유지)
    ├── ...
    ├── A-<appendix-title>.md         ← 부록 (A, B, ... 로 정렬)
    └── assets/                       ← 코스 전용 이미지·도표 (필요 시)
```

- 코스 슬러그는 소문자 ASCII + 하이픈 (`vibe-coding-foundations`).
- 레슨 파일명은 번호 prefix 를 유지합니다 (`01-`, `02-` ... ). 정렬 기준이자 자동 목차의 근거가 됩니다.
- 파일명 자체는 한글이어도 됩니다 — 저자가 목록에서 바로 알아볼 수 있는 쪽이 우선입니다. URL slug 는 매니페스트에서 별도로 ASCII 로 선언합니다.

## 새 코스 추가 체크리스트

1. `learning/<new-course-slug>/` 폴더 생성.
2. `00-index.md` 에 코스 개요·대상·학습 목표를 적습니다. (선택이지만 추천)
3. 레슨 파일을 `NN-<title>.md` 로 추가.
4. `apps/web/src/domains/learning/manifest.ts` 의 `LEARNING_COURSES` 배열에 코스 엔트리 추가:

   ```ts
   {
     slug: 'new-course-slug',
     title: '코스 제목',
     description: '한 줄 설명',
     parts: [
       {
         slug: 'intro',
         title: '시작하기',
         lessons: [
           { id: 'ncs-001-intro', slug: '01-intro', title: '도입', file: 'new-course-slug/01-도입.md' },
           // ...
         ],
       },
     ],
   }
   ```
5. `pnpm vitest run -c apps/web/vite.config.mts apps/web/src/domains/learning/manifest.spec.ts` 로 매니페스트 무결성 확인 (각 `file` 이 실제 파일과 매칭되고 `id` 가 유일한지 자동 검증).
6. 브라우저에서 `/w/<workspace>/learning` 진입 → 새 코스 카드가 보이면 OK.

## 본문 vs 학습 노트

러닝 콘텐츠에는 두 개의 저장소가 있고, **용도가 다릅니다**.

| 구분 | 저장소 | 누가 쓰나 | 원복 방법 | 용도 |
| --- | --- | --- | --- | --- |
| **본문** | `learning/**/*.md` (Git) | 관리자(PR) | `git revert` | 레슨의 공식 텍스트. 본문 오류 정정도 전부 여기서 PR로 처리. |
| **학습 노트** | DB (`NativeDoc` / `NativeDocPage`) | 학습자 본인 | 노트 archive / 재저장 | **개인 학습 노트**. 내가 이 레슨을 읽으며 든 생각·요약·질문. 원하면 공개로 공유 가능. |

운영 규칙:

- **본문 정정은 관리자가 PR로.** 학습 노트는 본문 오류를 고치는 도구가 아닙니다. 노트에 "이 본문 틀렸어요"라고 써도 다른 학습자가 그 정정이 공식인지 개인 의견인지 구분할 수 없습니다. 오류를 발견하면 관리자에게 알려 PR로 처리하세요.
- **노트는 본문을 앵커하지 않습니다.** 레슨 단위(lesson id) 로만 붙습니다. 본문이 리라이팅되어도 노트가 고아가 되지 않습니다.
- **레슨당 한 사용자 = 하나의 노트.** 섹션 헤딩으로 노트 안에서 여러 주제를 구조화하세요.
- **공개 범위는 `비공개`/`공개` 둘 중 하나.** 기본값은 비공개. 공개로 바꾸면 다른 학습자의 목록에도 나타납니다.
- **비공개 노트는 본인만 봅니다.** 관리자도 비공개 노트를 열람하지 못합니다.
- **lesson `id` 는 변경하지 않습니다.** URL slug·파일명·제목은 바꿔도 되지만 `id` 는 DB 노트 매핑의 불변 키입니다.
- **Manifest 에서 삭제된 lesson 의 노트는 자동 노출되지 않습니다.** DB 에는 `source_ref` 기준으로 남아 있으므로 필요하면 staff 도구로 확인·정리하세요.

## 기존 코스

| 슬러그 | 제목 | 설명 |
| --- | --- | --- |
| `vibe-coding-foundations` | 바이브 코딩 입문 | 소프트웨어·프로그래밍 기본부터 AIDOO 스택, 실전 워크플로까지. 전 구성원 공용 온보딩 트랙. |
| `database-storage-basics` | 데이터베이스 입문 — 저장소를 고르는 법 | SQL, NoSQL, 캐시, 검색, 벡터 DB, 객체 저장소까지 초보자 눈높이로 비교하는 저장소 선택 트랙. |

## 스타일 팁

- **박스 다이어그램(`┌┬┐└┴┘`) 금지** — monospace 에서 한글 폭과 ASCII 폭이 달라 정렬이 깨집니다. 대신 markdown table 또는 구조화된 목록을 쓰세요.
- 디렉터리 트리(`├── │ └──`) 는 한 열이라 정렬 걱정 없이 써도 됩니다.
- 코드 예제는 언어 힌트를 붙이면 (```` ```ts ```` 등) syntax highlighting 이 켜집니다.
