from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from minio.error import S3Error

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import ensure_bucket, get_minio_client
from ai_do_api.domains.meal_invoice_ocr.state import (
    _as_list,
    mutate_state,
    read_state_field,
)

# 객체/버킷이 '아직 없음'을 뜻하는 S3 오류 코드. 이때만 기본값으로 폴백한다.
_MISSING_S3_CODES = {"NoSuchKey", "NoSuchBucket"}

# 교정 저장소(학습 데이터). 교정 '목록'은 워크스페이스 DB 행(MealInvoiceOcrState.corrections_json)에
# 트랜잭션/행잠금으로 원자적으로 저장한다(다중 워커 lost-update 없음). 크롭 '이미지'만 해시 기반
# 불변 blob 이라 오브젝트 저장소(MinIO)에 둔다. "확인"한 원본→교정 쌍이 곧 학습 신호다.
_PREFIX = "meal-invoice-ocr/corrections"
_MAX_STORED = 1000
_MAX_WORKSPACE_IMAGE_BYTES = 256 * 1024 * 1024
_FIELDS = ("품명", "규격", "수량", "단가", "금액")
# few-shot 프롬프트에 넣는 필드. 품명만 넣는다.
#
# 수량·단가·금액 교정은 그 행에서만 참인 값이다. 이걸 "'9500'→'5500'" 같은 예시로 주면 비전 모델은
# 특정 숫자를 다른 숫자로 바꿔 읽으라는 지시로 받아들여, 다음 명세표의 멀쩡한 금액까지 왜곡한다.
# 단위도 마찬가지로 행마다 다르다("'1 k'→'1 박스'"). 이 교정들은 프롬프트가 아니라 거래처+품명이
# 일치할 때 후처리(vendor alias)에서 적용한다.
_FEWSHOT_FIELDS = ("품명",)


class CorrectionImageQuotaExceeded(ValueError):
    """워크스페이스 교정 이미지 저장 총량을 초과했다."""


def _legacy_img_key(workspace_id: str) -> str:
    # 구버전은 워크스페이스당 하나의 JSON map 에 이미지를 모았다. 신규 저장은 쓰지 않고 조회만 지원한다.
    return f"{_PREFIX}-images/{workspace_id}.json"


def _image_object_key(workspace_id: str, ref: str) -> str:
    return f"{_PREFIX}-images/{workspace_id}/{ref}.txt"


def _image_ref(image: str) -> str:
    return hashlib.sha1(image.encode("utf-8")).hexdigest()


def _get_json(key: str, default: Any) -> Any:
    """저장된 JSON 을 읽는다. '아직 없음'(NoSuchKey/NoSuchBucket)일 때만 기본값을 준다.

    연결 실패·타임아웃 같은 일시적 저장소 오류나 JSON 손상은 삼키지 않고 그대로 전파한다.
    (이걸 빈 기본값으로 바꿔 돌려주면, load→수정→put 경로에서 멀쩡한 공유 상태를 빈 값으로
    덮어써 데이터가 유실될 수 있기 때문이다.)
    """
    settings = get_settings()
    try:
        response = get_minio_client().get_object(settings.minio_bucket, key)
    except S3Error as error:
        if error.code in _MISSING_S3_CODES:
            return default
        raise
    try:
        return json.loads(response.read().decode("utf-8"))
    finally:
        response.close()
        response.release_conn()


def _put_json(key: str, data: Any) -> None:
    ensure_bucket()
    settings = get_settings()
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    get_minio_client().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(payload),
        length=len(payload),
        content_type="application/json",
    )


def _get_object_text(key: str) -> str | None:
    settings = get_settings()
    try:
        response = get_minio_client().get_object(settings.minio_bucket, key)
    except S3Error as error:
        if error.code in _MISSING_S3_CODES:
            return None
        raise
    try:
        return response.read().decode("utf-8")
    finally:
        response.close()
        response.release_conn()


