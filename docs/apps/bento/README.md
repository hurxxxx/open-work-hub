# bento/slides

Open Work Hub는 공식 `bento/slides` 단일 HTML 릴리스를 별도 출처의 iframe으로
임베딩한다. 문서 목록, 권한, 보관 상태와 문서 JSON은 Open Work Hub가 관리하고,
슬라이드 편집과 `.bento.html` 직렬화는 공식 Bento 런타임이 담당한다.

## 고정 버전과 공급망

- 원본 저장소: <https://github.com/nyblnet/bento>
- 릴리스: `v1.0.17`
- 소스 리비전: `efc0fab48ed1a9531bb1ae2a652a091832f64254`
- 릴리스 파일 SHA-256:
  `06026f088399a7422696ef122f424f09d4735fd128ae398392af31ce50ebdf9b`
- 라이선스: MIT

[`ops/bento/Dockerfile`](../../../ops/bento/Dockerfile)은 위 릴리스 파일과 라이선스,
제3자 고지를 내려받은 뒤 각각의 체크섬을 검증한다. 검증된 HTML에는 Work Hub 전용
브리지만 추가한다. 원본 버전을 올릴 때는 릴리스 태그, 소스 리비전, 세 체크섬을 한
변경으로 갱신하고 컨테이너 빌드와 브라우저 저장 흐름을 다시 검증한다.

## 로컬 실행

전체 개발 인프라를 시작하면 Bento도 함께 실행된다.

```bash
./scripts/dev-infra.sh up
```

Bento만 빌드하고 실행하려면 다음 명령을 사용한다.

```bash
docker compose --env-file .env.example \
  -f ops/compose/open-work-hub-dev.infra.yml up -d --build bento
```

기본 접근 주소는 `http://127.0.0.1:18084/`이고 상태 확인 주소는 `/healthz`다.
웹 앱은 이 별도 출처를 iframe으로 연다.

## 환경 변수

| 변수                             | 용도                      | 기본값                    |
| -------------------------------- | ------------------------- | ------------------------- |
| `OPEN_WORK_HUB_BENTO_BIND_HOST`  | 호스트 공개 주소          | `127.0.0.1`               |
| `OPEN_WORK_HUB_BENTO_IMAGE_TAG`  | 로컬 컨테이너 이미지 태그 | `1.0.17`                  |
| `OPEN_WORK_HUB_BENTO_PORT`       | 직접 접근용 호스트 포트   | `18084`                   |
| `OPEN_WORK_HUB_BENTO_SERVER_URL` | iframe이 사용할 공개 주소 | `http://127.0.0.1:18084/` |

운영에서는 별도 HTTPS 도메인을 Bento 컨테이너의 `8080` 포트로 프록시하고,
`OPEN_WORK_HUB_BENTO_SERVER_URL`을 그 절대 주소로 설정한 상태에서 웹 앱을 빌드한다.
허브와 같은 출처의 경로는 사용하지 않는다. 출처를 분리해야 Bento 런타임이 허브의
브라우저 저장소와 인증 토큰에 접근할 수 없다. 운영 URL은 HTTPS여야 하며 Work Hub를
iframe에 삽입할 수 있도록 프록시의 CSP와 프레임 정책도 함께 설정한다.

## 데이터와 권한 경계

- 앱 카탈로그의 `bento` 권한은 허브, 문서 API와 편집 경로를 함께 제어한다.
- `bento_documents` 테이블에는 워크스페이스, 소유자, 공개 범위, 버전, 보관 상태와
  정규화된 `bento/slides` JSON을 저장한다. 최대 문서 크기는 25 MiB다.
- 개인 문서는 소유자만 볼 수 있다. 워크스페이스 문서는 멤버가 열고 편집할 수 있으며,
  소유자와 워크스페이스 관리자가 이름·공개 범위·보관 상태를 관리한다.
- 갱신 API는 문서 버전을 비교해 동시에 저장된 변경을 덮어쓰지 않는다.
- 삭제는 먼저 보관한 뒤 영구 삭제하는 2단계 흐름이다.
- iframe에는 Work Hub 인증 토큰을 전달하지 않는다. 부모와 브리지는 정확한 출처와
  `window` 송신자를 모두 확인한 `postMessage`만 처리한다.
- 릴리스에 포함된 업데이트 확인과 온라인 공동 편집은 Bento가 제공하는 별도 외부
  서비스다. 완전한 오프라인 운용이 필요하면 Bento 화면의 오프라인 모드를 사용하고
  조직 네트워크 정책으로 외부 연결을 차단한다.

## 저장, 가져오기와 내보내기

- iframe 브리지는 Bento 문서 변경을 감지해 부모에 전달하고, 부모가 인증된 Bento API로
  자동 저장한다. 편집기의 저장 동작도 같은 API 저장 흐름으로 연결된다.
