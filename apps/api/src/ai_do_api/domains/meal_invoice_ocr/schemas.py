from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 요청 payload 상한(DoS·저장소 비대화 방지). 응답(서버 생성) 모델엔 걸지 않고, 클라이언트가 보내는
# request 전용 모델에만 건다.
# 크롭/페이지 이미지는 저DPI PNG data URL 이라 보통 수백 KB~약 1.5MB(base64) 수준 → 넉넉히 4MB 문자로 제한.
_MAX_IMAGE_CHARS = 4_000_000
# 명세표 한 장의 품목은 보통 ≤ 30줄. 한 번에 저장하는 교정 item 수를 넉넉히 제한.
_MAX_CORRECTION_ITEMS = 300
# 한 번에 내보내는 문서 수 상한(각 문서에 페이지 이미지가 실릴 수 있어 총량을 제한).
_MAX_EXPORT_DOCS = 100
# 교정 item 의 원본/교정 dict 키 수 상한(비정상적으로 많은 필드 방어).
_MAX_CORRECTION_FIELDS = 40
# 요청 전체(모든 item)의 크롭이미지 문자 총량 상한(~40MB). item 당 4MB × 300 개 누적을 막는다.
_MAX_TOTAL_IMAGE_CHARS = 40_000_000
# 내보내기 요청의 문서당 행 수·전체 행 수·텍스트 필드 길이 상한(전체 workbook 을 메모리에 만들기
# 때문에 과대 payload 로 인한 메모리 고갈을 막는다).
_MAX_ROWS_PER_DOC = 500
_MAX_EXPORT_TOTAL_ROWS = 5000
_MAX_TEXT_FIELD_CHARS = 2000
# 교정 저장의 문서 식별 토큰 길이 상한, 그리고 한 요청에 실을 문서 페이지 이미지 개수 상한.
_MAX_DOC_KEY_CHARS = 300
_MAX_DOC_IMAGES = 100


def _validate_data_url_image(value: str) -> str:
    """이미지 필드는 비어 있거나 'data:image/...;base64,' data URL 이어야 한다(형식 제한)."""
    if value and not value.startswith("data:image/"):
        raise ValueError("이미지는 data:image/ 형식의 data URL 이어야 합니다.")
    return value

# 값은 모두 문자열로 다룬다. OCR 원문 충실도(불확실 표기 '?', 쉼표, 손글씨 판독 애매)를 보존하고,
# 사용자가 그리드에서 자유롭게 교정할 수 있게 하기 위함이다. 검증(수량*단가, 행합 vs 합계)은
# 서버가 파싱 가능한 값만 계산해 참고용 플래그로 돌려준다.
# 클래스명은 도메인 접두(MealInvoice*)로 고유화한다 — 전역 OpenAPI 컴포넌트 이름 충돌 방지.


class MealInvoiceRowSource(BaseModel):
    """후처리 전에 OCR 이 실제로 읽은 값(학습 키 보존용).

    사전·기준 카탈로그·과거 교정(vendor alias)은 품명·수량 단위·원산지를 자동 보정한다. 그 결과를
    학습 원본으로 쓰면 '보정된 값 → 사용자 교정' 쌍이 저장되어, 실재 품목이 오독 키로 굳고 서로
    반대 방향 교정이 짝으로 쌓인다(예: 깻잎→감자 와 감자→깻잎 공존). 학습은 언제나 OCR 원문을
    키로 삼아야 하므로 보정 전 값을 함께 돌려준다.
    """

    # 브랜드·규격·단위 정제(_clean_item_name) 전에 OCR 이 읽은 품명 문자열 그대로. 표시용 품명은
    # 정제 결과지만, 학습 키는 문서에 실제로 인쇄된 이 원문이어야 같은 명세표를 다시 읽었을 때
    # 확정 교정이 정제 규칙과 무관하게 그대로 재적용된다.
    품명: str = ""
    수량: str = ""
    원산지: str = ""


