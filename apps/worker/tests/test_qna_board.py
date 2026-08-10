from __future__ import annotations

import json
from types import SimpleNamespace

from open_alm_worker.tasks import qna_board


class _Response:
    def __init__(self, text: str, *, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status: {self.status_code}")


class _FakeClient:
    def __init__(self) -> None:
        self.get_urls: list[str] = []
        self.post_payloads: list[dict[str, str]] = []

    def post(self, _url: str, *, data: dict[str, str], headers: dict[str, str]) -> _Response:
        self.post_payloads.append(data)
        assert headers["Referer"] == "http://gw/mobile/bbs/bbs_list.aspx"
        payload = {
            "draw": 1,
            "recordsTotal": 3,
            "recordsFiltered": 3,
            "data": [
                {
                    "num": "2800",
                    "subject": "<a href='read_bbs.aspx?num=2800'>보안 공지</a>",
                    "user_name": "<a>황성철</a>",
                    "modify_date": "2026-06-05 07:51",
                    "p_class": "보안소통창구",
                    "attach": "",
                },
                {
                    "num": "2000",
                    "subject": "<a href='read_bbs.aspx?num=2000'>일반 공지</a>",
                    "user_name": "<a>관리자</a>",
                    "modify_date": "2026-06-04 08:00",
                    "p_class": "공지사항",
                    "attach": "",
                },
                {
                    "num": "1887",
                    "subject": (
                        "<a href='read_bbs.aspx?bbs_num=0&num=1887&curPage=1'>"
                        "<span>복지제도 기준</span></a>"
                    ),
                    "user_name": "<a>유용욱</a>",
                    "modify_date": "2026-04-13 10:31",
                    "p_class": "주요공지사항(관리팀)",
                    "attach": "<img alt='fallback.pdf,'>",
                },
            ],
        }
        return _Response(json.dumps(payload, ensure_ascii=False))

    def get(self, url: str) -> _Response:
        self.get_urls.append(url)
        return _Response(
            """
            <html>
              <span id="lblSubject">복지제도 기준 상세</span>
              <span id="lblWriter">유용욱 과장 (관리팀)</span>
              <span id="lblDate">2025-03-07 오전 8:52:45</span>
              <span id="lblContents"><p>각종 신청서는 관리팀으로 제출해주시기 바랍니다.</p></span>
              <a href="download.aspx?&DownType=bbs&numBBS=1887&file=%EB%B3%84%EC%B2%A81.pdf">
                별첨1
              </a>
            </html>
            """
        )


def test_fetch_notices_uses_groupware_web_list_and_detail() -> None:
    settings = SimpleNamespace(
        qna_board_web_base_url="http://gw",
        qna_board_max_posts=1,
        qna_board_category="주요공지사항(관리팀)",
    )
    client = _FakeClient()

    notices = qna_board._fetch_notices(settings, client)  # noqa: SLF001

    assert len(notices) == 1
    assert notices[0].num == "1887"
    assert notices[0].title == "복지제도 기준 상세"
    assert notices[0].author == "유용욱 과장 (관리팀)"
    assert notices[0].date == "2025-03-07 오전 8:52:45"
    assert notices[0].body == "각종 신청서는 관리팀으로 제출해주시기 바랍니다."
    assert notices[0].attachments == ["별첨1.pdf"]
    assert client.get_urls == ["http://gw/mobile/bbs/read_bbs.aspx?bbs_num=0&num=1887&curPage=1"]
    assert client.post_payloads[0]["order[0][column]"] == "modify_date"


def test_board_category_match_is_exact() -> None:
    assert qna_board._matches_board_category(  # noqa: SLF001
        "주요공지사항(관리팀)",
        "주요공지사항(관리팀)",
    )
    assert not qna_board._matches_board_category(  # noqa: SLF001
        "공지사항",
        "주요공지사항(관리팀)",
    )
    assert not qna_board._matches_board_category(  # noqa: SLF001
        "주요공지사항",
        "주요공지사항(관리팀)",
    )


def test_parse_groupware_json_tolerates_server_warning_prefix() -> None:
    response = _Response('기간 이동 함수 오류{"draw":1,"recordsTotal":0,"data":[]}')

    payload = qna_board._parse_groupware_json(response)  # noqa: SLF001

    assert payload == {"draw": 1, "recordsTotal": 0, "data": []}


def test_crawl_board_stops_before_provider_io_when_platform_app_is_disabled(monkeypatch) -> None:
    settings = SimpleNamespace(
        qna_board_crawl_enabled=True,
        qna_board_web_base_url="http://gw",
        qna_board_web_username="worker",
        qna_board_web_password="secret",
    )

    class _Session:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = _Session()
    monkeypatch.setattr(qna_board, "get_settings", lambda: settings)
    monkeypatch.setattr(qna_board, "_db_session", lambda: session)
    monkeypatch.setattr(
        qna_board,
        "is_platform_app_enabled",
        lambda db, app_id: False,
        raising=False,
    )

    def fail_web_login(_settings) -> None:
        raise AssertionError("disabled Q&A worker must not call the provider")

    monkeypatch.setattr(qna_board, "_web_login", fail_web_login)

    assert qna_board.crawl_board.run() == "platform-disabled"
    assert session.closed is True


def test_download_attachments_returns_triple_when_detail_fetch_fails() -> None:
    # The read-page fallback fetch can fail; the return contract must stay a
    # 3-tuple (names, text, content_hashes) so the crawl caller's unpack cannot
    # raise ValueError and abort the whole board sync run.
    settings = SimpleNamespace(qna_board_web_base_url="http://gw")

    class _BoomClient:
        def get(self, _url: str):
            raise RuntimeError("network down")

    names, text, hashes = qna_board._download_attachments(  # noqa: SLF001
        _BoomClient(), settings, num="1887", detail_html=""
    )
    assert (names, text, hashes) == ([], "", [])
