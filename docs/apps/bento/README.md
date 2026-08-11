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

## 롤백

이전 `open-work-hub-bento` 이미지가 남아 있으면
`OPEN_WORK_HUB_BENTO_IMAGE_TAG`를 이전 태그로 돌린 뒤 서비스를 재생성한다. 소스
업그레이드 커밋 자체를 되돌릴 때는 Dockerfile의 버전·리비전·체크섬을 반드시 같은
세트로 복원한다.
