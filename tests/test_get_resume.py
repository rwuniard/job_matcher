from pathlib import Path

from get_resume import get_resume


def test_get_resume_reads_file_contents(tmp_path: Path) -> None:
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Senior Engineer\nPython\n", encoding="utf-8")

    result = get_resume(str(resume_file))

    assert result == "Senior Engineer\nPython\n"