class MealInvoiceRow(BaseModel):
    """거래명세표의 품목 한 줄."""

    품명: str = ""
    규격: str = ""
    수량: str = ""
    단가: str = ""
    금액: str = ""
    # 수기 명세표 양식 부가 컬럼. 원산지는 OCR/기본값(국내산), 나머지는 검수 입력.
    원산지: str = ""
    신선도: str = ""
    불량여부: str = ""
    반품여부: str = ""
    비고: str = ""
    # 수량*단가 와 금액 대조 결과(참고용). "OK" | "확인(계산값)" | "" (계산 불가).
    금액검증: str = ""
    # 원본 이미지에서 이 행이 인식된 세로 구간만 잘라낸 크롭(PNG data URL). 없으면 빈 문자열.
    크롭이미지: str = ""
    # 사용자가 검토·수정 후 '확인'한 행 표시(엑셀 내보내기에도 반영).
    확인여부: bool = False
    # 품명 사전 매칭 제안(OCR 품명과 다를 때만 채워짐). UI 에서 클릭하면 품명에 적용한다.
    사전후보: str = ""
    사전점수: float = 0.0
    # 기준 카탈로그(영양사 대장) 매칭 제안. 단위/단가 칩으로 표시, 클릭 시 적용. 값은 참고용.
    단위후보: str = ""
    단가후보: str = ""
    # 이 품목이 과거에 쓴 단위들(빈도 내림차순). OCR 단위와 다른 것을 칩으로 제안한다.
    단위후보목록: list[str] = Field(default_factory=list)
    # 사전·카탈로그·과거 교정으로 자동 보정하기 전에 OCR 이 읽은 값. 교정 학습의 키로 쓴다.
    원문: MealInvoiceRowSource = Field(default_factory=MealInvoiceRowSource)


class MealInvoiceDocument(BaseModel):
    """업로드한 한 파일(한 명세표)의 추출 결과."""

    원본파일: str = ""
    페이지: int = 1
    거래처: str = ""
    거래일: str = ""
    합계금액: str = ""
    # 부가세 제외 공급가액 소계(있으면). 부가세 분리 양식에서 행합과 비교하는 기준.
    공급가액: str = ""
    # 행 금액 합계 vs (공급가액/합계금액) 대조 결과(참고용). "일치" | "불일치(...)" | "".
    합계검증: str = ""
    # 원본 페이지 전체 이미지(저DPI PNG data URL). 화면 검수용. 없으면 빈 문자열.
    페이지이미지: str = ""
    품목: list[MealInvoiceRow] = Field(default_factory=list)


class MealInvoiceExtractResponse(BaseModel):
    documents: list[MealInvoiceDocument] = Field(default_factory=list)
    # 비전 OCR 이 붙지 않았거나(설정 누락) 일부 파일이 실패한 경우의 사람용 경고 메시지.
    warnings: list[str] = Field(default_factory=list)


class MealInvoiceExportRow(BaseModel):
    """엑셀 내보내기 요청의 한 행. 엑셀 생성에 쓰이지 않는 이미지(크롭/페이지)·사전/카탈로그 후보
    필드는 아예 받지 않는다. 인증 사용자가 5,000행 각각에 수 MB data URL 을 실어 수 GB JSON 을
    보내는 DoS 경로를 스키마 수준에서 차단한다(export 는 이미지가 필요 없다). 각 텍스트 필드는
    길이 상한으로 제한되고, extra='forbid' 로 이미지 등 미지정 필드를 '무시'가 아니라 '거절'한다
    (무시하면 거대 문자열이 파서에 실려 메모리만 소모하므로)."""

    model_config = ConfigDict(extra="forbid")

    품명: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    규격: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    수량: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    단가: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    금액: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    원산지: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    신선도: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    불량여부: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    반품여부: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    비고: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    금액검증: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    확인여부: bool = False


class MealInvoiceExportDocument(BaseModel):
    """엑셀 내보내기 요청의 한 문서. 페이지 이미지는 받지 않는다(export 미사용, extra='forbid')."""

    model_config = ConfigDict(extra="forbid")

    원본파일: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    페이지: int = 1
    거래처: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    거래일: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    합계금액: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    공급가액: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    합계검증: str = Field(default="", max_length=_MAX_TEXT_FIELD_CHARS)
    품목: list[MealInvoiceExportRow] = Field(
        default_factory=list, max_length=_MAX_ROWS_PER_DOC
    )


class MealInvoiceExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 그리드에서 사용자가 교정한 뒤의 문서 목록. 그대로 엑셀로 내보낸다(이미지 없는 전용 DTO).
    documents: list[MealInvoiceExportDocument] = Field(
        default_factory=list, max_length=_MAX_EXPORT_DOCS
    )

    @model_validator(mode="after")
    def _check_export_limits(self) -> "MealInvoiceExportRequest":
        """전체 행 수 상한(메모리 고갈 방어). 문서당 행 수·텍스트 길이는 각 필드 상한이 이미 강제한다."""
        total_rows = sum(len(doc.품목) for doc in self.documents)
        if total_rows > _MAX_EXPORT_TOTAL_ROWS:
            raise ValueError("전체 품목 행 수 상한을 초과했습니다.")
        return self


