"""Privacy-oriented tests for resume parsing."""

import logging

from spider_nix.intel.resume_parser import parse_resume


def test_parse_resume_logs_do_not_expose_contact_data(tmp_path, caplog):
    resume = tmp_path / "Candidate Example private resume.txt"
    resume.write_text(
        "\n".join(
            [
                "Candidate Example",
                "candidate.secret@example.com",
                "+1 555 0100 0100",
                "Senior Python Engineer",
                "Experience: 2018 - Present",
                "Python Rust Kubernetes",
            ]
        )
    )

    caplog.set_level(logging.INFO, logger="spider_nix.intel.resume_parser")

    data = parse_resume(resume)

    assert data.email == "candidate.secret@example.com"
    assert data.phone

    logs = caplog.text
    assert "candidate.secret@example.com" not in logs
    assert "+1 555 0100 0100" not in logs
    assert "Candidate Example" not in logs
    assert str(resume) not in logs
