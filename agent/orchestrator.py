"""
orchestrator.py — The main pipeline coordinator.

Runs all steps in order, manages the audit log, handles errors
and weak-match warnings, and yields progress updates so the UI
can show a real-time step tracker without blocking.

Pattern used: generator-based streaming.
  - Each `yield` sends a ProgressUpdate to the caller (the UI).
  - The UI renders it immediately, then the generator resumes the next step.
  - This gives the user visual feedback during the ~15-30 second run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generator, List, Optional

from core.audit_log import create_audit_log
from core.company_researcher import CompanyProfile, research_company
from core.config import MATCH_SCORE_THRESHOLD
from core.cover_letter import write_cover_letter
from core.jd_analyzer import analyze_job_description
from core.logger import setup_logger
from core.output_generator import (
    generate_match_report,
    generate_resume_docx,
    generate_text_outputs,
)
from core.outreach import write_outreach_message
from core.resume_parser import parse_resume
from core.resume_tailor import TailoredResume, tailor_resume
from core.validator import (
    calculate_match_score,
    check_integrity,
    validate_jd_input,
    validate_resume_input,
)

logger = setup_logger(__name__)

# ── Step registry ────────────────────────────────────────────────────────────
# Order matters — this defines both execution order and the UI display order.
PIPELINE_STEPS: list[tuple[str, str]] = [
    ("parse_resume",  "Parse Resume"),
    ("analyze_jd",    "Analyze Job Description"),
    ("validate",      "Validate Inputs"),
    ("match_score",   "Calculate Match Score"),
    ("research",      "Research Company"),
    ("tailor",        "Tailor Resume"),
    ("cover_letter",  "Write Cover Letter"),
    ("outreach",      "Write LinkedIn Outreach"),
    ("export",        "Generate Output Files"),
]

STEP_KEYS = [k for k, _ in PIPELINE_STEPS]


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class ApplicationPackage:
    """Everything produced by one pipeline run."""
    session_id: str
    candidate_name: str
    job_title: str
    company_name: str
    match_score: float
    match_level: str
    match_matrix: dict
    tailored_resume: TailoredResume
    cover_letter: str
    outreach_message: str
    resume_docx_path: str
    cover_letter_path: str
    outreach_path: str
    match_report_path: str
    audit_log_path: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class ProgressUpdate:
    """
    Yielded after every step so the UI can update the progress tracker.

    - current_step: the step key currently executing (or "done" / "error")
    - completed:    list of step keys that have fully finished
    - status:       "running" | "done" | "error"
    - package:      populated only on the final "done" yield
    - error_message: populated only on "error" yields
    """
    current_step: str
    completed: List[str]
    status: str
    package: Optional[ApplicationPackage] = None
    error_message: str = ""


# ── Main pipeline ────────────────────────────────────────────────────────────

def run_streaming(
    resume_bytes: bytes,
    jd_text: str,
    company_name: str,
) -> Generator[ProgressUpdate, None, None]:
    """
    Run the full job application pipeline as a generator.

    Yields a ProgressUpdate before starting each step (status="running"),
    and one final ProgressUpdate when everything is complete (status="done").
    On unrecoverable error, yields status="error" with an error_message.

    Why a generator?
    ─────────────────
    The pipeline takes 15-30 seconds. Without streaming, the UI would show
    a blank spinner the entire time. By yielding after each step, the UI
    can update a real-time progress tracker so the user sees work happening.
    This is the same pattern used by streaming LLM responses.
    """
    completed: List[str] = []
    current_step = "init"

    def _progress(step: str) -> ProgressUpdate:
        return ProgressUpdate(
            current_step=step,
            completed=list(completed),
            status="running",
        )

    def _done(step: str) -> None:
        completed.append(step)
        logger.info(f"Step complete: {step}")

    try:
        # ── Step 1: Parse resume ─────────────────────────────────────────
        current_step = "parse_resume"
        yield _progress(current_step)
        resume = parse_resume(resume_bytes)
        _done(current_step)

        # ── Step 2: Analyze job description ─────────────────────────────
        current_step = "analyze_jd"
        yield _progress(current_step)
        jd = analyze_job_description(jd_text)
        _done(current_step)

        # Resolve company name (prefer user input, fall back to JD field)
        resolved_company = (
            company_name.strip()
            or (jd.company_name or "Unknown")
        )

        # Create audit log now that we have names
        audit = create_audit_log(
            candidate_name=resume.full_name,
            job_title=jd.job_title,
            company=resolved_company,
        )
        session_id = audit.session_id

        audit.add_entry(
            step="parse_resume",
            action="Parsed resume PDF",
            input_summary=f"{len(resume_bytes):,} bytes",
            output_summary=(
                f"{resume.full_name} | "
                f"{len(resume.skills)} skills | "
                f"{len(resume.work_experience)} positions"
            ),
            reasoning="Structured extraction — single source of truth for all downstream steps",
        )
        audit.add_entry(
            step="analyze_jd",
            action="Analyzed job description",
            input_summary=f"{len(jd_text):,} chars",
            output_summary=(
                f"{jd.job_title} | "
                f"{len(jd.required_skills)} required | "
                f"{len(jd.preferred_skills)} preferred | "
                f"vague={jd.is_vague}"
            ),
            reasoning="Extracted requirements, ATS keywords, and vagueness flag",
        )

        # ── Step 3: Validate ─────────────────────────────────────────────
        current_step = "validate"
        yield _progress(current_step)
        resume_val = validate_resume_input(resume)
        jd_val = validate_jd_input(jd)

        warnings: List[str] = []
        warnings.extend(resume_val.warnings)
        warnings.extend(jd_val.warnings)

        if jd.is_vague:
            warnings.append(
                f"Job description is vague ({', '.join(jd.vague_reasons)}). "
                "Outputs will be generated but may be less targeted — "
                "consider adding more detail to the JD text."
            )

        if not resume_val.is_valid:
            raise ValueError(
                "Resume validation failed: " + " | ".join(resume_val.errors)
            )

        _done(current_step)

        # ── Step 4: Match score ──────────────────────────────────────────
        current_step = "match_score"
        yield _progress(current_step)
        match_score, match_matrix = calculate_match_score(resume, jd)
        audit.final_match_score = match_score

        if match_score < MATCH_SCORE_THRESHOLD:
            warnings.append(
                f"Weak match detected ({int(match_score * 100)}%). "
                f"Your resume covers fewer than 60% of the required skills. "
                f"All outputs are still generated — review the Match Report "
                f"to understand the gaps."
            )

        audit.add_entry(
            step="match_score",
            action="Calculated resume–JD match score",
            input_summary="Resume skills vs JD required + preferred skills",
            output_summary=f"{match_score:.0%} ({match_matrix['match_level']})",
            reasoning="Weighted: required 60% + preferred 20% + experience 20%",
            confidence=match_matrix["match_level"].lower(),
        )
        _done(current_step)

        # ── Step 5: Company research ─────────────────────────────────────
        current_step = "research"
        yield _progress(current_step)
        company = research_company(resolved_company, jd.job_title)

        if company.research_confidence == "low":
            warnings.append(
                f"Limited data found for '{resolved_company}'. "
                "Cover letter and outreach will use available context "
                "but may be less specific."
            )

        audit.add_entry(
            step="research",
            action="Researched company via web search",
            input_summary=f"Company: {resolved_company}",
            output_summary=(
                f"confidence={company.research_confidence} | "
                f"tech={len(company.tech_stack)} items | "
                f"news={len(company.recent_news)} items"
            ),
            reasoning="Personalize cover letter and outreach with real company context",
            confidence=company.research_confidence,
        )
        _done(current_step)

        # ── Step 6: Tailor resume ────────────────────────────────────────
        current_step = "tailor"
        yield _progress(current_step)
        tailored = tailor_resume(resume, jd, company)

        if not tailored.integrity_passed:
            warnings.append(
                "Resume integrity check did not fully pass. "
                "The tailored resume was accepted after retries but may contain "
                "unverified changes — review the changelog carefully before sending."
            )

        audit.add_entry(
            step="tailor",
            action="Tailored resume for role",
            input_summary="ResumeData + JobDescription + CompanyProfile",
            output_summary=(
                f"{len(tailored.changelog)} changes | "
                f"integrity_passed={tailored.integrity_passed} | "
                f"{len(tailored.not_added)} JD skills not added (not in resume)"
            ),
            reasoning="Reorder + reword for ATS + relevance; no new skills added",
            confidence="high" if tailored.integrity_passed else "medium",
            warnings=(
                [] if tailored.integrity_passed
                else ["Integrity check needed multiple retries"]
            ),
        )
        _done(current_step)

        # ── Step 7: Cover letter ─────────────────────────────────────────
        current_step = "cover_letter"
        yield _progress(current_step)
        cover_letter = write_cover_letter(resume, jd, company, tailored)

        audit.add_entry(
            step="cover_letter",
            action="Wrote personalized cover letter",
            input_summary="Resume + JD + company context + tailored resume",
            output_summary=f"{len(cover_letter.split())} words",
            reasoning="Hook-first structure; connects candidate background to company specifics",
        )
        _done(current_step)

        # ── Step 8: LinkedIn outreach ────────────────────────────────────
        current_step = "outreach"
        yield _progress(current_step)
        outreach = write_outreach_message(resume, jd, company)

        audit.add_entry(
            step="outreach",
            action="Wrote LinkedIn outreach message",
            input_summary="Resume + JD + company context",
            output_summary=f"{len(outreach.split())} words",
            reasoning="Short, specific message — connection request, not job application",
        )
        _done(current_step)

        # ── Step 9: Export files ─────────────────────────────────────────
        current_step = "export"
        yield _progress(current_step)

        integrity_report = check_integrity(
            original_resume=resume,
            tailored_content={
                "skills": tailored.skills,
                "jd_required_skills": jd.required_skills + jd.preferred_skills,
            },
        )

        resume_path = generate_resume_docx(tailored, session_id)
        cl_path, out_path = generate_text_outputs(cover_letter, outreach, session_id)
        report_path = generate_match_report(
            match_matrix, integrity_report, tailored.changelog, session_id
        )
        audit_path = audit.save()

        _done(current_step)

        # ── Final yield: complete package ────────────────────────────────
        package = ApplicationPackage(
            session_id=session_id,
            candidate_name=resume.full_name,
            job_title=jd.job_title,
            company_name=resolved_company,
            match_score=match_score,
            match_level=match_matrix["match_level"],
            match_matrix=match_matrix,
            tailored_resume=tailored,
            cover_letter=cover_letter,
            outreach_message=outreach,
            resume_docx_path=resume_path,
            cover_letter_path=cl_path,
            outreach_path=out_path,
            match_report_path=report_path,
            audit_log_path=audit_path,
            warnings=warnings,
        )

        logger.info(
            f"Pipeline complete | session={session_id} | "
            f"match={match_score:.0%} | warnings={len(warnings)}"
        )

        yield ProgressUpdate(
            current_step="done",
            completed=list(completed),
            status="done",
            package=package,
        )

    except Exception as e:
        logger.error(f"Pipeline failed at step '{current_step}': {e}", exc_info=True)
        yield ProgressUpdate(
            current_step=current_step,
            completed=list(completed),
            status="error",
            error_message=str(e),
        )
