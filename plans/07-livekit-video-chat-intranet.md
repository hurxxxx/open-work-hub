# LiveKit Video Chat Intranet Plan

> 문서 성격: AI-DO Meeting 앱에 self-hosted LiveKit 기반 화상 채팅을 추가하기 위한 실행 계획.
> 핵심 결정: 제품 내부 통합은 LiveKit Open Source를 1순위로 한다. 사내망/무도메인 환경은 public domain 없이도 운영할 수 있지만, 브라우저 카메라/마이크 보안 요구 때문에 HTTPS/WSS와 신뢰된 인증서 체인은 반드시 준비한다.

## Context

현재 Meeting 앱은 회의 일정, 참석자, 회의 노트, 첨부, 녹음 업로드, 전사/요약 파이프라인을 이미 갖고 있다.

- Backend: `apps/api/src/ai_do_api/domains/meeting/`
  - Meeting CRUD
  - 참석자 권한
  - notes ensure
  - 파일 첨부
  - recording staging/import/playback/retry/delete
- Web: `apps/web/src/app-modules/meeting/`
  - `/w/:workspaceSlug/meeting`
  - `/w/:workspaceSlug/meeting/:meetingId`
  - `MeetingWorkspaceLayout`: 왼쪽 협업 노트 + 오른쪽 Meeting detail 패널
  - `RecordingControls`: 현재는 브라우저 로컬 오디오 녹음 중심
- Infra:
  - `compose.dev.yml`: postgres, redis, opensearch, minio, nginx
  - `ops/dev/nginx.conf.template`: API/WebSocket proxy
  - `.env.example`: API/worker/MinIO/ASR/LLM 설정

2026-05-07 조사 기준:

- LiveKit Open Source는 Apache-2.0 라이선스이며 WebRTC SFU, SDK, token 기반 접속, recording/egress 경로를 제공한다.
- Jitsi Meet도 Apache-2.0이고 빠른 iframe 통합에는 적합하지만, AI-DO의 Meeting/Notes/Recording/Transcript 파이프라인과 깊게 결합하려면 iframe 중심 통합이 제약이 된다.
- OpenVidu Community는 LiveKit 기반의 운영 번들 성격이 강하다. 빠른 single-node 사내 설치에는 후보지만, upstream SDK/토큰/egress 흐름을 직접 통제하려면 LiveKit이 단순하다.
- mediasoup은 ISC 라이선스라 자유롭지만 signaling, auth, room lifecycle, UI, recording을 직접 설계해야 하므로 현재 제품 목표에는 저수준이다.

관련 공식 문서:

- LiveKit server: https://github.com/livekit/livekit
- LiveKit client connect/token: https://docs.livekit.io/intro/basics/connect/
- LiveKit React Components: https://docs.livekit.io/reference/components/react/
- LiveKit self-host deployment: https://docs.livekit.io/home/self-hosting/deployment/
- LiveKit ports/firewall: https://docs.livekit.io/home/self-hosting/ports-firewall/
- LiveKit Egress: https://docs.livekit.io/transport/media/ingress-egress/egress/
- Jitsi Meet: https://github.com/jitsi/jitsi-meet
- Jitsi iframe API: https://jitsi.github.io/handbook/docs/dev-guide/dev-guide-iframe/
- mediasoup: https://github.com/versatica/mediasoup

## Architecture / Principles

### 1. Self-hosted media plane

LiveKit Cloud는 기본 범위에서 제외한다. 사내망 요구는 외부 네트워크에 의존하지 않는 media plane이므로 LiveKit server, optional TURN, optional Egress worker를 내부 VM 또는 서버에 직접 띄운다.

FastAPI는 미디어를 중계하지 않는다. AI-DO API는 다음만 담당한다.

- Meeting 권한 확인
- LiveKit room name 결정
- 참가자 identity/metadata 결정
- LiveKit access token 발급
- optional room lifecycle/webhook 처리
- optional egress 결과를 기존 Recording/MinIO/전사 파이프라인으로 연결

브라우저의 오디오/비디오는 LiveKit server로 직접 흐른다.

### 2. Intranet TLS is mandatory

공인 도메인이 없어도 운영할 수 있지만, 브라우저 카메라/마이크와 WSS 접속 때문에 HTTPS/WSS secure context는 필요하다.

권장 우선순위:

1. 사내 DNS 이름 사용
   - 예: `ai-do.intra`, `livekit.intra`, `turn.intra`
   - public DNS가 아니라 내부 DNS여도 된다.
2. 사내 CA로 인증서 발급
   - 각 PC/브라우저/모바일 장비에 root CA를 신뢰 저장소로 배포한다.
   - 인증서 SAN에는 내부 DNS 이름을 넣는다.
