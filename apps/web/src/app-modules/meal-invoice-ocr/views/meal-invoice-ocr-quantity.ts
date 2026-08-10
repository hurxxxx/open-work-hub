// 수량/단가/금액의 파싱·정규화 순수 로직. 화면(뷰)과 분리해 회귀 테스트가 가능하게 둔다.
// 핵심 계약: 수량은 "숫자 단위"(예: "2 10k") 형식이라 단위에 섞인 숫자('10k')가 수량 숫자에
// 딸려 들어가면 안 된다(리뷰 회귀: parseNumber("2 10k") → 210 오류).

// 단위 표기 통일: 'kg'(및 '10kg')는 'k'(및 '10k')로 바꾼다.
export function normUnit(unit: string): string {
  return String(unit ?? '').replace(/kg/gi, 'k');
}

// 단위 드롭다운에 고정으로 노출하는 '정규 단위'와 그 순서. OCR·카탈로그가 어떤 표기로 주든
// canonicalUnit 으로 이 형태 중 하나에 모은다(없으면 정규화만 한 원문 유지).
export const UNIT_OPTIONS = [
  'ea',
  'k',
  '박스',
  'pk',
  'pac',
  '통',
  '10k',
  '판',
  '단',
  '병',
];

// 별칭 → 정규 단위. kg→k(는 normUnit 이 처리), box→박스, 팩·pack→pac 처럼 뜻이 같은 표기를 모은다.
// 키는 소문자·normUnit 적용 후 형태로 둔다(비교 전 동일 정규화를 거친다).
const UNIT_ALIASES: Record<string, string> = {
  '㎏': 'k',
  box: '박스',
  박: '박스',
  상자: '박스', // i18n-exempt-line: 단위 코드 별칭(표시 문구 아님)
  케이스: '박스', // i18n-exempt-line: 단위 코드 별칭(표시 문구 아님)
  case: '박스',
  팩: 'pac',
  pack: 'pac',
  개: 'ea',
  낱: 'ea',
  낱개: 'ea', // i18n-exempt-line: 단위 코드 별칭(표시 문구 아님)
  동: '통', // i18n-exempt-line: 손글씨 통↔동 흔한 오독을 정규 단위로 흡수
};

// 임의 단위 표기를 정규 단위 하나로 정규화한다. 예: 'kg'→'k', 'Box'→'박스', '팩'→'pac'.
// 정규 목록에도 별칭에도 없으면(예: '봉') 정규화만 한 원문을 그대로 돌려준다(값 손실 방지).
export function canonicalUnit(raw: string): string {
  const n = normUnit(
    String(raw ?? '')
      .trim()
      .toLowerCase(),
  );
  if (!n) return '';
  return UNIT_ALIASES[n] ?? n;
}

// 단위를 '허용 목록 10개'로만 강제한다(사용자 계약: 그 외 단위 절대 추가 금지). 별칭(box→박스,
// 동→통, 개→ea 등)은 흡수하고, 목록·별칭에도 없으면(예: 'c'·'봉'·'g') 빈 문자열로 둔다.
// 목록 밖 값은 보존하지 않는다(OCR 오독·비허용 단위가 화면·엑셀에 남지 않게).
export function enforceUnit(raw: string): string {
  const c = canonicalUnit(raw);
  return UNIT_OPTIONS.includes(c) ? c : '';
}

// 수량 저장 포맷: 숫자와 단위 사이에 공백을 둬 "10kg"처럼 숫자로 시작하는 단위도 보존한다.
// (구버전 "418kg"처럼 공백 없는 값은 앞 숫자/뒤 단위로 폴백 분리.)
export function splitQty(raw: string): { num: string; unit: string } {
  const s = String(raw ?? '').trim();
  const sp = s.indexOf(' ');
  if (sp >= 0)
    return {
      num: s.slice(0, sp).trim(),
      unit: normUnit(s.slice(sp + 1).trim()),
    };
  const m = /^([\d.,]*)(.*)$/.exec(s);
  return { num: m ? m[1] : s, unit: normUnit((m ? m[2] : '').trim()) };
}

export function joinQty(num: string, unit: string): string {
  return unit ? `${num} ${unit}` : num;
}

// 수량 숫자부의 불필요한 소수점을 정리한다: 정수인데 '8.0'·'74.00' 처럼 온 값은 '8'·'74' 로.
// 실제 소수(8.5)는 그대로 두고, 숫자로 못 읽는 값(빈값·'?'·범위 등)은 손대지 않는다(값 손실 방지).
export function normalizeQtyNumber(num: string): string {
  const s = String(num ?? '').trim();
  if (!s) return s;
  const cleaned = s.replace(/,/g, '');
  // 순수 숫자만 대상. '3?'·'1~2' 같은 표기는 원문 유지.
  if (!/^-?\d*\.?\d+$/.test(cleaned)) return s;
  const negative = cleaned.startsWith('-');
  const unsigned = negative ? cleaned.slice(1) : cleaned;
  const [rawInteger = '', rawFraction] = unsigned.split('.');
  const integer = (rawInteger || '0').replace(/^0+(?=\d)/, '');
  const fraction = rawFraction?.replace(/0+$/, '');
  const normalized = fraction ? `${integer}.${fraction}` : integer;
  // Number 로 왕복하면 MAX_SAFE_INTEGER를 넘는 정수가 반올림되므로 문자열로만 정규화한다.
  return negative && normalized !== '0' ? `-${normalized}` : normalized;
}

// 문자열에서 숫자만 뽑아 number 로. 비숫자는 제거(쉼표·단위·불확실 표기 '?' 등).
export function parseNumber(value: string): number | null {
  const cleaned = (value ?? '').replace(/[^0-9.-]/g, '');
  if (!cleaned || cleaned === '-' || cleaned === '.') return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

// 수량 전용 숫자 파싱: 단위부를 먼저 떼어내고 '숫자부'만 파싱한다. 그래야 "2 10k"가 2 로
// 해석되고(210 이 아니라), 단위 "10k"의 숫자가 수량에 섞이지 않는다.
export function parseQtyNumber(value: string): number | null {
  return parseNumber(splitQty(value).num);
}

// 금액 = round(수량 × 단가). 둘 중 하나라도 숫자로 못 읽으면 null(자동 계산 불가).
export function computeAmount(qtyRaw: string, priceRaw: string): number | null {
  const qty = parseQtyNumber(qtyRaw);
  const price = parseNumber(priceRaw);
  if (qty === null || price === null) return null;
  return Math.round(qty * price);
}
