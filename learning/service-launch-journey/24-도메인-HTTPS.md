# 24. 도메인·HTTPS·SSL 설정

> **한 줄 요약.** 서버를 띄운 다음의 마지막 마일은 **사람이 외울 수 있는 주소(도메인)** 와 **암호화된 통신(HTTPS)** 이다. 둘 다 1시간이면 끝나는 작업이지만 빠뜨리면 출시가 미뤄진다.

---

## 들어가며

레슨 23 에서 배포된 서비스는 보통 `https://my-app.vercel.app` 같은 임시 주소를 가집니다. 작동은 하지만 사용자에게 자랑할 만한 주소는 아닙니다. 진짜 출시는 자기 도메인(`couple-budget.com` 같은) 에 연결된 시점부터입니다.

처음 만드는 분이 도메인·HTTPS 단계에서 자주 막히는 자리:

- 도메인을 어디서 사야 할지 모름.
- DNS·A 레코드·CNAME 같은 단어가 헷갈림.
- HTTPS 가 왜 필요한지, SSL 인증서가 무엇인지 흐릿함.
- 모바일 앱의 딥링크·유니버설 링크는 또 다른 차원.

이 레슨은 이 마지막 마일을 매끄럽게 통과하는 절차를 안내합니다.

이 레슨을 다 읽으면:

- 도메인의 작동 원리(DNS·레코드 종류) 를 안다.
- 도메인 구매 → 서버 연결까지 직접 할 수 있다.
- HTTPS 와 SSL 인증서가 어떻게 자동 발급되는지 안다.
- www 와 non-www, 서브도메인 분리를 결정할 수 있다.
- 자주 빠지는 함정(전파 시간·강제 HTTPS·CSP) 을 안다.

---

## 1. 핵심 개념 — 도메인의 작동 원리

### 1.1 IP 주소와 도메인

서버는 **IP 주소** (`93.184.216.34` 같은) 로 식별됩니다. 사람은 외우기 어려우니 **도메인** (`example.com`) 을 사용합니다.

```
사람: "couple-budget.com 으로 가줘"
브라우저 → DNS 에 물음 → "그 도메인의 IP 가 뭔가요?"
DNS → "76.76.21.21 입니다"
브라우저 → 76.76.21.21 에 HTTP 요청
```

이 변환을 담당하는 시스템이 **DNS (Domain Name System)** 입니다.

### 1.2 DNS 레코드 종류

| 레코드 | 무엇 |
|---|---|
| **A** | 도메인 → IPv4 주소 |
| **AAAA** | 도메인 → IPv6 주소 |
| **CNAME** | 도메인 → 다른 도메인 (별칭) |
| **MX** | 메일 서버 지정 |
| **TXT** | 임의의 텍스트 (도메인 소유 검증·SPF 등) |
| **NS** | 이 도메인의 DNS 서버 |
| **CAA** | 어느 인증기관이 SSL 발급 가능한지 |

처음 출시에는 보통 A·AAAA·CNAME·TXT 면 충분.

### 1.3 도메인의 계층

```
www.couple-budget.com
 │   │              │
 │   │              └─ TLD (Top-Level Domain): .com, .kr, .io
 │   └─ 2차 도메인 (구매하는 부분): couple-budget
 └─ 서브도메인: www, api, app, admin
```

서브도메인은 무료로 무한 만들 수 있음. `api.couple-budget.com`·`admin.couple-budget.com` 같은 분리에 활용.

---

## 2. 도메인 구매

### 2.1 어디서 사나

| 등록업체 (Registrar) | 특징 |
|---|---|
| **Cloudflare Registrar** | 마진 없는 가격, 좋은 DNS 무료 |
| **Namecheap** | 가성비, 첫해 할인 |
| **Porkbun** | 저렴 |
| **Google Domains** (Squarespace 인수) | UX 좋음 |
| **GoDaddy** | 큰 곳, 비싸고 업셀 많음 |
| **카페24·후이즈** | 한국 |

처음에는 **Cloudflare Registrar** 또는 **Namecheap** 권장. 가격이 정직하고 부가 옵션 강매 없음.

### 2.2 도메인 이름 선택 팁

