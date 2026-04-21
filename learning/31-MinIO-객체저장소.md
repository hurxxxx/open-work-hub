# 31. MinIO — 자체 호스팅 객체 저장소(S3 호환)

> **한 줄 요약.** 파일(업로드 이미지, 첨부, AI 결과물 등)은 DB에 넣지 말고 **객체 저장소** 에 넣는다. **MinIO** 는 Amazon S3와 동일한 API를 쓰는 오픈소스 구현이며, 우리는 이걸 사내에 띄워 쓴다.

---

## 1. 왜 파일을 DB에 넣으면 안 되는가

- **DB 용량이 폭발** — 10MB 첨부 1000개면 DB만 10GB. 백업·복제가 모두 느려짐.
- **DB가 파일 서빙 부하까지 떠맡음** — 본업(쿼리)이 느려짐.
- **CDN·웹서버 최적화**(캐시, Range 요청)가 어려워짐.

**원칙**: 메타데이터만 DB, 실제 바이트는 **객체 저장소**.

---

## 2. 객체 저장소(Object Storage)란

"파일 덩어리(객체)를 키로 보관"하는 단순한 저장소. 폴더 트리는 가상이고, 본질은 **key → blob** 맵.

- **Amazon S3**(2006)가 사실상 표준. 다른 도구들도 S3 API를 흉내 냄.
- 특징: 무한 용량, 높은 내구성, HTTP로 직접 접근, 버전·메타데이터, 정책 기반 접근 제어.

### 이메일 비유

객체 저장소는 "거대한 파일 사물함"입니다. 이름표(key)를 붙여 넣으면, 언제든 이름만 대고 찾아올 수 있습니다.

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
| **Google Cloud Storage / Azure Blob** | S3와 유사. GCP/Azure 쓰는 곳. |
| **MinIO** (우리 선택) | 셀프호스팅 S3 호환. 오픈소스. |
| **Ceph** | 대규모·고급. 운영 난이도 높음. |
| **로컬 파일시스템** | 단일 서버엔 가능. 확장·내구성 한계. |
| **DB BLOB** | 지양(위 1절). |

---

## 4. 이 프로젝트의 MinIO 사용처

- **문서 첨부 파일** — 사용자가 업로드한 PDF·이미지·영상.
- **AI 결과물** — 생성된 이미지, 요약 PDF, 음성 TTS 파일.
- **내보내기/가져오기** — 워크스페이스 내보낸 파일.
- **아바타 이미지** 등 사용자 자산.
- **일시 보관소** — 대용량 업로드의 임시 스테이징.

DB의 `files` 테이블엔 `{id, filename, mime, size, object_key, uploaded_by, created_at}` 같은 **메타데이터**만. 실제 바이트는 MinIO의 `object_key` 자리에.

---

## 5. 버킷(bucket)과 키(key)

- **버킷**: 최상위 컨테이너. `aidoo-uploads`, `aidoo-avatars` 등.
- **키**: 그 안의 파일 경로. `documents/2026/04/abc123.pdf` 처럼 `/`로 "폴더 흉내".

실제로는 버킷이 평면이고 키가 전체 경로. "접두어(prefix)"로 폴더처럼 조회.

---

## 6. Presigned URL — "서버가 대신 서명한 직접 업로드/다운로드 링크"

대용량 파일을 서버를 경유해 올리면 느리고 부하가 큼. 해결책:

1. 클라이언트가 서버에 "업로드 URL 주세요" 요청
2. 서버가 MinIO에 서명된 임시 URL 생성 (예: 10분 유효)
3. 클라이언트가 **직접 MinIO로 업로드/다운로드**

이 방식이 표준. 우리 프로젝트도 대용량 첨부는 presigned URL 패턴을 따를 가능성이 큽니다.

---

## 7. 파이썬에서 MinIO 쓰기

SDK 옵션:
- **boto3** (AWS 공식 S3 SDK) — 거의 완벽 호환.
- **minio-py** — MinIO 공식, 가벼움.

```python
from minio import Minio

client = Minio(
    "minio:9000",
    access_key="...",
    secret_key="...",
    secure=False
)
client.put_object("aidoo-uploads", "documents/abc.pdf", file_stream, length)
url = client.presigned_get_object("aidoo-uploads", "documents/abc.pdf", expires=600)
```

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

---

## 11. 이해도 체크

1. 파일을 DB에 넣으면 안 되는 이유 두 가지를 들어 보세요.
2. 버킷과 키의 관계를 간단히 설명해 보세요.
3. Presigned URL이 해결하는 문제는 무엇인가요?
4. AWS S3 대신 MinIO를 선택한 이 프로젝트의 가장 큰 이유는?
5. MinIO 단일 노드만으로 운영하면 생길 수 있는 위험 두 가지를 적어 보세요.
