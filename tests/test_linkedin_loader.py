from linkedin_loader import get_linkedin_job_public


class _FakeResponse:
    def __init__(self, html: str) -> None:
        self._html = html

    def read(self) -> bytes:
        return self._html.encode("utf-8")


def test_get_linkedin_job_public_parses_expected_fields(monkeypatch) -> None:
    html = """
    <html>
      <body>
        <h1 class=\"top-card-layout__title\">Staff Data Engineer</h1>
        <a class=\"topcard__org-name-link\">Acme Corp</a>
        <span class=\"topcard__flavor--bullet\">San Francisco, CA</span>
        <div class=\"show-more-less-html__markup\">Build data platform at scale.</div>
      </body>
    </html>
    """

    def fake_urlopen(_request):
        return _FakeResponse(html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = get_linkedin_job_public("https://www.linkedin.com/jobs/view/123/")

    assert result == {
        "title": "Staff Data Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "description": "Build data platform at scale.",
    }


def test_get_linkedin_job_public_handles_missing_fields(monkeypatch) -> None:
    def fake_urlopen(_request):
        return _FakeResponse("<html><body></body></html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = get_linkedin_job_public("https://www.linkedin.com/jobs/view/123/")

    assert result == {
        "title": "",
        "company": "",
        "location": "",
        "description": "",
    }
