# 31. MinIO — 자체 호스팅 객체 저장소(S3 호환)

> **한 줄 요약.** 파일(업로드 이미지, 첨부, AI 결과물 등)은 DB에 넣지 말고 **객체 저장소** 에 넣는다. **MinIO** 는 Amazon S3와 동일한 API를 쓰는 오픈소스 구현이며, 우리는 이걸 사내에 띄워 쓴다.

> **🔑 한 마디로.** 파일 저장 전용 객체 저장소를 사내에 직접 운영하는 방식입니다. S3 API와 호환되어 향후 클라우드 전환 시 코드 변경을 최소화할 수 있습니다.

### MinIO 동작 핵심 정리

- 파일은 버킷+키 구조로 저장하며, 접근은 access key/secret key 기반 인증으로 제어합니다.
- Presigned URL은 만료 시간이 있는 임시 접근 토큰으로, 서버를 경유하지 않고 직접 업로드/다운로드를 가능하게 합니다.
- DB에는 메타데이터만 저장하고 실제 파일 바이트는 MinIO에 저장해야 DB 부하와 백업 비용을 줄일 수 있습니다.

### ⚠️ 객체 저장소에서 헷갈리기 쉬운 것들

- **"MinIO는 S3의 축소판이다"** — 핵심 API 호환성은 완전하며, Erasure Coding(오류 정정 부호 기반 분산 저장)·복제·라이프사이클 규칙까지 지원합니다. 기능적으로 기업용에 충분합니다.
- **"파일은 로컬 서버 디스크에 저장해도 충분하다"** — 서버가 여러 대가 되는 순간 "A 서버에는 있는데 B 서버에는 없는 파일"이 생깁니다. NFS로 공유하면 성능·장애 전파가 문제입니다. 객체 저장소가 정답입니다.
- **"업로드는 무조건 API 서버를 경유해야 한다"** — Presigned URL을 쓰면 클라이언트가 MinIO로 **직접** 업로드/다운로드합니다. API 서버는 서명 URL만 발급합니다.
- **"MinIO 단일 노드로도 안심이다"** — 디스크 고장 한 번에 모든 첨부가 날아갑니다. 실운영은 다중 노드 + 외부 백업이 기본입니다.
- **"S3 API만 같으면 완전히 호환된다"** — 서명 버전 v4, 일부 헤더, 정책 문법 등에서 미세한 차이가 있을 수 있으므로, SDK 선택(`boto3` vs `minio-py`)과 테스트가 필요합니다.

---

## 1. 왜 파일을 DB에 넣으면 안 되는가

- **DB 용량이 폭발** — 10MB 첨부 1000개면 DB만 10GB. 백업·복제가 모두 느려짐.
- **DB가 파일 서빙 부하까지 떠맡음** — 본업(쿼리)이 느려짐.
- **CDN·웹서버 최적화**(캐시, Range 요청)가 어려워짐.

**원칙**: 메타데이터만 DB, 실제 바이트는 **객체 저장소**.

---

## 2. 객체 저장소(Object Storage)란

"파일 덩어리(객체)를 키로 보관"하는 단순한 저장소. 폴더 트리는 가상이고, 본질은 **key → blob** 맵.

- **Amazon S3**(2006)가 사실상 표준이며, 다른 도구들도 S3 API 호환을 제공합니다.
- 특징: 무한 용량, 높은 내구성, HTTP로 직접 접근, 버전·메타데이터, 정책 기반 접근 제어.

### 객체 저장소를 한 번 더 정리

객체 저장소는 key를 기준으로 파일 객체를 조회하는 저장 구조입니다.

---

## 3. MinIO — "S3를 우리 서버에서"

### 3.1 무엇인가

**MinIO**는 Go 언어로 만든 고성능 오픈소스 객체 저장소. Amazon S3 API를 그대로 구현해, S3용 SDK를 그대로 재사용할 수 있습니다.

