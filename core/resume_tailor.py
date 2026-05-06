import re
import json
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from groq import Groq
from core.config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from core.resume_parser import ResumeData
from core.jd_analyzer import JobDescription
from core.company_researcher import CompanyProfile
from core.validator import check_integrity
from core.logger import setup_logger

logger = setup_logger(__name__)


class ChangeEntry(BaseModel):
    """One documented change made to the resume."""
    section: str                                         # e.g. "work_experience", "skills", "summary"
    original: str                                        # exact original text
    revised: str                                         # new text
    reason: str                                          # why this change improves the match
    change_type: Literal["reword", "reorder", "emphasize", "ats_inject"]
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str                               # why this confidence level was assigned
    ats_keywords_added: List[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """
    The modified resume plus a full audit trail of every change.

    work_experience and education are stored as plain dicts (not Pydantic
    models) because we receive them as JSON from the LLM and pass them
    directly to the output generator.
    """
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    work_experience: List[dict] = Field(default_factory=list)
    education: List[dict] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    changelog: List[ChangeEntry] = Field(default_factory=list)
    not_added: List[str] = Field(default_factory=list)  # JD skills absent from resume
    integrity_passed: bool = True


def _build_prompt(
    resume: ResumeData,
    jd: JobDescription,
    company: CompanyProfile,
    previous_violations: Optional[List[str]] = None,
) -> str:
    resume_json = resume.model_dump(exclude={"raw_text"})

    violation_block = ""
    if previous_violations:
        violation_block = (
            f"\n\nPREVIOUS ATTEMPT FAILED INTEGRITY CHECK.\n"
            f"These skills were added but do NOT exist in the original resume — "
            f"remove them entirely: {previous_violations}\n"
            f"Use ONLY skills that appear in the original resume skills list above.\n"
        )

    return f"""You are an expert resume writer. Tailor the resume below for the specific role.

INTEGRITY RULES — THESE ARE ABSOLUTE AND CANNOT BE BROKEN:
1. Do NOT add any skill, technology, or tool not already in the resume's skills list
2. Do NOT add any work experience, company, or job title not already in the resume
3. You MAY reword existing bullet points to use job description language — only if the bullet already describes that concept
4. You MAY reorder bullet points and skills to lead with the most relevant
5. ATS keywords may only be injected into a bullet that genuinely describes that keyword's concept
6. Every change MUST have a reason and a confidence score
{violation_block}
ORIGINAL RESUME:
{json.dumps(resume_json, indent=2)}

JOB DESCRIPTION:
- Title: {jd.job_title}
- Company: {jd.company_name or company.name}
- Required Skills: {", ".join(jd.required_skills)}
- Preferred Skills: {", ".join(jd.preferred_skills)}
- ATS Keywords: {", ".join(jd.ats_keywords)}
- Key Responsibilities: {chr(10).join(f"  • {r}" for r in jd.responsibilities[:6])}

COMPANY RESEARCH (confidence: {company.research_confidence}):
- Tech Stack: {", ".join(company.tech_stack) or "Not found"}
- Culture Values: {", ".join(company.culture_values) or "Not found"}
- Hiring Signals: {", ".join(company.hiring_signals) or "Not found"}

Return ONLY valid JSON with this exact structure:
{{
    "full_name": "string",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "summary": "rewritten summary if one exists, else null",
    "skills": [
        "EXACT skills from the original list — reordered to lead with JD-relevant ones",
        "NO new skills may be added"
    ],
    "work_experience": [
        {{
            "company": "string",
            "title": "string",
            "duration": "string",
            "responsibilities": ["reordered/reworded bullets — same concept, JD language where valid"],
            "achievements": ["reordered/reworded achievements"]
        }}
    ],
    "education": [same structure as input — no changes needed unless reordering],
    "certifications": [same as input],
    "projects": [same as input — may reorder by relevance],
    "languages": [same as input],
    "changelog": [
        {{
            "section": "work_experience / skills / summary / projects / certifications",
            "original": "exact original text before change",
            "revised": "new text after change",
            "reason": "specific reason — e.g. JD requires X and this bullet already describes X",
            "change_type": "reword / reorder / emphasize / ats_inject",
            "confidence": "high / medium / low",
            "confidence_reason": "e.g. high — the bullet clearly describes API development which directly matches the JD requirement for REST API experience",
            "ats_keywords_added": ["keywords injected if change_type is ats_inject, else empty list"]
        }}
    ],
    "not_added": [
        "list every JD required/preferred skill that is NOT in the resume and therefore was NOT added"
    ]
}}

CONFIDENCE SCORING GUIDE:
- high: The change clearly and directly improves the match. No ambiguity. A reviewer would agree immediately.
- medium: The change is likely beneficial but involves some interpretation of the bullet's meaning.
- low: The connection is plausible but uncertain. Flag for the user to review before sending.

Return ONLY the JSON object. No explanation, no markdown."""


def tailor_resume(
    resume: ResumeData,
    jd: JobDescription,
    company: CompanyProfile,
    max_retries: int = 2,
) -> TailoredResume:
    """
    Tailor the resume to the job description.

    Design:
      - Single-stage: the LLM is given the full resume, JD, and company
        context and asked to produce the tailored resume + changelog in one
        call. This mirrors the "analysis → writing" rule because the
        changelog IS the analysis — it must be justified before any change
        is accepted.
      - Integrity check runs after each attempt. If it fails, the violation
        is fed back to the LLM and we retry (up to max_retries).
    """
    client = Groq(api_key=GROQ_API_KEY)
    logger.info("Starting resume tailoring")

    previous_violations: Optional[List[str]] = None

    for attempt in range(max_retries + 1):
        try:
            prompt = _build_prompt(resume, jd, company, previous_violations)

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=GROQ_MAX_TOKENS,
                temperature=0.1,
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n?", "", content)
                content = re.sub(r"\n?```$", "", content)

            parsed = json.loads(content)

            integrity = check_integrity(
                original_resume=resume,
                tailored_content={
                    "skills": parsed.get("skills", []),
                    "jd_required_skills": jd.required_skills + jd.preferred_skills,
                },
            )

            if not integrity.passed and attempt < max_retries:
                logger.warning(
                    f"Integrity violation on attempt {attempt + 1}: "
                    f"{integrity.added_skills} — retrying"
                )
                previous_violations = integrity.added_skills
                continue

            changelog: List[ChangeEntry] = []
            for entry in parsed.get("changelog", []):
                try:
                    changelog.append(ChangeEntry(**entry))
                except Exception as e:
                    logger.warning(f"Skipping malformed changelog entry: {e}")

            tailored = TailoredResume(
                **{k: v for k, v in parsed.items() if k not in ("changelog", "not_added")},
                changelog=changelog,
                not_added=parsed.get("not_added", []),
                integrity_passed=integrity.passed,
            )

            logger.info(
                f"Tailoring complete: {len(changelog)} changes | "
                f"integrity_passed={tailored.integrity_passed} | "
                f"not_added={len(tailored.not_added)}"
            )
            return tailored

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise ValueError(
                    f"Resume tailoring failed after {max_retries + 1} attempts "
                    f"(LLM returned invalid JSON): {e}"
                )

        except Exception as e:
            logger.error(f"Tailoring error on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise

    raise ValueError("Resume tailoring failed after all retry attempts")
