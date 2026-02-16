import linkedin_loader_private


class _FakeElement:
    def __init__(self, text: str) -> None:
        self._text = text
        self.clicked = False

    def inner_text(self) -> str:
        return self._text

    def click(self) -> None:
        self.clicked = True


class _FakeLocator:
    def __init__(self, texts):
        self._elements = [_FakeElement(text) for text in texts]

    def count(self) -> int:
        return len(self._elements)

    @property
    def first(self) -> _FakeElement:
        return self._elements[0]

    def inner_text(self) -> str:
        return self._elements[0].inner_text() if self._elements else ""


class _FakePage:
    def __init__(self, selector_texts: dict[str, list[str]]) -> None:
        self._selector_texts = selector_texts
        self.visited_url = None

    def goto(self, url: str) -> None:
        self.visited_url = url

    def wait_for_selector(self, _selector: str, timeout: int) -> None:
        assert timeout == 30000

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self._selector_texts.get(selector, []))


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self.pages = [page]
        self.closed = False

    def new_page(self) -> _FakePage:
        return self.pages[0]

    def close(self) -> None:
        self.closed = True


class _FakePlaywright:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.chromium = self

    def launch_persistent_context(self, **_kwargs) -> _FakeBrowser:
        return _FakeBrowser(self._page)


class _FakePlaywrightContext:
    def __init__(self, page: _FakePage) -> None:
        self._playwright = _FakePlaywright(page)

    def __enter__(self) -> _FakePlaywright:
        return self._playwright

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_get_linkedin_job_detects_applied_status(monkeypatch) -> None:
    page = _FakePage(
        {
            ".job-details-jobs-unified-top-card__job-title h1": ["Principal Engineer"],
            ".jobs-apply-button--applied": ["Application submitted"],
            ".jobs-description": ["Detailed JD"],
            "body": ["irrelevant"],
        }
    )

    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", lambda: _FakePlaywrightContext(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/1/")

    assert result.title == "Principal Engineer"
    assert result.status == "applied"
    assert result.description == "Detailed JD"


def test_get_linkedin_job_detects_closed_status_from_page_fallback(monkeypatch) -> None:
    page = _FakePage(
        {
            ".job-details-jobs-unified-top-card__job-title h1": ["Site Reliability Engineer"],
            ".jobs-description": ["Detailed JD"],
            "body": ["This role is no longer accepting applications."],
        }
    )

    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", lambda: _FakePlaywrightContext(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/2/")

    assert result.title == "Site Reliability Engineer"
    assert result.status == "closed"