def _put_object_text(key: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    ensure_bucket()
    settings = get_settings()
    payload = text.encode("utf-8")
    get_minio_client().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(payload),
        length=len(payload),
        content_type=content_type,
    )


def _remove_object(key: str) -> None:
    settings = get_settings()
    try:
        get_minio_client().remove_object(settings.minio_bucket, key)
    except S3Error as error:
        if error.code not in _MISSING_S3_CODES:
            raise


def _load_legacy_images(workspace_id: str) -> dict[str, str]:
    data = _get_json(_legacy_img_key(workspace_id), {})
    return data if isinstance(data, dict) else {}


def _put_image(workspace_id: str, ref: str, image: str) -> int:
    _put_object_text(_image_object_key(workspace_id, ref), image)
    return len(image.encode("utf-8"))


def _get_image(workspace_id: str, ref: str) -> str | None:
    image = _get_object_text(_image_object_key(workspace_id, ref))
    if image is not None:
        return image
    legacy = _load_legacy_images(workspace_id)
    legacy_image = legacy.get(ref)
    return legacy_image if isinstance(legacy_image, str) else None


def _remove_image(workspace_id: str, ref: str) -> None:
    _remove_object(_image_object_key(workspace_id, ref))


def _record_refs(records: list[dict[str, Any]]) -> set[str]:
    return {
        str(record.get("image_ref"))
        for record in records
        if record.get("image_ref")
    }


def _stored_size(workspace_id: str, ref: str, record: dict[str, Any]) -> int:
    raw_size = record.get("image_size")
    if isinstance(raw_size, int) and raw_size >= 0:
        return raw_size
    if isinstance(raw_size, str) and raw_size.isdigit():
        return int(raw_size)
    image = _get_image(workspace_id, ref)
    size = len(image.encode("utf-8")) if image else 0
    if size:
        record["image_size"] = size
    return size