class MealInvoiceCorrectionItem(BaseModel):
    """확인한 행 하나의 원본 OCR값 → 사람 교정값 쌍. 학습(few-shot/파인튜닝)의 원천 데이터."""

    거래처: str = ""
    거래일: str = ""
    # {"품명":..,"규격":..,"수량":..,"단가":..,"금액":..} 형태. 한국어 값은 dict value 라 이름 충돌 없음.
    원본: dict[str, str] = Field(default_factory=dict)
    교정: dict[str, str] = Field(default_factory=dict)
    # 이 행의 원본 크롭 이미지(PNG data URL). 관리 화면 표시용. few-shot 텍스트와 분리 저장된다.
    # 보통은 비우고, 페이지 이미지는 요청 상단 '문서이미지' 맵에 문서당 한 번만 싣는다(아래 문서키로 연결).
    크롭이미지: str = Field(default="", max_length=_MAX_IMAGE_CHARS)
    # 이 교정이 속한 문서 식별 토큰. '문서이미지' 맵의 키와 맞춰 해당 문서 페이지 이미지에 연결한다.
    문서키: str = Field(default="", max_length=_MAX_DOC_KEY_CHARS)

    _check_image = field_validator("크롭이미지")(_validate_data_url_image)

    @field_validator("원본", "교정")
    @classmethod
    def _limit_dict_values(cls, value: dict[str, str]) -> dict[str, str]:
        # 저장 후 few-shot 프롬프트로 결합되므로, 필드 수와 값 길이를 제한한다(과대 상태·프롬프트 방어).
        if len(value) > _MAX_CORRECTION_FIELDS:
            raise ValueError("교정 필드 수 상한을 초과했습니다.")
        for item_value in value.values():
            if len(item_value or "") > _MAX_TEXT_FIELD_CHARS:
                raise ValueError("교정 값 길이 상한을 초과했습니다.")
        return value


class MealInvoiceCorrectionSaveRequest(BaseModel):
    items: list[MealInvoiceCorrectionItem] = Field(
        default_factory=list, max_length=_MAX_CORRECTION_ITEMS
    )
    # 문서키 → 페이지 이미지(data URL). 확인 행마다 같은 페이지 이미지를 반복 전송하면 한 장
    # 20~30행에서도 전체 이미지 총량이 상한을 넘어 저장이 실패하므로, 문서당 한 번만 여기 싣는다.
    문서이미지: dict[str, str] = Field(default_factory=dict)

    @field_validator("문서이미지")
    @classmethod
    def _check_doc_images(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > _MAX_DOC_IMAGES:
            raise ValueError("문서 이미지 수 상한을 초과했습니다.")
        for image in value.values():
            if len(image or "") > _MAX_IMAGE_CHARS:
                raise ValueError("문서 이미지 크기 상한을 초과했습니다.")
            _validate_data_url_image(image or "")
        return value

    @model_validator(mode="after")
    def _limit_total_images(self) -> "MealInvoiceCorrectionSaveRequest":
        """요청 전체 이미지 문자 총량 상한(개별 4MB × 다수 누적 방어). item·문서이미지 모두 합산."""
        total = sum(len(item.크롭이미지 or "") for item in self.items)
        total += sum(len(image or "") for image in self.문서이미지.values())
        if total > _MAX_TOTAL_IMAGE_CHARS:
            raise ValueError("요청 전체 이미지 총량 상한을 초과했습니다.")
        return self


class MealInvoiceCorrectionSaveResponse(BaseModel):
    saved: int = 0
    total_stored: int = 0


class MealInvoiceCorrectionRecord(BaseModel):
    id: str = ""
    거래처: str = ""
    거래일: str = ""
    원본: dict[str, str] = Field(default_factory=dict)
    교정: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""
    # 원본 페이지 이미지 보유 여부. 실제 이미지는 목록에 싣지 않고 별도 엔드포인트로 조회한다.
    이미지있음: bool = False


class MealInvoiceCorrectionListResponse(BaseModel):
    items: list[MealInvoiceCorrectionRecord] = Field(default_factory=list)
    total: int = 0


class MealInvoiceCatalogInfoResponse(BaseModel):
    # 적재된 기준 카탈로그의 품목 수(제안에 쓰인다).
    items: int = 0
    # 카탈로그에서 쓰인 단위 목록(빈도 내림차순). 수량 단위 드롭다운 후보로 쓴다.
    units: list[str] = Field(default_factory=list)
