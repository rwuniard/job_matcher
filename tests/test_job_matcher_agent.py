import job_matcher_agent
from linkedin_loader_private import LinkedInJob


def test_match_job_skips_agent_invoke_for_applied_job(monkeypatch, capsys) -> None:
    monkeypatch.setattr(job_matcher_agent, "get_resume", lambda _filename: "resume")
    monkeypatch.setattr(
        job_matcher_agent,
        "get_linkedin_job",
        lambda _url: LinkedInJob(title="Role", description="desc", status="applied"),
    )

    class _FakeAgent:
        def invoke(self, _payload):
            raise AssertionError("invoke should not be called for applied/closed jobs")

    monkeypatch.setattr(job_matcher_agent, "create_agent", lambda **_kwargs: _FakeAgent())
    monkeypatch.setattr(job_matcher_agent, "ChatGoogleGenerativeAI", lambda **_kwargs: object())

    job_matcher_agent.match_job("https://www.linkedin.com/jobs/view/1/")

    output = capsys.readouterr().out
    assert "The candidate has applied to the job or the job is closed." in output


def test_match_job_invokes_agent_for_open_job(monkeypatch, capsys) -> None:
    monkeypatch.setattr(job_matcher_agent, "get_resume", lambda _filename: "resume")
    monkeypatch.setattr(
        job_matcher_agent,
        "get_linkedin_job",
        lambda _url: LinkedInJob(
            title="Senior Platform Engineer",
            description="Build cloud platforms.",
            status="open",
        ),
    )

    captured = {}

    class _FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class _FakeAgent:
        def invoke(self, payload):
            captured["payload"] = payload
            return {"messages": [_FakeMessage("ignored"), _FakeMessage("match result")]}

    monkeypatch.setattr(job_matcher_agent, "create_agent", lambda **_kwargs: _FakeAgent())
    monkeypatch.setattr(job_matcher_agent, "ChatGoogleGenerativeAI", lambda **_kwargs: object())

    job_matcher_agent.match_job("https://www.linkedin.com/jobs/view/2/")

    output = capsys.readouterr().out
    assert "AI Response: match result" in output
    user_message = captured["payload"]["messages"][0]["content"]
    assert "Job Title: Senior Platform Engineer" in user_message
    assert "Job Description: Build cloud platforms." in user_message
    assert "Resume: resume" in user_message
