from groq import Groq
from core.config import GROQ_API_KEY, GROQ_MODEL
from core.resume_parser import ResumeData
from core.jd_analyzer import JobDescription
from core.company_researcher import CompanyProfile
from core.logger import setup_logger

logger = setup_logger(__name__)


def _pick_hook(company: CompanyProfile, jd: JobDescription) -> str:
    """Pick the most specific reference point for the opening line."""
    if company.recent_news:
        return company.recent_news[0]
    if company.products:
        return f"{company.name}'s {company.products[0]}"
    if company.tech_stack:
        return f"{company.name}'s use of {company.tech_stack[0]}"
    return f"{company.name}'s work in this space"


def _build_prompt(
    resume: ResumeData,
    jd: JobDescription,
    company: CompanyProfile,
) -> str:
    most_recent = resume.work_experience[0] if resume.work_experience else None
    recent_role = (
        f"{most_recent.title} at {most_recent.company}"
        if most_recent else "my recent work"
    )
    hook = _pick_hook(company, jd)

    return f"""Write a LinkedIn connection request message from a job seeker to someone at {company.name}.

CANDIDATE:
- Name: {resume.full_name}
- Most recent role: {recent_role}
- Top skills relevant to this role: {", ".join(resume.skills[:4])}
- Applying for: {jd.job_title}

COMPANY:
- Name: {company.name}
- Specific hook to reference: {hook}
- Culture: {", ".join(company.culture_values[:2]) or "Not found"}

MESSAGE RULES:
- Total length: 80-120 words (LinkedIn enforces limits)
- Structure:
    Line 1: Reference {hook} specifically — show genuine interest, not flattery
    Lines 2-3: One-sentence intro — who you are and your most relevant experience
    Line 4: Soft ask — a conversation, NOT "please refer me" or "can you get me an interview"
- Do NOT use: "I came across your profile", "I would love to pick your brain", "I hope this message finds you well"
- Do NOT mention applying — this is a connection request, not a job application
- Sound like a real human, not a recruiter template
- End with a low-pressure question or ask

Output ONLY the message text. Nothing else."""


def write_outreach_message(
    resume: ResumeData,
    jd: JobDescription,
    company: CompanyProfile,
) -> str:
    """
    Generate a short LinkedIn outreach message using Groq.

    Temperature 0.35 — slightly creative but still controlled.
    The message needs to feel personal, not mass-produced.
    """
    client = Groq(api_key=GROQ_API_KEY)
    logger.info(f"Writing LinkedIn outreach — {jd.job_title} at {company.name}")

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": _build_prompt(resume, jd, company)}],
            max_tokens=256,
            temperature=0.35,
        )
        message = response.choices[0].message.content.strip()
        logger.info(f"Outreach written: {len(message.split())} words")
        return message

    except Exception as e:
        logger.error(f"Outreach generation failed: {e}")
        raise
