"""
test_pipeline.py — Staged smoke tests for the Job Application Agent.

Run from the project root:
    python test_pipeline.py

The tests are staged so you can diagnose exactly where a failure occurs:
  Stage 1 — Import check     (catches missing packages, syntax errors)
  Stage 2 — Environment      (checks .env keys are present)
  Stage 3 — JD Analysis      (first real Groq API call)
  Stage 4 — Company Research (Groq + Tavily)
  Stage 5 — Full Pipeline    (requires a PDF in sample_data/)

Each stage prints PASS or FAIL with a reason.
Stop as soon as you see a FAIL — fix it before continuing.
"""

import os
import sys
import traceback
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"
WARN = "\033[93m  WARN\033[0m"


def section(title: str) -> None:
    print(f"\n{'─' * 56}")
    print(f"  {title}")
    print(f"{'─' * 56}")


def ok(msg: str) -> None:
    print(f"{PASS}  {msg}")


def fail(msg: str, hint: str = "") -> None:
    print(f"{FAIL}  {msg}")
    if hint:
        print(f"        Hint: {hint}")


def info(msg: str) -> None:
    print(f"{INFO}  {msg}")


def warn(msg: str) -> None:
    print(f"{WARN}  {msg}")


# ── Stage 1: Imports ──────────────────────────────────────────────────────────

def stage_1_imports() -> bool:
    section("Stage 1 — Import check")
    modules = [
        ("groq",                     "pip install groq"),
        ("tavily",                   "pip install tavily-python"),
        ("pypdf",                    "pip install pypdf"),
        ("docx",                     "pip install python-docx"),
        ("pydantic",                 "pip install pydantic"),
        ("dotenv",                   "pip install python-dotenv"),
        ("gradio",                   "pip install gradio"),
        ("core.config",              "check core/config.py"),
        ("core.logger",              "check core/logger.py"),
        ("core.resume_parser",       "check core/resume_parser.py"),
        ("core.jd_analyzer",         "check core/jd_analyzer.py"),
        ("core.validator",           "check core/validator.py"),
        ("core.audit_log",           "check core/audit_log.py"),
        ("core.company_researcher",  "check core/company_researcher.py"),
        ("core.resume_tailor",       "check core/resume_tailor.py"),
        ("core.cover_letter",        "check core/cover_letter.py"),
        ("core.outreach",            "check core/outreach.py"),
        ("core.output_generator",    "check core/output_generator.py"),
        ("agent.orchestrator",       "check agent/orchestrator.py"),
        ("ui.app",                   "check ui/app.py"),
    ]

    all_ok = True
    for module, hint in modules:
        try:
            __import__(module)
            ok(module)
        except Exception as e:
            fail(f"{module}  →  {e}", hint)
            all_ok = False

    return all_ok


# ── Stage 2: Environment ──────────────────────────────────────────────────────

def stage_2_env() -> bool:
    section("Stage 2 — Environment (.env)")
    from dotenv import load_dotenv
    load_dotenv()

    all_ok = True
    keys = {
        "GROQ_API_KEY":   ("gsk_...", "console.groq.com → API Keys"),
        "TAVILY_API_KEY": ("tvly-...", "app.tavily.com → API"),
    }

    for key, (prefix, source) in keys.items():
        val = os.getenv(key)
        if not val:
            fail(f"{key} is missing", f"Add it to .env — get it at {source}")
            all_ok = False
        elif not val.startswith(prefix.replace("...", "")):
            warn(f"{key} found but has unexpected prefix (expected {prefix})")
        else:
            ok(f"{key}  ({val[:12]}...)")

    return all_ok


# ── Stage 3: JD Analyzer ─────────────────────────────────────────────────────

SAMPLE_JD = """
Software Engineer — Backend
Company: Acme Corp | Full-time | Remote

We are looking for a Backend Software Engineer to join our platform team.

Requirements:
- 3+ years of experience with Python
- Strong knowledge of REST API design
- Experience with PostgreSQL and Redis
- Familiarity with Docker and Kubernetes
- Experience with cloud platforms (AWS preferred)

Nice to have:
- FastAPI or Django experience
- Knowledge of message queues (Kafka, RabbitMQ)
- CI/CD pipeline experience (GitHub Actions)

Responsibilities:
- Design and implement scalable backend services
- Write clean, well-tested Python code
- Collaborate with frontend engineers on API contracts
- Participate in on-call rotation
- Review pull requests and mentor junior engineers

We value ownership, speed, and technical clarity.
"""