- **짧을수록 좋음** — 외우기·타이핑 쉬움.
- **하이픈·숫자 피하기** — 입으로 전달하기 어려움.
- **목적이 분명** — 서비스 이름과 일치.
- **TLD 신중히** — `.com` 이 가장 무난, `.io`·`.app`·`.kr` 도 OK.
- **상표 검색** — 다른 사람의 상표와 충돌 없는지.

### 2.3 가격

- `.com` — 보통 연 $10~$15.
- `.io`·`.app` — $30~$60.
- `.kr` — 연 22,000원~33,000원.

프리미엄 도메인 (사람이 이미 보유) 은 수백~수만 달러일 수 있음.

### 2.4 등록 후 즉시 할 일

- **WHOIS Privacy** 활성화 — 자기 개인정보가 공개되지 않게. 보통 무료.
- **자동 갱신** 활성화 — 잊어버리면 도메인 만료 → 다른 사람 손에.
- **2FA** 등록업체 계정에 — 도메인 탈취 위험.

---

## 3. DNS 설정 — 서버에 연결

### 3.1 DNS 호스팅 — 등록업체와 다를 수 있음

도메인 구매한 곳과 DNS 관리하는 곳이 같을 수도 다를 수도. 보통:

- 등록업체 = DNS — Cloudflare·Namecheap.
- 등록업체 ≠ DNS — 도메인은 GoDaddy 에서, DNS 는 Cloudflare 로.

**Cloudflare 의 무료 DNS** 가 가장 권장. 빠르고 다양한 보안 기능.

### 3.2 PaaS 가 알려주는 대로

Vercel·Render·Fly 같은 PaaS 는 도메인 추가 시 어떤 레코드를 어디에 추가해야 하는지 알려줍니다.

**Vercel 예시:**
```
앱: couple-budget.com 추가
Vercel 가 알려줌:
  - A record: 76.76.21.21
  - 또는 CNAME: cname.vercel-dns.com

DNS 호스팅 (Cloudflare) 에 가서 추가:
  Type: A
  Name: @ (루트 도메인)
  Value: 76.76.21.21
  Proxy: OFF (Vercel 이 자동 발급할 수 있게)
```

5분~몇 시간 후 도메인이 동작.

### 3.3 www 와 non-www

`couple-budget.com` 과 `www.couple-budget.com` 둘 다 동작하게 하는 것이 표준.

**옵션 A: 둘 다 같은 곳으로**
```
@        A      76.76.21.21
www      CNAME  cname.vercel-dns.com
```

**옵션 B: 한쪽으로 리다이렉트**
- 카논컬: `couple-budget.com` 이 메인, `www` 는 거기로 리다이렉트.
- 또는 반대.

대부분의 PaaS 가 자동으로 처리. 메인을 한 가지로 정하면 SEO·일관성에 유리.

### 3.4 서브도메인 분리

흔한 분리 패턴:

| 서브도메인 | 용도 |
|---|---|
| `couple-budget.com` | 메인 웹앱·랜딩 |
| `app.couple-budget.com` | 로그인된 앱 (SaaS 흔함) |
| `api.couple-budget.com` | 백엔드 API |
| `admin.couple-budget.com` | 어드민 |
| `staging.couple-budget.com` | Staging 환경 |
| `docs.couple-budget.com` | 문서 |

각 서브도메인은 독립된 CNAME·A 레코드.

### 3.5 DNS 전파 시간

DNS 변경은 즉시 반영되지 않음. **전파 시간 (Propagation)** 이 있음.

- 보통 몇 분 ~ 몇 시간.
- TTL (Time To Live) 설정에 따라 최대 48시간.
- 새 도메인은 보통 빠름.

`dig couple-budget.com` 또는 `nslookup` 명령으로 진행 상황 확인.

---

## 4. HTTPS 와 SSL 인증서

### 4.1 HTTP vs HTTPS

| 프로토콜 | 통신 |
|---|---|
| HTTP | 평문 — 누구나 가로채면 다 보임 |
| HTTPS | 암호화 — 안전 |

**오늘날 HTTPS 는 사실상 필수.**
- 비밀번호·개인정보·결제 정보 — 평문이면 큰 사고.
- 검색 엔진 (Google) 이 HTTPS 우대.
- 브라우저가 HTTP 사이트에 "안전하지 않음" 경고.
- 일부 API (위치·카메라 등) 는 HTTPS 만 동작.
- PWA 는 HTTPS 필수.