3. DNS를 만들 수 없으면 IP SAN 인증서 사용
   - 예: `https://10.10.0.20`, `wss://10.10.0.21`
   - IP가 바뀌면 인증서를 다시 발급해야 하므로 운영성이 떨어진다.

`http://사내IP:포트`는 개발/검증용으로만 다룬다. `localhost`는 브라우저에서 예외적으로 secure context 취급될 수 있지만, 다른 PC가 접속하는 사내망 운영 환경에는 해당하지 않는다.

### 3. Meeting room identity is deterministic

LiveKit room name은 AI-DO의 workspace/meeting 식별자에서 안정적으로 만든다.

```text
ai-do:<workspace_id>:meeting:<meeting_id>
```

토큰 identity는 AI-DO user id를 기준으로 한다.

```text
identity = <user_id>
name = <display_name or full_name or email>
metadata = {
  workspace_id,
  meeting_id,
  role,
  email
}
```

권한은 현재 Meeting 권한 모델을 따른다. organizer와 attendee만 참가 토큰을 받을 수 있어야 한다.

### 4. Recording remains product-owned

LiveKit Egress를 사용하더라도 canonical recording 상태와 전사/문서화 파이프라인은 AI-DO가 소유한다.

권장 흐름:

```text
User clicks Record in Meeting video panel
  -> API verifies organizer/participant policy
  -> API starts LiveKit Egress
  -> Egress writes to MinIO/S3-compatible bucket
  -> LiveKit webhook or API poll marks egress complete
  -> AI-DO creates/links Recording or MeetingRecording row
  -> existing recording.transcribe pipeline continues
```

단기 v1에서는 "화상 통화 참가"와 "기존 브라우저 오디오 녹음"을 먼저 유지하고, LiveKit Egress는 Stage 5로 분리한다. 이렇게 하면 화상 채팅 출시와 녹화 인프라 안정화를 분리할 수 있다.

### 5. Feature flag first

LiveKit 설정이 없는 환경에서도 Meeting 앱이 깨지면 안 된다.

```text
DOOWON_VIDEO_ENABLED=false
DOOWON_LIVEKIT_URL=
DOOWON_LIVEKIT_API_KEY=
DOOWON_LIVEKIT_API_SECRET=
DOOWON_LIVEKIT_ROOM_PREFIX=ai-do
```

`DOOWON_VIDEO_ENABLED=false`이면 UI는 화상회의 버튼/패널을 숨기고 현재 Meeting/Recording 동작을 유지한다.

## Implementation Stages

### Stage 0 - Final decision and network prerequisites

- LiveKit 직접 통합을 1순위로 확정한다.
- 사내 운영 방식 중 하나를 선택한다.
  - 내부 DNS + 사내 CA
  - IP SAN 인증서 + 고정 IP
- 운영 대상 네트워크에서 다음 포트 정책을 확정한다.
  - HTTPS/WSS: `443/tcp`
  - LiveKit HTTP/WebSocket upstream: internal `7880/tcp`
  - ICE TCP fallback: `7881/tcp`
  - ICE UDP range: 기본 `50000-60000/udp`, 운영 여건에 따라 축소
  - TURN/TLS fallback 필요 여부
- 모바일 브라우저 사용 여부를 확인한다.
  - iOS/Android까지 지원해야 하면 사내 CA 배포 절차가 필수다.

### Stage 1 - Local/dev LiveKit service

파일 범위:

- `compose.dev.yml`
- `compose.dev.host.yml`
- `compose.local.yml`
- `.env.example`
- `scripts/dev-infra.sh`
- optional `ops/livekit/livekit.dev.yaml`

작업:

- LiveKit server container를 dev compose에 추가한다.
- `livekit.dev.yaml`을 추가한다.
- dev 기본값은 local testing 중심으로 둔다.

예시 설정:

```yaml
port: 7880

rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 50100
  use_external_ip: false
  node_ip: 127.0.0.1

keys:
  devkey: devsecret
```

사내망 검증용 설정은 `node_ip`를 서버의 내부 IP로 바꾼다.

```yaml
rtc:
  use_external_ip: false
  node_ip: 10.10.0.21
```

### Stage 2 - API settings and token endpoint

파일 범위:

- `apps/api/src/ai_do_api/core/settings.py`
- `apps/api/src/ai_do_api/domains/meeting/schemas.py`
- `apps/api/src/ai_do_api/domains/meeting/router.py`
- `apps/api/src/ai_do_api/domains/meeting/service.py`
- `apps/api/tests/test_meeting_video.py`
- `apps/api/pyproject.toml`

작업:

- LiveKit server SDK 의존성을 추가한다.
  - Python 후보: `livekit-api`
- Settings에 video/livekit 환경변수를 추가한다.
- `MeetingVideoTokenResponse` schema를 추가한다.
- endpoint를 추가한다.

```text
POST /api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting_id}/video-token
```

응답 예:

