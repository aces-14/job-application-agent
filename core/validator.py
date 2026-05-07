import re
from typing import List, Tuple
from dataclasses import dataclass, field
from core.resume_parser import ResumeData
from core.jd_analyzer import JobDescription
from core.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

@dataclass
class IntegrityReport:
    passed: bool
    added_skills: List[str] = field(default_factory=list)
    removed_skills: List[str] = field(default_factory=list)
    added_experience: List[str] = field(default_factory=list)
    reworded_sections: List[str] = field(default_factory=list)
    not_added: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

def validate_resume_input(resume: ResumeData) -> ValidationResult:
    result = ValidationResult(is_valid=True)

    if not resume.full_name:
        result.errors.append("Resume missing candidate name.")
        result.is_valid = False

    if not resume.skills:
        result.warnings.append(
            "No skills detected in resume. "
            "Match scoring will be limited."
        )

    if not resume.work_experience:
        result.warnings.append(
            "No work experience detected. "
            "The tailored resume may be limited."
        )

    if len(resume.raw_text) < 200:
        result.errors.append(
            "Resume content is very short. "
            "Please ensure the full resume is uploaded."
        )
        result.is_valid = False

    logger.info(
        f"Resume validation: valid={result.is_valid}, "
        f"errors={len(result.errors)}, "
        f"warnings={len(result.warnings)}"
    )
    return result

def validate_jd_input(jd: JobDescription) -> ValidationResult:
    result = ValidationResult(is_valid=True)

    if jd.is_vague:
        result.warnings.append(
            f"Job description appears vague: "
            f"{', '.join(jd.vague_reasons)}"
        )
        result.info.append(
            "The agent will ask clarifying questions "
            "before proceeding."
        )

    if not jd.required_skills and not jd.preferred_skills:
        result.warnings.append(
            "No specific skills detected in job description. "
            "ATS keyword injection will be limited."
        )

    if not jd.job_title:
        result.errors.append("Could not detect job title from description.")
        result.is_valid = False

    logger.info(
        f"JD validation: valid={result.is_valid}, "
        f"vague={jd.is_vague}"
    )
    return result

def check_integrity(
    original_resume: ResumeData,
    tailored_content: dict
) -> IntegrityReport:
    report = IntegrityReport(passed=True)

    original_skills_lower = {s.lower() for s in original_resume.skills}
    tailored_skills = tailored_content.get("skills", [])
    tailored_skills_lower = {s.lower() for s in tailored_skills}

    # Check for added skills
    added = tailored_skills_lower - original_skills_lower
    if added:
        report.added_skills = list(added)
        report.violations.append(
            f"INTEGRITY VIOLATION: Skills added that were not "
            f"in original resume: {list(added)}"
        )
        report.passed = False
        logger.error(f"Integrity violation — added skills: {added}")

    # Check for removed skills
    removed = original_skills_lower - tailored_skills_lower
    if removed:
        report.removed_skills = list(removed)
        logger.info(f"Skills not included in tailored version: {removed}")

    # Identify JD skills NOT added (because not in resume)
    jd_skills = tailored_content.get("jd_required_skills", [])
    original_skills_lower_list = [s.lower() for s in original_resume.skills]
    not_added = [
        skill for skill in jd_skills
        if skill.lower() not in original_skills_lower_list
    ]
    report.not_added = not_added

    if not_added:
        logger.info(
            f"JD skills NOT added (not in resume): {not_added}"
        )

    logger.info(
        f"Integrity check: passed={report.passed}, "
        f"violations={len(report.violations)}"
    )
    return report

_STOP = {'and', 'or', 'the', 'of', 'in', 'for', 'with', 'to', 'a', 'an'}


def _tokenize(s: str) -> list:
    return [
        t for t in re.split(r'[\s/,().&+\-]+', s.lower())
        if len(t) >= 3 and t not in _STOP
    ]


def _tok_eq(a: str, b: str) -> bool:
    """Token equality with fuzzy prefix match for plurals/variants."""
    if a == b:
        return True
    if len(a) < 5 or len(b) < 5:
        return False
    n = min(len(a), len(b))
    shared = next((i for i in range(n) if a[i] != b[i]), n)
    # Match if shared prefix is ≥80% of the shorter token (min 5 chars)
    return shared >= max(5, int(n * 0.8))


def _skill_matches(resume_skill: str, jd_skill: str) -> bool:
    """
    Multi-strategy skill match:
    1. Exact string equality
    2. Substring containment (existing: 'django' in 'django rest framework')
    3. Token match: ALL tokens of the shorter phrase found in the longer phrase,
       with fuzzy prefix matching to handle plurals and minor variants
       ('agile methodology' matches 'agile/scrum development methodologies',
        'python django' matches 'Python (Django 4.x, Flask)')
    """
    r = resume_skill.strip().lower()
    j = jd_skill.strip().lower()
    if r == j:
        return True
    shorter, longer = (r, j) if len(r) <= len(j) else (j, r)
    if len(shorter) >= 3 and shorter in longer:
        return True
    r_toks = _tokenize(r)
    j_toks = _tokenize(j)
    if not r_toks or not j_toks:
        return False
    shorter_toks = r_toks if len(r_toks) <= len(j_toks) else j_toks
    longer_toks  = j_toks if len(r_toks) <= len(j_toks) else r_toks
    return all(any(_tok_eq(t, u) for u in longer_toks) for t in shorter_toks)


def _partition_skills(
    resume_skills: set, jd_skills: set
) -> Tuple[list, list]:
    matched, missing = [], []
    for jd_skill in jd_skills:
        if any(_skill_matches(r, jd_skill) for r in resume_skills):
            matched.append(jd_skill)
        else:
            missing.append(jd_skill)
    return matched, missing


def calculate_match_score(
    resume: ResumeData,
    jd: JobDescription
) -> Tuple[float, dict]:
    resume_skills_lower = {s.lower() for s in resume.skills}
    required_lower = {s.lower() for s in jd.required_skills}
    preferred_lower = {s.lower() for s in jd.preferred_skills}

    required_matches, missing_required = _partition_skills(resume_skills_lower, required_lower)
    preferred_matches, missing_preferred = _partition_skills(resume_skills_lower, preferred_lower)

    required_score = len(required_matches) / len(required_lower) if required_lower else 0.5
    preferred_score = len(preferred_matches) / len(preferred_lower) if preferred_lower else 0.5
    experience_score = 1.0 if resume.work_experience else 0.3

    total_score = (
        required_score * 0.6 +
        preferred_score * 0.2 +
        experience_score * 0.2
    )

    match_matrix = {
        "overall_score": round(total_score, 2),
        "required_score": round(required_score, 2),
        "preferred_score": round(preferred_score, 2),
        "experience_score": round(experience_score, 2),
        "matched_required": required_matches,
        "matched_preferred": preferred_matches,
        "missing_required": missing_required,
        "missing_preferred": missing_preferred,
        "match_level": (
            "Strong" if total_score >= 0.75
            else "Moderate" if total_score >= 0.5
            else "Weak"
        )
    }

    logger.info(f"Match score: {total_score:.2f} ({match_matrix['match_level']})")
    return total_score, match_matrix