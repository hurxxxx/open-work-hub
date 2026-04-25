# 22. Git 브랜치 전략 — 개발/운영 분리

> **한 줄 요약.** 브랜치 전략은 단순한 절차가 아니라 **사고를 구조적으로 막는 장치**다. main 한 줄로 굴리는 팀과 잘 분리한 팀의 출시 사고 빈도는 차원이 다르다.

---

## 들어가며

Git 은 거의 모든 팀이 씁니다. 그런데 같은 도구를 쓰면서도 어떤 팀은 매끄럽게 출시하고, 어떤 팀은 매번 사고가 납니다. 차이는 도구가 아니라 **브랜치를 어떻게 굴리는가** 입니다.

레슨 02 의 사례 3 을 떠올려 보세요. main 한 줄로 굴리던 팀이 미완성 기능과 핫픽스가 동반 출시되는 사고를 본 그 사례. 이건 거의 모든 작은 팀이 한 번씩 겪는 통과의례입니다.

이 레슨은 처음 시작하는 팀이 안전하게 굴릴 수 있는 **가벼운 브랜치 전략** 과, 규모가 커지면 어떻게 진화시킬지를 정리합니다.

이 레슨을 다 읽으면:

- 브랜치 전략이 왜 출시 속도와 안정성을 결정하는지 안다.
- GitHub Flow·GitLab Flow·Git Flow 의 차이를 안다.
- 처음 만드는 팀에 권장하는 단순 전략을 안다.
- 핫픽스·릴리즈·기능 브랜치를 구분하고 적용할 수 있다.
- PR 리뷰·자동 검사의 기본 패턴을 안다.

---

## 1. 핵심 개념 — 브랜치는 무엇을 분리하는가

### 1.1 브랜치의 본질 — 시간의 갈림길

Git 의 한 커밋은 하나의 부모를 가집니다. 브랜치는 **그 시간의 갈림길**입니다. 한 시점에서 시작해 다른 방향으로 자라나는 평행 선.

```
        ┌─→ feature/login    ←→ 새 기능 개발
        │
main ───┼─→
        │
        └─→ feature/signup   ←→ 다른 새 기능 개발
```

각 브랜치는 독립적으로 자라다가 나중에 main 으로 합쳐(merge)집니다.

### 1.2 브랜치가 분리하는 것

| 분리 대상 | 왜 분리 |
|---|---|
| **개발 중인 기능** | 미완성이 운영에 들어가지 않게 |
| **버그 수정** | 핵심 기능 작업 중에 끼어든 긴급 수정 |
| **운영 버전** | 안정된 상태가 항상 있어야 |
| **개발자별 작업** | 동시 작업 충돌 방지 |
| **환경별 설정** | 개발·staging·운영 |

### 1.3 좋은 브랜치 전략의 조건

| 조건 | 의미 |
|---|---|
| **항상 배포 가능한 main** | main 을 그대로 운영에 올려도 OK |
| **명확한 기능 단위** | 한 브랜치 = 한 기능 또는 수정 |
| **짧은 수명** | 며칠 이내에 main 으로 합쳐짐 |
| **자동 검사 통과** | 머지 전 테스트·린트 자동 |
| **명확한 책임자** | 누가 만들고 누가 리뷰했는지 |

---

## 2. 주요 브랜치 전략 — 3가지

### 2.1 GitHub Flow (가장 단순) ⭐

main 하나 + 기능 브랜치들. 출시 속도가 빠른 SaaS·웹 서비스에 적합.

```
main ───●──────●──────●──────●──→
        ↑      ↑      ↑      ↑
        │      │      │      │
   feature/  feature/ fix/  feature/
   login     signup   bug   profile
```

**규칙:**
- main 은 항상 배포 가능 상태.
- 새 작업은 main 에서 새 브랜치를 따고.
- 작업 끝나면 PR 으로 main 으로 머지.
- 머지되면 자동 배포.

**장점:** 단순. 쉽게 시작.
**단점:** 릴리즈 버전을 따로 관리하기 어려움.

**처음 만드는 팀에 가장 권장.**

### 2.2 GitLab Flow (환경별 브랜치)

