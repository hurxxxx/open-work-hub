"""IMDS 책임광물 사용현황 조사표 도메인.

IMDS 보고서 PDF 의 아이콘 색상(빨강/노랑/초록/파랑)을 인식하여 부품/제품/재료/
화학물질을 IMDS 표준으로 분류하고, 책임광물 22종이 포함된 가지를 추출해 회사 양식
엑셀에 채워 넣는 무상태(stateless) 동기식 도메인.

레거시 CLI(``imds_responsible_minerals.py``)를 AI-DO 플랫폼 계약(Workspace 스코프,
업로드 검증, localized error, 파일 다운로드 응답)으로 재해석해 포팅했다.
"""