def _unique_image_sizes(workspace_id: str, records: list[dict[str, Any]]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for record in records:
        ref = str(record.get("image_ref") or "")
        if not ref:
            continue
        sizes[ref] = max(sizes.get(ref, 0), _stored_size(workspace_id, ref, record))
    return sizes


def _remove_image_refs(workspace_id: str, refs: set[str]) -> None:
    for ref in refs:
        try:
            _remove_image(workspace_id, ref)
        except Exception:  # noqa: BLE001
            # 이미지 정리는 best-effort 다. DB 레코드가 이미 제거된 뒤라 실패해도 학습 데이터 무결성은 유지된다.
            pass


def load_corrections(workspace_id: str) -> list[dict[str, Any]]:
    return _as_list(read_state_field(workspace_id, "corrections_json", []))


def load_images(workspace_id: str) -> dict[str, str]:
    images: dict[str, str] = {}
    for record in load_corrections(workspace_id):
        ref = str(record.get("image_ref") or "")
        if not ref or ref in images:
            continue
        image = _get_image(workspace_id, ref)
        if image is not None:
            images[ref] = image
    return images


def append_corrections(
    workspace_id: str,
    records: list[dict[str, Any]],
    doc_images: dict[str, str] | None = None,
) -> int:
    """새 교정 쌍을 축적하고 저장소의 총 개수를 돌려준다(DB 행 잠금으로 원자적).

    페이지 이미지는 행마다 반복 전송하지 않고 문서당 한 번씩 doc_images(문서키→data URL)로 받는다.
    각 이미지는 콘텐츠 해시로 한 번만 저장(중복 제거)하고, 레코드는 자신의 '문서키'로 그 이미지를
    참조한다. 하위호환으로 record 에 직접 실린 '크롭이미지'도 계속 처리한다.
    """
    if not records:
        return len(load_corrections(workspace_id))
    doc_images = doc_images or {}

    def _apply(state: Any) -> tuple[int, set[str]]:
        existing = _as_list(state.corrections_json)
        new_images: dict[str, str] = {}
        stamp = datetime.now(timezone.utc).isoformat()
        # 문서별 페이지 이미지를 콘텐츠 해시로 한 번씩만 저장하고 문서키→ref 맵을 만든다.
        doc_refs: dict[str, tuple[str, int]] = {}
        for doc_key, image in doc_images.items():
            if not image:
                continue
            ref = _image_ref(image)
            new_images[ref] = image
            doc_refs[str(doc_key)] = (ref, len(image.encode("utf-8")))
        for record in records:
            record.setdefault("created_at", stamp)
            record.setdefault("id", uuid.uuid4().hex)
            doc_key = str(record.pop("문서키", "") or "")
            image = record.pop("크롭이미지", "") or ""
            if image:
                # 레코드에 직접 실린 이미지(하위호환)도 해시로 저장하고 참조를 남긴다.
                ref = _image_ref(image)
                new_images[ref] = image
                record["image_ref"] = ref
                record["image_size"] = len(image.encode("utf-8"))
            elif doc_key and doc_key in doc_refs:
                # 같은 문서의 다른 확인 행들도 문서 페이지 이미지를 공유 참조한다.
                ref, size = doc_refs[doc_key]
                record["image_ref"] = ref
                record["image_size"] = size
        combined = (existing + records)[-_MAX_STORED:]
        sizes = _unique_image_sizes(workspace_id, combined)
        if sum(sizes.values()) > _MAX_WORKSPACE_IMAGE_BYTES:
            raise CorrectionImageQuotaExceeded("meal invoice correction image quota exceeded")
        # 이미지(MinIO)를 DB 커밋 전에 먼저 저장 → 텍스트가 참조하는 이미지가 항상 먼저 존재해,
        # 중간 실패 시에도 '참조는 있는데 이미지가 없는' 레코드가 생기지 않는다.
        for ref, image in new_images.items():
            _put_image(workspace_id, ref, image)
        removed_refs = _record_refs(existing) - _record_refs(combined)
        state.corrections_json = combined
        return len(combined), removed_refs

    count, removed_refs = mutate_state(workspace_id, _apply)
    _remove_image_refs(workspace_id, removed_refs)
    return count


def get_correction_image(workspace_id: str, correction_id: str) -> str | None:
    """해당 교정이 참조하는 원본 페이지 이미지(data URL)를 돌려준다. 없으면 None."""
    record = next(
        (r for r in load_corrections(workspace_id) if r.get("id") == correction_id),
        None,
    )
    ref = record.get("image_ref") if record else None
    if not ref:
        return None
    return _get_image(workspace_id, str(ref))


def list_corrections(workspace_id: str) -> list[dict[str, Any]]:
    """저장된 교정 목록(관리용). id 가 없는 레거시 레코드엔 id 를 부여하고 한 번 저장한다."""
    records = load_corrections(workspace_id)
    if all(record.get("id") for record in records):
        return records

    def _apply(state: Any) -> list[dict[str, Any]]:
        recs = _as_list(state.corrections_json)
        for record in recs:
            if not record.get("id"):
                record["id"] = uuid.uuid4().hex
        state.corrections_json = recs
        return recs

    return mutate_state(workspace_id, _apply)


def delete_correction(workspace_id: str, correction_id: str) -> int:
    def _apply(state: Any) -> tuple[int, bool, set[str]]:
        records = _as_list(state.corrections_json)
        remaining = [r for r in records if r.get("id") != correction_id]
        changed = len(remaining) != len(records)
        state.corrections_json = remaining
        removed_refs = _record_refs(records) - _record_refs(remaining)
        return (len(remaining), changed, removed_refs)

    count, changed, removed_refs = mutate_state(workspace_id, _apply)
    if changed:
        # 레코드 제거 커밋이 성공한 뒤에만 참조 없는 이미지를 정리한다(put-after-delete-commit).
        _remove_image_refs(workspace_id, removed_refs)
    return count


def clear_corrections(workspace_id: str) -> None:
    def _apply(state: Any) -> set[str]:
        refs = _record_refs(_as_list(state.corrections_json))
        state.corrections_json = []
        return refs

    refs = mutate_state(workspace_id, _apply)
    # DB 를 비운 커밋이 성공한 뒤 이미지를 제거한다(현재 참조 = ∅ → 전량 삭제).
    _remove_image_refs(workspace_id, refs)


def build_fewshot(
    corrections: list[dict[str, Any]],
    *,
    limit: int = 24,
    known_names: set[str] | None = None,
) -> str:
    """축적된 교정에서 '품명 오독 → 정답' 예시 텍스트를 만들어 OCR 프롬프트에 주입한다.

    known_names: 실재 품목 이름(사전·기준 카탈로그). 여기 있는 이름은 오독 예시로 쓰지 않는다.
    '깻잎'처럼 실재하는 품목을 "잘못 읽은 글자"로 제시하면 모델이 그 이름을 기피하거나 다른 행의
    정답으로 옮겨 쓴다. 같은 이유로 다른 교정에서 '정답'으로 확정된 적 있는 이름도 제외한다.

    ``원본.품명`` 은 정제(브랜드·규격·단위 제거) 전 OCR 원문이다(학습 키 공간). 프롬프트 예시는 정제
    품명끼리의 쌍으로 만든다. 원문을 그대로 왼쪽에 넣으면 '규격·브랜드가 붙은 원문 → 정제된 정답'이
    오독 예시가 되어, 모델에게 브랜드·규격을 지워서 읽으라고 가르친다(원문 그대로 읽기 설계와 충돌).
    같은 이유로 실재 품목·확정 이름 제외 판단도 문자열이 아니라 정제 키로 한다.
    """
    from ai_do_api.domains.meal_invoice_ocr.service import _alias_key, display_item_name

    known = {_alias_key(name) for name in (known_names or set())}
    confirmed = {
        _alias_key((record.get("교정") or {}).get("품명", "")) for record in corrections
    }
    known.discard("")
    confirmed.discard("")
    seen: set[tuple[str, str]] = set()
    pairs: list[str] = []
    # 최근 것 우선.
    for record in reversed(corrections):
        원본 = record.get("원본") or {}
        교정 = record.get("교정") or {}
        for field in _FEWSHOT_FIELDS:
            raw = str(원본.get(field, "") or "").strip()
            fixed = str(교정.get(field, "") or "").strip()
            if not raw or not fixed or raw == fixed:
                continue
            raw_key = _alias_key(raw)
            # 정제만으로 같아지는 쌍은 오독이 아니다(사용자가 품명을 고치지 않은 행).
            if raw_key == _alias_key(fixed):
                continue
            if raw_key in known or raw_key in confirmed:
                continue
            # 예시의 왼쪽도 표시 품명 공간으로 맞춘다(규격·브랜드 제거 지시가 섞이지 않게).
            raw = display_item_name(raw) or raw
            key = (raw, fixed)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(f"'{raw}'→'{fixed}'")
            if len(pairs) >= limit:
                break
        if len(pairs) >= limit:
            break
    if not pairs:
        return ""
    return (
        "\n\n참고: 과거에 사람이 교정한 'OCR 오독 → 정답' 예시다. "
        "같은 글씨/품목이 보이면 정답 쪽 표기를 따르라: " + ", ".join(pairs) + "."
    )


def records_from_items(items: list[Any]) -> list[dict[str, Any]]:
    """스키마 CorrectionItem 목록 → 저장용 dict 목록. 원본과 교정이 실제로 다른 것만."""
    records: list[dict[str, Any]] = []
    for item in items:
        원본 = {k: str(v) for k, v in (item.원본 or {}).items()}
        교정 = {k: str(v) for k, v in (item.교정 or {}).items()}
        if 원본 == 교정:
            continue
        records.append(
            {
                "거래처": item.거래처,
                "거래일": item.거래일,
                "원본": 원본,
                "교정": 교정,
                "문서키": getattr(item, "문서키", "") or "",
                "크롭이미지": getattr(item, "크롭이미지", "") or "",
            }
        )
    return records
