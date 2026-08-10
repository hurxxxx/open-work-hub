"""기안/메일 작성 도우미 도메인.

원본(`C:\\server\\routes\\drafteditor.py`, `mailwriter.py`)의 기안서·업무 메일
작성 기능을 Open ALM 내부 LLM(``complete_chat``) 위로 포팅한 무상태 도메인이다.
LLM 태스크 등록은 ``domains/ai/__init__.py``(``register_ai_capabilities``)에서
``draft_assist`` / ``mail_compose`` 로 한다.
"""