### 3.2 왜 S3를 직접 쓰지 않고 MinIO를 쓰나

우리 프로젝트가 MinIO를 선택한 배경:

1. **온프레미스 / 사내 운영** — 회사 네트워크 안에 파일을 두고 싶은 경우. 기업용 데이터는 외부 클라우드 저장이 꺼려지는 경우 많음.
2. **비용 예측 가능성** — AWS S3는 트래픽 단위 과금. MinIO는 자체 서버 비용만.
3. **개발/테스트 용이** — Docker Compose 로컬에서 AWS 없이 개발 가능.
4. **AI 작업물 보호** — 고객 사내 문서/AI 산출물을 외부로 보내기 어려움.
5. **API 호환** — 나중에 AWS S3로 옮겨도 코드 수정 거의 없음.

### 3.3 대안

| 옵션 | 비고 |
|---|---|
| **Amazon S3** | 표준. SaaS. 외부 네트워크 허용이 필요. |
| **Cloudflare R2** | S3 호환 + egress(나가는 트래픽) 비용 0. 공개 자산·글로벌 배포에 강점. |
| **Backblaze B2** | S3 호환·저렴한 스토리지 단가. 백업 보관용으로 인기. |
| **Google Cloud Storage / Azure Blob** | S3와 유사. GCP/Azure 쓰는 곳. |
| **SeaweedFS** | 오픈소스 분산 파일/객체 시스템. 작은 파일 많을 때 유리. |
| **MinIO 7.2 SDK** (우리 선택) | 셀프호스팅 S3 호환. 오픈소스. 사내망 내 운영. |
| **Ceph** | 대규모·고급. 운영 난이도 높음. |
| **로컬 파일시스템** | 단일 서버엔 가능. 확장·내구성 한계. |
| **DB BLOB** | 지양(위 1절). |

우리가 MinIO를 고른 요지: **사내망에 두고 싶은 기업 데이터 + 개발/운영 환경 동일성**. 트래픽 비용 중요하면 R2, 백업 단가 중요하면 B2를 보조로 붙이는 구성도 가능.

---

## 4. 이 프로젝트의 MinIO 사용처

- **문서 첨부 파일** — 사용자가 업로드한 PDF·이미지·영상.
- **에디터 이미지** — BlockNote(26장) 에디터 안에 붙여넣은 이미지.
- **임시 업로드** — 저장 전 단계의 스테이징(upload → scan → commit).
- **AI 결과물** — 생성된 이미지, 요약 PDF, 음성 TTS 파일.
- **내보내기/가져오기** — 워크스페이스 내보낸 파일.
- **아바타 이미지** 등 사용자 자산.

DB의 `files` 테이블엔 `{id, filename, mime, size, object_key, uploaded_by, created_at}` 같은 **메타데이터**만. 실제 바이트는 MinIO의 `object_key` 자리에.

### 4.1 🏢 업무 시나리오

**케이스 — 문서 에디터에 이미지 붙여넣기**
1. 사용자가 BlockNote 에디터에 이미지를 Ctrl+V 붙여넣기.
2. 프런트가 API에 "업로드 URL 주세요" 요청 → API가 MinIO용 presigned PUT URL 발급.
3. 브라우저가 **직접** MinIO로 파일 전송(서버를 거치지 않아 API 부하 없음).
4. 업로드 완료 후 API에 "커밋" 호출 → `files` 테이블에 메타데이터 행 생성, `object_key`는 `editor-images/ws-{id}/{uuid}.png`.
5. 에디터는 presigned GET URL을 `<img src>`로 사용.

**케이스 — 관리자의 "1년 지난 임시 업로드 정리"**
- 버킷에 Lifecycle 규칙을 설정: `tmp/` 접두어 객체는 30일 후 자동 삭제.
- 사람이 cron 돌릴 필요 없이 MinIO가 주기 점검.

---

## 5. 버킷(bucket)과 키(key)

