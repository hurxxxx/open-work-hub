# 종합검진 앱 (management-tasks)

관리팀 워크스페이스에서 사용하는 업무 앱이며 사용자 표시 이름은 "종합검진"이다(내부 앱 id·라우트·
backend domain은 `management-tasks`/`management_tasks`로 유지한다). 현재 기능은 종합검진 대상자
관리이며 `/w/:workspaceSlug/management-tasks`에서 제공한다. ERP와 판정 결과는 회사 공통
자원으로 유지하지만, 앱 활성화와 접근은 선택한 워크스페이스의 entitlement와 membership으로
제한한다.

## 종합검진 대상자 관리

- HR 도메인의 통합 consumer read 경계에서 `basis = erp`를 명시한다. 이 view는 최신
  `succeeded` master의 ERP-connected people(`matched`, `erp_only`, `identity_conflict`)만
  포함하며 `groupware_only`와 격리 conflict row는 제외한다. ERP DB, raw snapshot table이나
  `load_latest_accepted_erp_employee_snapshot()` source reader를 직접 호출하지 않고 별도 직원
  master, 날짜명 table, 플랫폼 사용자·조직도 생성하지 않는다.
- 판정 결과에는 master run ID, ERP source run ID, ERP view schema version·projection hash,
  row별 source snapshot provenance ID와 ERP source 수집 시각을 보존한다. Raw ERP snapshot이
  retention으로 삭제돼도 master에 materialize된 ERP view v2의 9개 field와 이 provenance로
  현재 view가 동작하며 raw row를 다시 읽지 않는다.
- 전년도 수검 XLSX 매칭(승인된 계약, 2026-07): 사번이 있으면 현재 ERP 기준 projection의 사번
  정확일치로 자동 확정한다. 사번이 없는 파일(예: 2026 개인별 단가)은 이름으로 매칭하되, 동일 이름(동명이인)이
  둘 이상이면 부서명(ERP·필요 시 활성 그룹웨어 조직도)의 정확 일치 또는 공백으로 구분된 명시적
  상·하위 조직 관계로 한 명이 특정될 때만 확정하고, 부분 문자열·유사도 점수로 형제 부서를 고르지 않는다. 명확하지 않으면
  "확인 필요"로 남긴다(fail-closed — 엉뚱한 동명이인을 자동 확정하지 않는다). ERP가 A/B 접미로
  구분한 동명이인은 파일도 같은 접미를 쓸 때만 그 접미로 정확 확정한다. 부양가족 행은 판정에서 제외한다.
- 병합 셀로 표현된 부서는 바로 이어지는 부양가족 행에만 상속한다. 빈 본인 행이나 빈 구분 행을 넘어
  이전 부서를 재사용하지 않는다.
- 사번·이름·본인여부·부서 등 identity/relation 열에 수식이 있으면 계산 캐시가 없거나 오래되어 값을
  신뢰할 수 없으므로 업로드를 거부한다(No·비용 합계 등 판정에 쓰지 않는 계산 전용 열의 수식은 허용).
- 현재 ERP 기준 projection(현직자)에 없는 행(퇴사·미반영·오타)은 판정 대상에서 제외하며 export를
  막지 않는다.
  동명이인 미해소("확인 필요") 행이 있을 때만 preview로 두고 최종 명단 export를 차단한다.
- 화면·export 워크플로(승인된 제품 결정): 대상 연도는 항상 다음 해로 고정한다(선택 UI 없음 — 완료된
  올해 명단으로 내년 대상자를 산출). 대상자 목록·전직원 현황 다운로드 버튼은 두지 않고 최종 명단(xlsx)
  산출만 제공한다. 판정 표는 25/50/100행 페이지네이션으로 렌더링 상한을 둔다.
- 업로드 응답 상세는 "확인 필요"와 현직 미일치 행을 우선해 최대 200행만 반환하고, 생략이 있으면
  화면에 명시한다. 집계 수치는 상세 표시 상한과 무관하게 전체 행을 기준으로 유지한다.
- 개인정보 보호: 대상자 화면은 기본적으로 명단을 가리고 사용자가 "표시"를 눌러야 노출하며, 5분 무조작
  시 자동으로 다시 가린다.