- `.bento.html` 가져오기는 HTML을 실행하지 않고 `#bento-doc` JSON만 파싱한다.
- 내보내기는 공식 런타임의 `serialize()` 결과를 `.bento.html`로 다운로드한다.
- 원본 HTML 전체를 데이터베이스에 보관하지 않는다. 공식 런타임을 업데이트해도 저장된
  표준 문서 JSON을 새 런타임에 다시 로드할 수 있다.

API 스키마를 변경하면 Alembic 마이그레이션을 추가하고 OpenAPI 기반 웹 클라이언트를
다시 생성한다.

## 로컬 AI로 프레젠테이션 생성

허브의 `AI로 만들기`는 프롬프트, 슬라이드 수와 공개 범위를 받아 새 문서를 만든다.
편집기 상단의 `AI로 수정`은 iframe 브리지에서 최신 문서를 회수해 먼저 저장한 뒤 수정 지시와
함께 로컬 모델에 전달한다. 검증된 전체 문서를 같은 레코드의 다음 버전으로 저장하고
`window.bento.loadDoc` 브리지를 통해 열린 편집기에 즉시 다시 로드한다.
모델 응답은 데이터베이스에 저장하기 전에 다음 조건을 검증한다.

- 현재 런타임 리비전에 고정된 공식
  [AI 작성 가이드](https://github.com/nyblnet/bento/blob/efc0fab48ed1a9531bb1ae2a652a091832f64254/docs/agents.md)와
  [문서 포맷](https://github.com/nyblnet/bento/blob/efc0fab48ed1a9531bb1ae2a652a091832f64254/docs/format.md)에 맞는
  `bento/slides` v1 JSON
- 1280×720 캔버스 안에 배치된 편집 가능한 `text`, `shape`, `chart`, `table` 요소
- 요청한 슬라이드 수, 고유 ID, 안전한 인라인 HTML, 유효한 슬라이드 링크
- 새로 발급한 `docId`와 서버 시각의 `modified`; 모델이 만든 협업 키·외부 자산·실행 가능한
  콘텐츠는 저장하지 않음

모델의 시스템 컨텍스트에는 공식 작성 가이드의 안전한 부분을 압축해 함께 전달한다. 요소 필드만
나열하는 수준이 아니라 96px 여백과 2·3·4열 좌표, 타이포 계층, `role`, 공유 ID 기반 morph,
state slide와 link, 차트·표의 실제 JSON 형태, 발표자 노트와 최종 자체 점검 규칙을 포함한다.
따라서 생성과 수정 모두 같은 Bento 작성 규칙을 사용하며, 런타임에서 외부 문서를 가져오지 않아
로컬·오프라인 실행을 유지한다.

새 문서 생성은 에이전트 루프가 아닌 고정된 2단계 로컬 LLM 파이프라인이다. 첫 단계인
`bento.plan_presentation`은 thinking을 활성화해 사용자 brief를 장별 목적, 핵심 메시지, 서로 다른
composition, 구체적인 visual anchor, 콘텐츠와 요소 예산을 가진 스토리보드로 만든다. 서버가 계획의
슬라이드 수와 필수 필드를 검증한 다음에만 두 번째 `bento.generate_presentation` 호출이 계획을
편집 가능한 요소로 렌더링한다. 렌더링 단계는 숨은 추론이 장문 JSON 출력 예산을 소진하지 않도록
thinking을 끄며, 계획에 지정된 다이어그램·프로세스·코드 흐름·차트·표를 일반 문단이나 반복 카드로
축소하지 않도록 요구한다. 생성 시간과 가독성을 위해 한 슬라이드는 최대 24개의 목적 있는 요소를
목표로 하며, 큰 재귀 트리나 격자는 핵심 상태만 그룹화해 표현한다. 계획 단계가 실패하면 렌더링과
문서 저장은 수행하지 않는다.

모델 출력은 일반 텍스트 JSON에만 의존하지 않는다. Docker Model Runner에
`submit_bento_document` 함수 호출과 단일 `document_json` 인자를 강제 요청한다. DMR의 OpenAI
호환 API는 JSON 모드는 제공하지만 llama.cpp의 JSON Schema 문법 제약을 그대로 노출하지 않고,
이 Qwen 버전은 복잡한 객체 인자 스키마를 사용할 때 도구 호출 파서와 충돌한다. 따라서 문서 자체는
직렬화된 문자열 인자로 전달하며, DMR/Qwen이 장문 생성에서 강제 도구 선택을 무시하고 일반 JSON을
반환하는 경우를 위해 `json_object` 모드도 함께 요청한다. 일반 JSON 응답은 동일한 검증 경로만
폴백으로 허용한다. 서버는 결과를 다시 파싱하여 요소 종류,
좌표, ID, 링크, HTML 안전성 및 슬라이드 수를 전체 검증한다. 검증에 실패하면 같은 로컬 workload가
실패 사유와 응답을 받아 한 번 자동 교정하며, 교정 결과도 전체 검증을 다시 통과해야 저장한다.
원본 응답과 프롬프트는 운영 로그나 상호작용 원장에 저장하지 않는다.

응답 정규화 단계에서는 역할이 빠진 텍스트에 `title`, `subtitle`, `body`, `kicker` 중 적절한
`role`을 보완하고, 슬라이드마다 하나뿐인 제목에는 공통 `morphId`를 부여한다. 이전 슬라이드와
공유되는 morph 키가 하나도 없는데 모델이 `transition: "morph"`만 지정한 경우에는 `fade`로
낮춰 실제로 작동하지 않는 전환 설정이 저장되지 않게 한다. Qwen이 자주 생략하는
`rotation`·`opacity`·shape `radius`는 Bento 기본값으로 보완하고, 선 요소의 0폭·0높이 표현과
`text` 필드, 표 cell `text`, `sub`·`sup`·목록 HTML은 실행 가능한 콘텐츠를 추가하지 않는 범위에서
공식 Bento 필드와 안전한 `span`·`br` HTML로 정규화한다.

계획·생성·수정 호출은 각각 `bento.plan_presentation`, `bento.generate_presentation`,
`bento.edit_presentation` workload로 중앙 AI Gateway에 등록되어 있다. 세 workload는 `local`
route만 허용한다. Bento 앱은
provider나 모델명을 선택하지 않으며, 관리자 모델 설정의 로컬 provider와 기본 모델 또는
workload override를 따른다. 모델 호출이나 응답 검증이 실패하면 새 문서나 새 버전을 저장하지
않는다. 수정 API는 요청 버전과 저장 버전을 모델 호출 전후로 확인해 동시 편집 결과를 덮어쓰지
않는다.

AI 수정 입력에서는 협업 키, 자산, 레이아웃, 댓글과 알 수 없는 확장 필드를 모델에 보내지 않는다.
이 필드들은 서버가 기존 값 그대로 보존한다. 현재 AI 수정 대상은 1280×720 문서의 편집 가능한
`text`, `shape`, `chart`, `table` 요소이며 이미지·SVG·미디어가 포함된 문서는 안전하게 거부한다.

### Docker Model Runner와 Qwen3.6

Apple Silicon 개발 환경의 기본 예시는 Docker Model Runner의
`ai/qwen3.6:35B-A3B-UD-Q4_K_M`이다. 35B 전체 중 토큰당 3B를 활성화하는 MoE 모델이며,
양자화 모델 파일은 약 23GB이므로 충분한 메모리와 디스크 여유를 확인한다.

```bash
docker desktop enable model-runner --tcp=12434
pnpm dev:qwen:pull
pnpm dev:qwen:start
pnpm dev:qwen:status
pnpm dev:qwen:smoke
```

호스트 API의 OpenAI 호환 base URL은
`http://127.0.0.1:12434/engines/v1`이다. `.env.example`은 이 주소와
`docker-model-runner` profile을 사용한다. 다른 OpenAI 호환 런타임을 사용할 때는
`OPEN_WORK_HUB_LLM_LOCAL_PROVIDER`, `OPEN_WORK_HUB_LLM_LOCAL_BASE_URL`과 timeout만 바꾼다.

모델을 처음 받은 뒤 관리자 화면의 `AI 모델 설정`에서 다음을 한 번 수행한다.

1. Local provider endpoint를 위 base URL로 저장하고 `모델 찾기`를 실행한다.
2. 발견된 Qwen3.6 모델에 `chat` capability를 부여하고 활성화한다.
3. Local provider 기본 모델로 선택하거나 `bento.plan_presentation`,
   `bento.generate_presentation`, `bento.edit_presentation` workload의 `default` 역할에 지정한다.

모델 선택은 DB 제어 평면이 소유하므로 환경 변수나 Bento 코드에 모델 ID를 넣지 않는다.
설정 변경 후 API를 재시작할 필요는 없다. 다만 `.env`의 endpoint/profile을 변경했다면 API를
재시작해야 한다.

## 롤백

이전 `open-work-hub-bento` 이미지가 남아 있으면
`OPEN_WORK_HUB_BENTO_IMAGE_TAG`를 이전 태그로 돌린 뒤 서비스를 재생성한다. 소스
업그레이드 커밋 자체를 되돌릴 때는 Dockerfile의 버전·리비전·체크섬을 반드시 같은
세트로 복원한다.
