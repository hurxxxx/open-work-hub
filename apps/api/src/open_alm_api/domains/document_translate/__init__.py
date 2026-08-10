"""문서 번역/요약 도메인.

업로드 문서(PDF/DOCX/XLSX/PPTX/TXT)나 붙여넣은 텍스트를 내부 LLM(``complete_chat``)으로
번역/요약/핵심추출하는 무상태(stateless) 동기식 도메인. 원본(``C:\\server\\routes\\document.py``)의
Open ALM/자동차부품 도메인 프롬프트를 포팅했다.
"""