### 4.2 SSL/TLS 인증서

HTTPS 를 작동시키는 디지털 인증서. 신뢰된 **인증기관(CA)** 이 발급.

- 도메인 소유자가 진짜인지 검증.
- 통신 암호화 키 설정.

과거에는 인증서가 비쌌지만 (연 $50~$300), 2015 년 이후 무료 발급이 표준이 됐습니다.

### 4.3 Let's Encrypt — 무료 자동 인증서

비영리 단체. 무료 + 자동 갱신.

- 90일 만료, 자동 갱신.
- 거의 모든 PaaS 가 백그라운드에서 사용.

**사용자가 신경 쓸 일 없음.** Vercel·Cloudflare·Render 모두 도메인 연결만 하면 자동.

### 4.4 자동 발급 흐름

```
1. 도메인을 PaaS 에 추가
2. PaaS 가 Let's Encrypt 에 인증서 요청
3. Let's Encrypt 가 도메인 소유 검증 (HTTP-01 또는 DNS-01)
4. 검증 통과 → 인증서 발급
5. PaaS 가 인증서를 서버에 설치
6. 90일 전에 자동 갱신
```

이 모든 과정이 자동. 처음에는 "왜 안 되지" 싶다가 5~10분 기다리면 인증서가 활성화됩니다.

### 4.5 인증서 종류

| 종류 | 무엇 |
|---|---|
| **DV (Domain Validation)** | 도메인 소유만 검증. Let's Encrypt 는 DV. 일반적. |
| **OV (Organization Validation)** | 조직 정보까지 검증. 비쌈. |
| **EV (Extended Validation)** | 가장 엄격. 브라우저에 회사 이름 표시 (이젠 거의 안 함). |

처음 출시에 DV 면 충분. 금융·대기업이 OV/EV 를 검토.

---

## 5. HTTPS 모범 사례

### 5.1 HTTP → HTTPS 강제 리다이렉트

사용자가 `http://...` 로 접근해도 자동으로 `https://...` 로.

```
HTTP 301 Moved Permanently
Location: https://couple-budget.com/...
```

대부분의 PaaS 가 자동. 직접 운영 시 nginx·Caddy 설정.

### 5.2 HSTS (HTTP Strict Transport Security)

브라우저에게 "이 도메인은 항상 HTTPS 만" 을 알리는 헤더.

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

- 1년간 HTTP 시도조차 안 함.
- 첫 접속의 다운그레이드 공격 차단.
- preload 등록 시 브라우저에 미리 박힘.

### 5.3 인증서 자동 갱신 모니터링

90일 만료를 잊으면 사이트가 갑자기 "안전하지 않음" 으로. 자동 갱신이 동작하는지 확인.

- PaaS 의 인증서 상태 페이지 정기 확인.
- 만료 30일 전 알림 도구 (Uptime Robot·CertWatch).

### 5.4 Mixed Content 방지

HTTPS 페이지에 HTTP 자원(이미지·스크립트)을 불러오면 일부가 차단되거나 경고. **모든 자원을 HTTPS** 로.

```html
<!-- 나쁨 -->
<img src="http://example.com/image.jpg">

<!-- 좋음 -->
<img src="https://example.com/image.jpg">

<!-- 더 좋음 (프로토콜 자동 매칭) -->
<img src="//example.com/image.jpg">
```

---

## 6. 모바일 앱의 딥링크

웹과 별개로, 모바일 앱은 도메인을 **딥링크** 와 연결합니다.

### 6.1 iOS Universal Links

`https://couple-budget.com/invite/abc123` 클릭 시 앱이 열리도록.

설정:
- `apple-app-site-association` 파일을 도메인 루트에.
- iOS 앱의 `Associated Domains` Capability 등록.

### 6.2 Android App Links

같은 개념. 설정:
- `assetlinks.json` 을 `/.well-known/` 에.
- Android Manifest 에 intent filter.

### 6.3 도메인을 미리 챙기는 이유

웹사이트만 운영하더라도, 앞으로 모바일 앱을 낼 가능성이 있다면 도메인 루트 파일 두 개를 호스팅할 수 있어야 합니다. PaaS 의 정적 파일 호스팅·헤더 설정 능력을 미리 확인.