- **버킷**: 최상위 컨테이너. `open-work-hub-uploads`, `open-work-hub-avatars` 등.
- **키**: 버킷 내 객체를 식별하는 전체 경로 문자열. 예: `documents/2026/04/abc123.pdf`.

버킷은 평면 구조이며 키 전체를 기준으로 저장됩니다. 조회 시에는 접두어(prefix) 조건으로 그룹화합니다.

---

## 6. Presigned URL — 서버 서명 기반 직접 업로드/다운로드 링크

대용량 파일을 서버를 경유해 올리면 느리고 부하가 큼. 해결책:

1. 클라이언트가 서버에 "업로드 URL 주세요" 요청
2. 서버가 MinIO에 서명된 임시 URL 생성 (예: 10분 유효)
3. 클라이언트가 **직접 MinIO로 업로드/다운로드**

이 방식이 표준. 우리 프로젝트도 대용량 첨부는 presigned URL 패턴을 따를 가능성이 큽니다.

---

## 7. 파이썬에서 MinIO 쓰기

SDK 옵션:
- **boto3** (AWS 공식 S3 SDK) — 거의 완벽 호환. AWS/MinIO 혼용 시 유리.
- **minio-py 7.2** — MinIO 공식, 가벼움. **우리 프로젝트 선택**.

```python
from minio import Minio

client = Minio(
    "minio:9000",
    access_key="...",
    secret_key="...",
    secure=False
)
client.put_object("open-work-hub-uploads", "documents/abc.pdf", file_stream, length)
url = client.presigned_get_object("open-work-hub-uploads", "documents/abc.pdf", expires=600)
```

### 7.1 🛠️ 5분 실습 — MinIO 웹 콘솔 둘러보기

1. 로컬 `docker compose up -d minio` 후 `http://localhost:9001` 접속.
2. 기본 계정(compose의 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`)으로 로그인.
3. 좌측 "Buckets" → 기존 버킷을 눌러 객체 목록 확인.
4. 파일 하나를 업로드해 보고, "Share" 버튼으로 presigned URL을 생성해 브라우저 새 탭에서 열어 봅니다(유효시간이 끝나면 403).
5. 이것이 바로 API 서버가 코드로 수행하는 작업의 **GUI 버전**입니다.

---

## 8. 보안·운영 포인트

### 8.1 접근 제어

- 버킷은 기본 **비공개**.
- Presigned URL로 일시적 접근을 허용.
- IAM 유사 정책으로 API 키별 권한 분리.

### 8.2 암호화

- 저장 시 암호화(SSE).
- 전송 시 HTTPS — 운영 환경에선 Nginx 뒤에서 TLS.

### 8.3 수명주기

- 오래된 임시 파일을 자동 삭제하는 **Lifecycle 규칙**.
- 버전 관리(versioning)를 켜면 덮어써도 이전 버전 보관.

### 8.4 백업·복제

- MinIO는 다중 노드 복제(Erasure Coding)를 지원. 단일 노드 운영은 위험.
- 외부로 S3 복제(replication)를 거는 **이중화** 전략도 가능.

---

## 9. Docker Compose의 MinIO

```yaml
services:
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: ...
    volumes:
      - ./data/minio:/data
    ports:
      - "9000:9000"   # API
      - "9001:9001"   # 웹 콘솔
```

웹 콘솔(`:9001`)에서 버킷 생성/키 조회/정책 설정을 GUI로 할 수 있어 비개발자에게도 친숙합니다.

---

## 10. 핵심 요약

- 파일은 DB가 아닌 **객체 저장소**에.
- **MinIO**: S3 API와 동일한 오픈소스 구현. 사내 운영·개발 친화.
- 메타데이터는 DB, 바이트는 MinIO, 이게 기본 패턴.
- 대용량은 **Presigned URL**로 서버 부하 회피.
- 보안은 기본 비공개 + 서명 URL + 암호화 + 수명주기.
