# Diagrams App Operations

Open Work Hub 다이어그램 앱은 draw.io UI를 별도 컨테이너로 실행하고, API가 다이어그램
XML과 PNG 미리보기를 저장한다.

## Environment Contract

- 로컬 개발에서는 `OPEN_WORK_HUB_DRAWIO_BIND_HOST=0.0.0.0`과 비어 있는
  `OPEN_WORK_HUB_DRAWIO_SERVER_URL`을 사용할 수 있다.
- 공개 환경에서는 draw.io를 별도 origin으로 제공하고 그 HTTPS URL을
  `OPEN_WORK_HUB_DRAWIO_SERVER_URL`에 설정한다.
- `OPEN_WORK_HUB_DRAWIO_IMAGE_TAG`는 draw.io 이미지 버전을 고정한다.
- `OPEN_WORK_HUB_DRAWIO_PORT`는 호스트 포트다.

실제 `.env`는 배포 환경의 비밀 저장소에서 관리하며 저장소에 커밋하지 않는다.

## Deploy Checklist

1. draw.io origin의 DNS와 TLS를 구성한다.
2. 배포 환경의 draw.io 변수와 이미지 태그를 확인한다.
3. `scripts/infra-stack.sh <environment> up`으로 컨테이너를 기동한다.
4. 컨테이너 health check와 HTTP 응답을 확인한다.
5. Open Work Hub 웹에서 새 다이어그램 생성과 저장을 확인한다.

## Nginx

리버스 프록시는 draw.io를 Open Work Hub와 다른 origin으로 제공해야 한다. 인증 토큰이
저장되는 메인 origin 아래에 draw.io를 직접 프록시하지 않는다.

## Rollback

앱 코드를 이전 버전으로 되돌려도 draw.io 컨테이너는 남겨 둬도 된다. 다만 신규 다이어그램 앱을 다시 활성화하려면 아래가 모두 살아 있어야 한다.

- draw.io 컨테이너 health check 정상
- draw.io URL의 TLS 정상
- API 스키마에 다이어그램 테이블 포함
- MinIO 접근 정상