main + 환경별 브랜치 (staging·production).

```
main ─────●──────●──────●──→         (개발 통합)
          │      │
staging ──┴──────●──────●──→         (staging 환경)
                 │
production ──────┴──────●──→         (운영 환경)
```

**규칙:**
- main 으로 머지 → staging 으로 자동 배포.
- staging 검증 후 production 브랜치로 머지 → 운영 배포.

**장점:** 환경 간 차이 명확.
**단점:** 약간 더 복잡.

### 2.3 Git Flow (전통, 무거움)

main · develop · feature · release · hotfix 다섯 종류.

```
main      ────●─────────────●─────●──→     (운영 릴리즈)
              │             │     │
release       │      ●──────┘     │
              │      │             │
develop   ────●──────●──────●─────●──→      (개발 통합)
              ↑      ↑      ↑     ↑
        feature   feature feature hotfix
```

**규칙:**
- 새 기능 → develop 에서 분기.
- 릴리즈 준비 → release 브랜치 → main 머지.
- 운영 버그 → hotfix 브랜치 → main + develop 동시 머지.

**장점:** 릴리즈 버전 관리에 강함.
**단점:** 복잡, 빠른 출시에 부적합. 모바일 앱처럼 버전 단위 출시에 적합.

---

## 3. 처음 시작하는 팀의 권장 전략

### 3.1 GitHub Flow + 약간의 보강

가장 단순하고 안전한 시작점:

- **main 브랜치** — 항상 배포 가능.
- **기능 브랜치** (`feature/login`·`fix/typo` 등) — 작업 단위.
- **PR 으로만 main 에 머지** — 직접 푸시 금지.
- **PR 마다 자동 테스트** 통과해야 머지 가능.
- **최소 1명의 리뷰 승인** — 혼자 일해도 셀프 리뷰의 뜻.

### 3.2 브랜치 명명 규칙

| 접두어 | 용도 | 예시 |
|---|---|---|
| `feature/` | 새 기능 | `feature/couple-invitation` |
| `fix/` | 버그 수정 | `fix/login-redirect-loop` |
| `chore/` | 잡일 (의존성 업데이트 등) | `chore/upgrade-react` |
| `refactor/` | 리팩터링 | `refactor/extract-payment` |
| `docs/` | 문서 | `docs/update-readme` |
| `hotfix/` | 운영 긴급 | `hotfix/null-pointer-on-checkout` |

브랜치 이름이 곧 작업 설명. 이름만 봐도 무엇인지 알 수 있게.

### 3.3 일하는 흐름 한 사이클

```bash
# 1. main 최신화
git checkout main
git pull origin main

# 2. 새 브랜치
git checkout -b feature/couple-invitation

# 3. 작업 + 커밋
# ... 코드 변경 ...
git add .
git commit -m "feat(couple): add invitation code generation"

# 4. 푸시 + PR
git push -u origin feature/couple-invitation
# → GitHub UI 에서 PR 생성

# 5. 리뷰·자동 검사 통과 → 머지
# 6. 브랜치 삭제 (자동 또는 수동)
```

---

## 4. 커밋·PR 관리

### 4.1 좋은 커밋 메시지

```
<type>(<scope>): <subject>

<body — 왜 이 변경을 했는지>

<footer — 이슈 번호 등>
```

예시:

```
feat(couple): add invitation code generation

Couple invitation flow needs a unique short code that can be sent via
KakaoTalk. Generate 8-char base32 codes with 24h expiry.

Closes #42
```

`type` 의 흔한 분류 (Conventional Commits):

| type | 의미 |
|---|---|
| feat | 새 기능 |
| fix | 버그 수정 |
| docs | 문서 |
| style | 포맷팅 |
| refactor | 리팩터링 |
| test | 테스트 |
| chore | 잡일 |
| perf | 성능 개선 |

### 4.2 PR 의 크기

작은 PR 이 좋습니다. 큰 PR 의 단점:

- 리뷰가 어렵다 (대충 OK 누름).
- 머지 충돌 위험.
- 문제 발생 시 원인 파악 어려움.
- 롤백이 위험.

