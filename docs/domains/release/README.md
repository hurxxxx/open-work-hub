# Release Domain

Open Work Hub의 배포 환경은 저장소의 Compose 구성과 안전한 환경 변수 계약을 기반으로
각 운영 환경에서 구성한다. 특정 서버, 사용자 계정, systemd unit 또는 내부 네트워크에
종속된 배포 절차는 프로젝트 소스에 포함하지 않는다.

- 개발 인프라: `ops/compose/open-work-hub-dev.infra.yml`
- 운영 인프라: `ops/compose/open-work-hub-prod.infra.yml`
- 공통 실행 명령: `scripts/infra-stack.sh`