def stage_3_jd_analyzer() -> bool:
    section("Stage 3 — JD Analyzer (first Groq call)")

    try:
        from core.jd_analyzer import analyze_job_description

        info("Sending sample JD to Groq LLM...")
        jd = analyze_job_description(SAMPLE_JD)

        ok(f"Job title detected:      {jd.job_title}")
        ok(f"Required skills:         {jd.required_skills[:3]} ...")
        ok(f"Preferred skills:        {jd.preferred_skills[:3]} ...")
        ok(f"ATS keywords:            {jd.ats_keywords[:3]} ...")
        ok(f"Vague JD flag:           {jd.is_vague}")

        if not jd.required_skills:
            warn("No required skills extracted — JD may be too vague")
        return True

    except Exception as e:
        fail(f"JD analysis failed: {e}")
        traceback.print_exc()
        return False


# ── Stage 4: Company Research ─────────────────────────────────────────────────

def stage_4_company_research() -> bool:
    section("Stage 4 — Company Research (Groq + Tavily)")

    try:
        from core.company_researcher import research_company

        info("Searching for 'Stripe' (Software Engineer role)...")
        profile = research_company("Stripe", "Software Engineer")

        ok(f"Research confidence:     {profile.research_confidence}")
        ok(f"Tech stack found:        {profile.tech_stack[:3]} ...")
        ok(f"Culture values:          {profile.culture_values[:2]} ...")
        ok(f"Recent news items:       {len(profile.recent_news)}")
        ok(f"Search queries used:     {len(profile.search_queries_used)}")

        if profile.research_confidence == "low":
            warn("Low confidence — Tavily may have returned limited results for Stripe")

        return True

    except Exception as e:
        fail(f"Company research failed: {e}")
        traceback.print_exc()
        return False


# ── Stage 5: Full Pipeline ────────────────────────────────────────────────────

def stage_5_full_pipeline() -> bool:
    section("Stage 5 — Full Pipeline (requires sample_data/resume.docx)")

    docx_path = Path("sample_data/resume.docx")

    if not docx_path.exists():
        warn(
            "sample_data/resume.docx not found — skipping full pipeline test.\n"
            "        To run this stage:\n"
            "          1. Copy your resume .docx to sample_data/resume.docx\n"
            "          2. Re-run: python test_pipeline.py"
        )
        return True  # not a failure, just skipped

    try:
        from agent.orchestrator import run_streaming

        info(f"Using resume: {docx_path}")
        info("Running full pipeline (15–30 seconds)...")

        with open(docx_path, "rb") as f:
            resume_bytes = f.read()

        final_package = None
        for update in run_streaming(resume_bytes, SAMPLE_JD, "Acme Corp"):
            if update.status == "error":
                fail(f"Pipeline error at step '{update.current_step}': {update.error_message}")
                return False

            step_label = update.current_step.replace("_", " ").title()
            if update.package is None:
                info(f"Running: {step_label}...")
            else:
                final_package = update.package
                ok(f"Pipeline complete!")

        if final_package:
            ok(f"Candidate:           {final_package.candidate_name}")
            ok(f"Match score:         {final_package.match_score:.0%} ({final_package.match_level})")
            ok(f"Changes made:        {len(final_package.tailored_resume.changelog)}")
            ok(f"Not added (integrity): {len(final_package.tailored_resume.not_added)} JD skills")
            ok(f"Cover letter words:  {len(final_package.cover_letter.split())}")
            ok(f"Outreach words:      {len(final_package.outreach_message.split())}")
            ok(f"Warnings:            {len(final_package.warnings)}")
            ok(f"Resume docx:         {final_package.resume_docx_path}")

            if final_package.warnings:
                for w in final_package.warnings:
                    warn(w)

        return True

    except Exception as e:
        fail(f"Full pipeline failed: {e}")
        traceback.print_exc()
        return False


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 56)
    print("  Job Application Agent — Pipeline Smoke Tests")
    print("═" * 56)

    stages = [
        ("Imports",          stage_1_imports),
        ("Environment",      stage_2_env),
        ("JD Analyzer",      stage_3_jd_analyzer),
        ("Company Research", stage_4_company_research),
        ("Full Pipeline",    stage_5_full_pipeline),
    ]

    results = {}
    for name, fn in stages:
        passed = fn()
        results[name] = passed
        if not passed and name in ("Imports", "Environment"):
            print(f"\n\033[91m  Stopping early — fix {name} before continuing.\033[0m\n")
            break

    # Summary
    section("Summary")
    all_passed = True
    for name, passed in results.items():
        status = PASS if passed else FAIL
        print(f"{status}  {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n\033[92m  All tests passed. Run the UI with:\033[0m")
        print("    python app.py")
        print("    Then open: http://localhost:7860\n")
    else:
        print(f"\n\033[91m  Fix the failures above before running the UI.\033[0m\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