**한 PR = 한 가지 일.** 200~400 줄 변경이 적당. 1000 줄 넘어가면 분리 검토.

### 4.3 PR 리뷰

리뷰어가 봐야 할 것:

- **로직** — 의도대로 동작하는가.
- **테스트** — 새 기능에 테스트가 있는가.
- **에지 케이스** — 빈 입력·에러·동시성.
- **보안** — 입력 검증·권한 검사.
- **성능** — N+1 쿼리·과도한 호출.
- **가독성** — 6개월 후의 자기가 읽을 수 있는가.

### 4.4 PR 자동 검사

CI 가 PR 마다 자동 실행:

- Lint·Format
- 단위·통합 테스트
- 빌드 성공
- 보안·취약점 스캔
- (선택) E2E

GitHub repo 설정 "Require status checks to pass" 켜기. 통과 안 하면 머지 불가.

---

## 5. 머지 전략 — Merge / Squash / Rebase

main 으로 합칠 때 3가지 방식.

### 5.1 Merge Commit

머지 커밋이 따로 생성. 브랜치 히스토리 보존.

```
main ──●──●──●─────────────●──
            \             /
             ●──●──●──●──● feature
```

**장점:** 작업 흐름이 그대로 보임.
**단점:** 히스토리가 복잡해짐.

### 5.2 Squash Merge ⭐

기능 브랜치의 여러 커밋을 한 커밋으로 압축해 main 에.

```
main ──●──●──●──●──●──     (한 PR = 한 커밋)
```

**장점:** main 히스토리가 깔끔. 한 커밋 = 한 기능.
**단점:** 브랜치의 작은 커밋들이 사라짐.

**처음 시작에 가장 권장.** GitHub 의 PR 옵션 중 "Squash and merge".

### 5.3 Rebase

기능 브랜치의 커밋을 main 끝으로 옮겨 붙임. 직선 히스토리.

```
main ──●──●──●──●──●──●──●──     (직선)
```

**장점:** 가장 깔끔.
**단점:** 충돌 처리가 어려움. 익숙해야 함.

---

## 6. 운영 사고 시나리오

### 6.1 핫픽스 (Hotfix)

운영에 긴급 버그 발견. 일반 흐름을 끊지 않으면서 빠르게 수정.

**GitHub Flow 의 핫픽스:**

```
1. main 에서 hotfix/xxx 브랜치
2. 빠른 수정 + 테스트
3. PR → 빠른 리뷰 → main 머지
4. 자동 배포
```

main 이 항상 배포 가능 상태이기 때문에 가능.

**Git Flow 의 핫픽스 (모바일 앱 등):**

```
1. main 에서 hotfix/xxx 브랜치 (운영 버전 기준)
2. 수정
3. main + develop 양쪽에 머지
4. 새 패치 버전 태그 (v1.0.1)
5. 빌드·배포
```

### 6.2 롤백 (Rollback)

새 배포가 망가졌을 때 이전 버전으로 되돌림.

**옵션 A. 이전 버전 재배포** — 가장 안전. 이미지·산출물에 버전이 명확하다면 이전 태그를 다시 배포.

**옵션 B. revert 커밋** — main 에 revert 커밋을 추가, 자동 배포.

```bash
git revert <bad-commit>
git push origin main
```

`git reset --hard` 같은 파괴적 명령은 절대 main 에 안 함 (다른 사람의 작업 사라짐).

### 6.3 충돌 (Merge Conflict)

같은 파일·줄을 두 사람이 동시 수정. 머지 시 Git 이 어느 쪽을 선택할지 모름.

```
<<<<<<< HEAD
const TIMEOUT = 30;
=======
const TIMEOUT = 60;
>>>>>>> feature/timeout
```

해결: 둘 중 하나를 고르거나 합쳐 적기. 작은 PR + 자주 main pull 이 충돌 줄임.

---

## 7. 자주 빠지는 함정

### 함정 1. main 에 직접 푸시

작은 팀이 자주 하는 일. 모든 변경은 PR 을 거치게. GitHub repo 설정 "Branch protection" 으로 강제.

### 함정 2. 브랜치를 너무 오래 둠