```json
{
  "enabled": true,
  "ws_url": "wss://livekit.intra",
  "room_name": "ai-do:workspace-123:meeting:meeting-456",
  "token": "<jwt>",
  "participant_identity": "user-789"
}
```

권한 테스트:

- organizer는 token을 받을 수 있다.
- attendee는 token을 받을 수 있다.
- workspace member지만 meeting participant가 아니면 token을 받을 수 없다.
- `DOOWON_VIDEO_ENABLED=false`이면 clear disabled response 또는 404/409 정책 중 하나로 실패한다.
- token에는 configured TTL이 적용된다.

### Stage 3 - Web SDK integration

파일 범위:

- `package.json`
- `apps/web/src/app-modules/meeting/api/meeting-api.ts`
- `apps/web/src/app-modules/meeting/views/MeetingView/MeetingWorkspaceLayout.tsx`
- 신규 `apps/web/src/app-modules/meeting/views/MeetingView/VideoMeetingPanel.tsx`
- 신규 `apps/web/src/app-modules/meeting/views/MeetingView/useMeetingVideoToken.ts`
- i18n resource files

작업:

- LiveKit React 의존성을 추가한다.
  - `livekit-client`
  - `@livekit/components-react`
  - `@livekit/components-styles`
- `getMeetingVideoToken()` API client를 추가한다.
- `MeetingWorkspaceLayout` 상단 또는 노트 위쪽에 compact video panel을 추가한다.
- 기본 UI는 다음 상태를 처리한다.
  - video disabled
  - token loading
  - permission denied
  - media permission denied
  - connected
  - disconnected/reconnect
- 첫 버전은 full custom UI보다 LiveKit React Components의 `LiveKitRoom` + `VideoConference` 조합을 사용한다.
- 화면 공유, 카메라, 마이크, 참가자 목록, 연결 끊기 기본 controls를 제공한다.

UI 원칙:

- Meeting workspace의 주 작업은 여전히 노트와 회의 상세다.
- 화상 패널은 노트를 밀어내지 않도록 접기/펼치기 가능하게 둔다.
- 모바일에서는 별도 full-height panel 또는 drawer로 전환한다.

### Stage 4 - Intranet TLS deployment profile

파일 범위:

- `README.md` 또는 `docs/ops/livekit-intranet.md`
- `ops/dev/nginx.conf.template` 또는 별도 production reverse proxy config
- optional `ops/livekit/`

작업:

- 내부 DNS + 사내 CA 기준 운영 절차를 문서화한다.
- IP SAN 인증서 fallback 절차를 문서화한다.
- reverse proxy에서 WebSocket upgrade와 long timeout을 보장한다.
- LiveKit server는 TLS termination을 직접 하거나 reverse proxy 뒤에 둔다. 운영 단순성은 별도 `livekit.intra` endpoint를 두는 쪽이 낫다.
- TURN/TLS가 필요한 경우 `turn.intra:443` 경로를 별도 설계한다.

검증 명령 예:

```bash
curl -vk https://livekit.intra
openssl s_client -connect livekit.intra:443 -servername livekit.intra
```

브라우저 검증:

- `https://ai-do.intra`에서 카메라/마이크 permission prompt가 뜬다.
- `wss://livekit.intra` 연결이 mixed content나 certificate error 없이 열린다.

### Stage 5 - Recording/Egress integration

파일 범위:

- `apps/api/src/ai_do_api/domains/meeting/router.py`
- `apps/api/src/ai_do_api/domains/meeting/schemas.py`
- `apps/api/src/ai_do_api/domains/meeting/service.py`
- `apps/api/src/ai_do_api/domains/recording/` 또는 current recording compatibility layer
- `apps/worker/src/ai_do_worker/tasks/recording.py`
- `apps/api/tests/test_meeting_video_egress.py`

작업:

- API에 egress start/stop endpoint를 추가한다.

```text
POST /meeting/meetings/{meeting_id}/video-egress/start
POST /meeting/meetings/{meeting_id}/video-egress/stop
```

- LiveKit Egress가 MinIO/S3-compatible endpoint로 저장하도록 구성한다.
- egress complete webhook 또는 polling path를 만든다.
- 완료된 object를 canonical Recording 또는 MeetingRecording에 연결한다.
- 기존 `recording.transcribe` pipeline으로 이어지게 한다.

주의:

- LiveKit Egress는 별도 프로세스/컨테이너다. GPU는 필수가 아니지만 CPU/IO 사용량이 크므로 API/worker와 같은 작은 VM에 무작정 합치지 않는다.
- v1에서 "참가자별 오디오 분리"가 필요하면 track egress/multi-track 정책을 별도 결정한다.

### Stage 6 - Admin/observability

파일 범위:

- API health/debug endpoint 또는 ops docs
- logging configuration
- optional admin settings UI

작업:

- video feature status를 health/debug에서 확인할 수 있게 한다.
- LiveKit connection failure, token issue, webhook failure를 structured log로 남긴다.
- 최소 지표를 정한다.
  - token issued count
  - room join failure count
  - egress started/completed/failed
  - average participants per room
  - reconnect count

## Verification

### Backend unit/integration

- `DOOWON_VIDEO_ENABLED=false`에서 token endpoint가 비활성 상태를 반환한다.
- organizer/attendee만 token endpoint를 통과한다.
- participant가 아닌 workspace member는 거부된다.
- room name이 workspace/meeting 기준으로 안정적으로 생성된다.
- token TTL과 identity/metadata가 의도대로 들어간다.
- LiveKit SDK 호출부는 unit test에서 fake signer 또는 deterministic token helper로 검증한다.

### Web unit/component

- video disabled state가 Meeting 화면을 깨지 않는다.
- token loading/error/success state가 렌더링된다.
- connect button이 token API를 한 번만 호출한다.
- disconnect가 LiveKit room에서 정상 detach된다.
- 모바일 viewport에서 video panel이 노트/상세 패널과 겹치지 않는다.

### Local manual

- `pnpm dev` 또는 dev infra에서 LiveKit이 뜬다.
- `localhost` 테스트에서 두 브라우저가 같은 meeting room에 입장한다.
- 카메라/마이크 mute/unmute가 동작한다.
- 네트워크 재연결 시 UI가 회복된다.

### Intranet manual

- 사내 PC 두 대가 `https://ai-do.intra`로 접속한다.
- 사내 CA가 배포되지 않은 PC에서는 의도적으로 실패한다.
- CA 배포된 PC에서는 certificate warning 없이 접속한다.
- 서로 다른 VLAN/방화벽 구간에서 UDP 연결 가능 여부를 확인한다.
- UDP 차단 환경에서는 TCP/TURN fallback 동작을 확인한다.

### Recording/Egress manual

- 회의 중 egress start/stop이 동작한다.
- MinIO에 object가 생성된다.
- AI-DO recording row가 생성 또는 연결된다.
- playback이 동작한다.
- 전사 pipeline으로 이어진다.

## Decision Log

| 항목 | 결정 |
|---|---|
| 1차 후보 | LiveKit Open Source |
| 라이선스 기준 | Apache-2.0 중심의 permissive license 선호 |
| Jitsi 위치 | 빠른 iframe/embed 대안. 제품 내부 deep integration에는 후순위 |
| OpenVidu 위치 | LiveKit 기반 운영 번들 후보. upstream 직접 통합보다 통제면에서 후순위 |
| mediasoup 위치 | 저수준 SFU 후보. 현재 제품 범위에는 과함 |
| 사내망 운영 | self-hosted LiveKit |
| 무도메인 처리 | 내부 DNS 권장, 불가 시 IP SAN 인증서 |
| TLS | 카메라/마이크와 WSS 때문에 운영 필수 |
| FastAPI 역할 | 권한 확인 + token 발급 + optional egress/webhook orchestration |
| Media path | 브라우저에서 LiveKit server로 직접 연결 |
| 녹화 v1 | 화상 통화와 분리. 기존 browser audio recording 유지 후 LiveKit Egress를 후속 연결 |
| Feature flag | `DOOWON_VIDEO_ENABLED=false` 기본 |

## Open Questions

- 내부 DNS를 만들 수 있는가, 아니면 고정 IP + IP SAN 인증서로 가야 하는가?
- 사내 CA root 인증서를 모든 대상 PC/모바일에 배포할 수 있는가?
- 회의 참가자는 organizer/attendee로 제한할지, workspace member 초대 입장을 허용할지?
- UDP port range를 넓게 열 수 있는가?
- TURN/TLS fallback이 v1 필수인가?
- 녹화는 room composite MP4로 충분한가, 아니면 참가자별/트랙별 오디오 분리가 필요한가?
- 모바일 Safari/Chrome 지원을 v1 acceptance에 포함할 것인가?

## Rollback Plan

- API token endpoint는 feature flag 뒤에 둔다. 문제가 생기면 `DOOWON_VIDEO_ENABLED=false`로 비활성화한다.
- Web은 video panel을 lazy route/component로 분리한다. SDK import 또는 runtime 문제가 있으면 panel만 숨기고 기존 Meeting workspace를 유지한다.
- Infra에서 LiveKit container는 기존 postgres/redis/minio/nginx와 독립 서비스로 둔다. 장애 시 LiveKit만 중지하고 AI-DO core 앱은 계속 운영한다.
- Egress integration은 Stage 5까지 분리한다. 녹화 문제가 있으면 기존 browser audio recording/import path로 되돌린다.
- 사내 TLS/CA 배포 문제가 있으면 운영 출시를 보류하고 localhost/dev 검증만 유지한다.