- 업로드와 판정 run은 매 실행마다 새 불변 이력으로 저장한다. 설정은 나이 계산 방식, 고령 기준,
  성인 기준, 근속 기준 네 필드만 적용하며 변경 이력을 남긴다.
- 판정 조회와 export 전에 현재 ERP 기준 master projection, 판정 설정, 최신 전년도 업로드의
  조합을 다시 확인한다. 판정 이후 입력이 바뀌면 기존 run은 이력으로만 보존하고 새 판정을 생성하기 전에는
  화면 조회와 모든 export를 fail-closed로 차단한다. 전사 설정 갱신은 singleton row를 잠근 뒤
  적용해 동시에 수정된 서로 다른 필드가 유실되지 않게 한다.
- ERP 기준 view는 별도 age threshold 없이 latest `succeeded` `hr-master-v5`를 last-known-good
  head로 사용한다. 더 최신 master 시도의 `building`·`failed`는 관리자 배치 상태에서 노출되지만
  그 사실만으로 종합검진 source를 stale 또는 unavailable로 만들지 않는다. 호환 master 부재,
  ERP view schema·projection hash·필수 field·row count 검증 실패에는 raw ERP snapshot으로
  fallback하지 않고 fail-closed한다. 판정 후 master projection hash, 설정 또는 최신 전년도
  업로드가 바뀌어 input hash가 달라지면 판정 row는 보존되더라도 목록 조회와 모든 export를
  `stale_inputs`로 차단하며 별도 과거 이력 조회를 제공하지 않는다.
- 통합 인사의 자동·유효 `workforce_category`, 사람별 관리자 분류 지정과 그룹웨어-ERP 직접
  매핑은 integrated 정합 정보이며 ERP 기준 모집단을 바꾸지 않는다. 매핑·분류 지정·초기화
  전후 ERP 인원, 위 9개 field와 projection hash가 같아야 한다.
- 이 앱의 단일 ERP 기준 projection, 판정 응답과 export는 각각 최대 5,000명(행)으로 제한한다. ERP
  metadata가 상한을 넘으면 원본 행을 materialize하지 않으며, XLSX 결과가 8 MiB를 넘으면
  다운로드를 거부한다. 이 규모를 넘기는 운영 요구는 서버 pagination/streaming 계약을 먼저
  확장한 뒤 활성화한다.
- 판정 조회, 업로드, 판정 재계산, 설정 변경과 세 종류 export는 원문 개인정보 없이 집계값,
  run ID와 접근에 사용한 workspace ID/key를 audit log에 기록한다.

## 활성화 계약

앱 catalog ID는 `management-tasks`, backend domain은 `management_tasks`, app availability는
`workspace`, resource scope는 `company`다. 앱은 기본 비활성이며 플랫폼 관리자가 승인한
관리팀 워크스페이스에서만 visibility override를 활성화한다. 서버는 요청의 워크스페이스
membership과 앱 entitlement를 모두 검사한다. 관리팀 워크스페이스의 직접 membership은 검진
업무 담당자 지정으로 간주하므로 구성원을 제한적으로 관리해야 한다. 다른 워크스페이스에 앱을
활성화하면 회사 공통 임직원 정보에 접근할 수 있어 visibility 변경은 플랫폼 관리자만 수행할 수
있으며, 활성화 대상은 승인된 관리팀 워크스페이스로 한정한다.

## 운영 활성화 전 결정사항

전년도 수검 원본 행과 판정 결과에는 민감한 임직원 정보가 복제된다. HR raw snapshot과 master의
365일 보존 계약을 이 앱 데이터에 그대로 적용할지, 검진 업무의 별도 법적·업무 보존기간을
적용할지는 아직 결정되지 않았다. 보존기간, 폐기 책임자와 복구 예외가 승인되고 자동 폐기 절차가
구현되기 전에는 운영에서 이 앱을 활성화하지 않는다. 앱이 기본 숨김인 것도 이 조건을 반영한다.

ERP 수집과 통합 master의 consumer projection·검증·보존 계약은
[HR 동기화 계약](../../domains/hr/README.md)을 따른다.