3주된 feature 브랜치는 main 과 점점 멀어져 충돌 폭증. **며칠 이내에** 머지.

### 함정 3. PR 이 너무 큼

1000줄 넘는 PR 은 리뷰 안 됨. 분할.

### 함정 4. 커밋 메시지가 "fix" 한 줄

6개월 후 자기가 자기 커밋을 못 알아봄. 의미 있는 메시지.

### 함정 5. 강제 푸시 (force push) 남발

`git push --force` 는 다른 사람의 커밋을 지울 수 있음. 자기 브랜치에서만, 그것도 신중히. main 에는 절대 금지.

### 함정 6. 핫픽스 후 develop 에 안 머지

Git Flow 에서 hotfix 를 main 에만 적용하고 develop 에 안 옮기면, 다음 배포 시 같은 버그가 다시 등장. 양쪽 머지 필수.

### 함정 7. 자동 검사 없이 머지

CI 통과 안 하고 "급하니까" 머지. 깨진 main → 다른 팀 작업 영향.

### 함정 8. 시크릿 커밋

`.env`·API 키를 실수로 커밋. 한 번 git history 에 들어가면 영원히 흔적이 남음. 발견 즉시 키 회수·새로 발급. **`git secret scan` 도구**를 PR 자동 검사에.

### 함정 9. 거대 파일 커밋

이미지·동영상·DB 덤프를 git 에 커밋. 저장소 용량 폭증. **Git LFS** 사용 또는 외부 저장소.

### 함정 10. 브랜치 이름이 의미 없음

`my-branch`·`fix1`·`tmp` — 누구도 모름. 명명 규칙.

---

## 8. 한 셜 더

### 8.1 Trunk-Based Development

GitHub Flow 의 더 단순한 버전. 모두가 main(=trunk) 에 직접 머지하되, 매우 짧은 브랜치(몇 시간)·기능 토글로 미완성을 숨김.

대규모 팀이 빠른 출시를 위해 채택. 처음에는 GitHub Flow 가 무난.

### 8.2 Feature Flag

미완성 기능을 main 에 머지하되 사용자에겐 안 보이게.

```ts
if (featureFlags.coupleInvitationV2) {
  // 새 흐름
} else {
  // 기존 흐름
}
```

장점:
- main 이 항상 배포 가능.
- 점진적 출시 (1% → 10% → 100%).
- 즉시 롤백 (플래그 OFF).

도구: LaunchDarkly·GrowthBook·Flagsmith·Unleash.

### 8.3 모노레포의 브랜치

여러 패키지가 한 저장소에 있을 때, 영향받는 패키지만 빌드·테스트. **Nx affected**·**Turbo**·**Bazel** 같은 도구.

### 8.4 Conventional Commits + Semantic Release

Conventional Commits 형식의 커밋을 자동 분석해 시맨틱 버저닝과 CHANGELOG 자동 생성.

```bash
npx semantic-release
# main 머지마다 자동으로 새 버전 태그·릴리즈 생성
```

### 8.5 추가 키워드

- **Code Owners** — 파일별 자동 리뷰어 지정 (CODEOWNERS 파일).
- **Dependabot** — 의존성 자동 업데이트 PR.
- **Branch Protection Rules** — main 에 직접 푸시·강제 푸시 차단.
- **Required Reviews** — 특정 인원의 승인 강제.
- **Stacked PRs** — 의존하는 PR 들을 쌓아서 작업.

---

## 마치며

오늘 한 일:

- 브랜치 전략의 **본질**과 좋은 전략의 조건.
- **3가지 전략** (GitHub Flow·GitLab Flow·Git Flow) 비교.
- 처음 만드는 팀에 권장: **GitHub Flow + Squash Merge**.
- 커밋·PR 관리, 자동 검사, 머지 전략.
- 핫픽스·롤백·충돌 시나리오.
- 함정 10가지.

다음 레슨 [`23. 배포 인프라 — 클라우드 vs Vercel/CF`](./23-배포-인프라.md) 에서는 빌드된 산출물을 **어디에 어떻게 띄울지** 결정하는 영역으로 들어갑니다.

다음 페이지에서 만나요.
