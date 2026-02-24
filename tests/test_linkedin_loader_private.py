import threading
import pytest
import linkedin_loader_private
from linkedin_loader_private import LinkedInSessionExpiredError


# ── Fake Playwright infrastructure ────────────────────────────────────────────

class _FakeLocator:
    """Minimal Playwright Locator double."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    def count(self) -> int:
        return len(self._texts)

    @property
    def first(self) -> "_FakeLocator":
        # Playwright .first returns a Locator for the first match (count=1) or empty.
        return _FakeLocator(self._texts[:1])

    def inner_text(self) -> str:
        return self._texts[0] if self._texts else ""

    def locator(self, _selector: str) -> "_FakeLocator":
        return _FakeLocator([])  # no nested elements by default

    def filter(self, **_kwargs) -> "_FakeLocator":
        return _FakeLocator([])  # no matching buttons by default

    def evaluate(self, _script: str) -> None:
        pass


class _FakePage:
    """Minimal Playwright Page double."""

    def __init__(
        self,
        title: str,
        body_text: str,
        selector_texts: dict[str, list[str]] | None = None,
        url: str = "https://www.linkedin.com/jobs/view/123/",
    ) -> None:
        self._title = title
        self._body_text = body_text
        self._selector_texts = selector_texts or {}
        self.url = url

    def goto(self, url: str, **_kwargs) -> None:
        pass

    def title(self) -> str:
        return self._title

    def wait_for_selector(self, _selector: str, timeout: int = 30000) -> None:
        pass

    def wait_for_timeout(self, _ms: int) -> None:
        pass

    def locator(self, selector: str) -> _FakeLocator:
        if selector == "body":
            return _FakeLocator([self._body_text])
        return _FakeLocator(self._selector_texts.get(selector, []))


class _FakeBrowser:
    """Minimal Playwright BrowserContext double."""

    def __init__(self, page: _FakePage, has_auth_cookie: bool = True) -> None:
        self.pages = [page]
        self.closed = False
        self._has_auth_cookie = has_auth_cookie

    def cookies(self) -> list[dict]:
        if self._has_auth_cookie:
            return [{"name": "li_at", "value": "fake-session-token"}]
        return []

    def new_page(self) -> _FakePage:
        return self.pages[0]

    def close(self) -> None:
        self.closed = True


class _FakePlaywright:
    def __init__(self, page: _FakePage, has_auth_cookie: bool = True) -> None:
        self._page = page
        self._has_auth_cookie = has_auth_cookie
        self.chromium = self

    def launch_persistent_context(self, **_kwargs) -> _FakeBrowser:
        return _FakeBrowser(self._page, has_auth_cookie=self._has_auth_cookie)


class _FakePlaywrightContext:
    def __init__(self, page: _FakePage, has_auth_cookie: bool = True) -> None:
        self._playwright = _FakePlaywright(page, has_auth_cookie=has_auth_cookie)

    def __enter__(self) -> _FakePlaywright:
        return self._playwright

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _patch(page: _FakePage, has_auth_cookie: bool = True):
    """Returns a sync_playwright replacement for monkeypatching."""
    return lambda: _FakePlaywrightContext(page, has_auth_cookie=has_auth_cookie)


# ── Status detection tests ─────────────────────────────────────────────────────

def test_get_linkedin_job_detects_applied_status(monkeypatch) -> None:
    page = _FakePage(
        title="Principal Engineer | Acme Corp | LinkedIn",
        body_text="application submitted — check your profile",
    )
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/1/")

    assert result.title == "Principal Engineer"
    assert result.status == "applied"


def test_get_linkedin_job_detects_closed_status(monkeypatch) -> None:
    page = _FakePage(
        title="Site Reliability Engineer | Acme | LinkedIn",
        body_text="this role is no longer accepting applications.",
    )
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/2/")

    assert result.title == "Site Reliability Engineer"
    assert result.status == "closed"


def test_get_linkedin_job_detects_open_status_with_sdui_description(monkeypatch) -> None:
    page = _FakePage(
        title="Staff Engineer | Acme | LinkedIn",
        body_text="some generic page content",
        selector_texts={
            "[data-sdui-component*='aboutTheJob']": ["We are looking for a Staff Engineer..."],
        },
    )
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/3/")

    assert result.title == "Staff Engineer"
    assert result.status == "open"
    assert "Staff Engineer" in result.description


def test_get_linkedin_job_falls_back_to_selector_for_description(monkeypatch) -> None:
    page = _FakePage(
        title="Backend Engineer | Acme | LinkedIn",
        body_text="some generic page content",
        selector_texts={
            "#job-details": ["Backend role description from fallback."],
        },
    )
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/4/")

    assert result.title == "Backend Engineer"
    assert result.status == "open"
    assert result.description == "Backend role description from fallback."


def test_get_linkedin_job_title_strips_company_suffix(monkeypatch) -> None:
    page = _FakePage(title="Senior Dev | BigCorp | LinkedIn", body_text="open role")
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page))

    result = linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/5/")

    assert result.title == "Senior Dev"


def test_get_linkedin_job_raises_when_session_expired(monkeypatch) -> None:
    page = _FakePage(title="Job | LinkedIn", body_text="content")
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page, has_auth_cookie=False))

    with pytest.raises(LinkedInSessionExpiredError):
        linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/6/")


# ── Threading lock tests ───────────────────────────────────────────────────────

def test_playwright_lock_is_released_after_successful_call(monkeypatch) -> None:
    page = _FakePage(title="Job | LinkedIn", body_text="open role")
    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _patch(page))

    linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/7/")

    assert not linkedin_loader_private._playwright_lock.locked(), \
        "Lock must be released after a successful call"


def test_playwright_lock_is_released_after_exception(monkeypatch) -> None:
    def _bad_playwright():
        raise RuntimeError("Playwright exploded")

    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _bad_playwright)

    with pytest.raises(RuntimeError):
        linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/8/")

    assert not linkedin_loader_private._playwright_lock.locked(), \
        "Lock must be released even when an exception is raised"


def test_playwright_lock_is_held_during_call(monkeypatch) -> None:
    """Lock must be held at the moment sync_playwright() is entered."""
    lock_state: list[bool] = []

    def _spy_playwright():
        lock_state.append(linkedin_loader_private._playwright_lock.locked())
        return _FakePlaywrightContext(_FakePage(title="Job | LinkedIn", body_text="open"))

    monkeypatch.setattr(linkedin_loader_private, "sync_playwright", _spy_playwright)

    linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/9/")

    assert lock_state == [True], "Lock should be held during sync_playwright call"


def test_concurrent_calls_do_not_raise(monkeypatch) -> None:
    """Multiple threads calling get_linkedin_job must all complete without error."""
    monkeypatch.setattr(
        linkedin_loader_private, "sync_playwright",
        lambda: _FakePlaywrightContext(_FakePage(title="Job | LinkedIn", body_text="open role")),
    )

    errors: list[Exception] = []

    def _run():
        try:
            linkedin_loader_private.get_linkedin_job("https://www.linkedin.com/jobs/view/10/")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Concurrent calls raised exceptions: {errors}"