---

## 7. 자주 빠지는 함정

### 함정 1. "DNS 전파" 안 기다림

레코드 추가 직후 안 된다고 좌절. 5분~몇 시간 기다리세요. `dig` 로 확인.

### 함정 2. www 와 non-www 중 하나만 동작

한쪽으로 접근한 사용자가 "사이트 없음" 보는 사고. 반드시 둘 다 또는 한쪽 → 다른 쪽 리다이렉트.

### 함정 3. CNAME 을 루트 도메인(`@`) 에

CNAME 은 루트 도메인에 못 붙임 (DNS 표준). A 레코드 또는 ALIAS·ANAME (Cloudflare 의 CNAME Flattening) 사용.

### 함정 4. HTTPS 강제 안 함

`http://...` 로 사용자가 들어와도 그대로 동작. 비밀번호 노출. **무조건 HTTPS 리다이렉트**.

### 함정 5. 인증서 만료 방치

Let's Encrypt 자동 갱신이 어떤 이유로 실패. 만료 전 알림 도구 활용.

### 함정 6. 와일드카드 인증서 불필요한 사용

`*.couple-budget.com` 같은 와일드카드는 보안상 위험 (한 인증서가 모든 서브도메인 커버). 명시적 도메인별 인증서가 더 안전.

### 함정 7. 도메인 만료

자동 갱신을 끄고 잊어버려 도메인 빼앗김. 갱신 활성화 + 카드 정보 최신화.

### 함정 8. WHOIS 공개

개인 이름·주소·전화번호가 누구나 검색 가능. WHOIS Privacy 켜기.

### 함정 9. CSP 너무 강함 / 너무 약함

**Content Security Policy** 헤더가 너무 강하면 자기 자원이 차단되고, 너무 약하면 XSS 위험. 점진적으로 강화.

### 함정 10. Cloudflare Proxy 모드 충돌

Cloudflare 의 주황색 구름 (Proxy) 이 켜져 있으면 PaaS 의 인증서 발급이 실패할 수 있음. 처음에는 회색 구름(DNS-only) 으로 두고, PaaS 인증서 발급 후 활성화.

---

## 8. 한 셜 더

### 8.1 CDN — 정적 자원 가속

이미지·JS·CSS 를 사용자 가까이 캐싱.

- **Cloudflare** — 무료 티어 강력.
- **Fastly·Akamai·CloudFront** — 큰 회사용.
- 대부분의 PaaS 가 기본 내장 (Vercel·Netlify).

### 8.2 도메인 평판

스팸·악용으로 도메인이 블랙리스트에 오를 수 있음. 메일 발송 도메인 분리·SPF/DKIM/DMARC 설정.

### 8.3 ACM·Cloudflare Origin Cert

PaaS 가 아니라 직접 운영 시:
- AWS Certificate Manager (ACM) — AWS 자원에 무료 인증서.
- Cloudflare Origin Cert — Cloudflare 와 오리진 사이 15년 인증서.

### 8.4 IDN — 국제화 도메인

`한국.kr` 같은 한글 도메인. Punycode 로 변환되어 처리. 일반적으로 ASCII 도메인 권장 (호환성).

### 8.5 추가 키워드

- **DNSSEC** — DNS 응답 위변조 방지.
- **DoH (DNS over HTTPS)** — DNS 조회 암호화.
- **Subresource Integrity (SRI)** — 외부 스크립트 무결성 검증.
- **Certificate Transparency** — 발급된 인증서 공개 로그.

---

## 마치며

오늘 한 일:

- 도메인의 **작동 원리** (DNS·레코드 종류).
- 도메인 구매·DNS 설정·서버 연결.
- **www 와 non-www**, 서브도메인 분리.
- HTTPS 의 필요성과 **Let's Encrypt 자동 발급**.
- HTTPS 모범 사례 (강제 리다이렉트·HSTS·Mixed Content).
- 함정 10가지.

다음 레슨 [`25. 앱스토어·구글플레이 등록과 심사`](./25-앱스토어-등록.md) 에서는 모바일 앱이 있다면 거쳐야 할 마지막 관문 — 앱 스토어 등록 절차를 봅니다.

다음 페이지에서 만나요.
