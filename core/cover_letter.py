from groq import Groq
from core.config import GROQ_API_KEY, GROQ_MODEL, GROQ_COVER_LETTER_TEMPERATURE
from core.resume_parser import ResumeData
from core.jd_analyzer import JobDescription
from core.company_researcher import CompanyProfile
from core.resume_tailor import TailoredResume
from core.logger import setup_logger

logger = setup_logger(__name__)


def _pick_company_hook(company: CompanyProfile, jd: JobDescription) -> str:
    """
    Pick the most specific thing we can reference about the company.
    Specificity makes the letter feel researched, not templated.
    """
    if company.recent_news:
        return company.recent_news[0]
    if company.products:
        return f"their work on {company.products[0]}"
    if company.culture_values:
        return f"their focus on {company.culture_values[0]}"
    return f"the {jd.job_title} opportunity"


def _build_prompt(
    resume: ResumeData,
    jd: JobDescription,
    company: CompanyProfile,
    tailored: TailoredResume,
) -> str:
    top_roles = [
        f"{exp['title']} at {exp['company']}"
        for exp in tailored.work_experience[:2]
        if exp.get("title") and exp.get("company")
    ]

    # Pick strongest achievement or responsibility from the most recent role
    proof_point = ""
    if tailored.work_experience:
        first = tailored.work_experience[0]
        pool = first.get("achievements") or first.get("responsibilities") or []
        proof_point = pool[0] if pool else ""

    hook = _pick_company_hook(company, jd)
    relevant_skills = [s for s in tailored.skills if s.lower() in
                       {k.lower() for k in jd.required_skills + jd.preferred_skills}][:6]

    return f"""Write a professional cover letter. It must sound like a real person wrote it — not AI, not a template.

CANDIDATE:
- Name: {resume.full_name}
- Most recent roles: {", ".join(top_roles) or "See resume"}
- Strongest proof point: {proof_point or "Extensive relevant experience"}
- Skills matching this role: {", ".join(relevant_skills) or ", ".join(tailored.skills[:6])}

ROLE:
- Position: {jd.job_title}
- Company: {company.name}
- Key requirements: {", ".join(jd.required_skills[:5])}
- Main responsibilities: {" | ".join(jd.responsibilities[:3])}

COMPANY CONTEXT (research confidence: {company.research_confidence}):
- Products/Services: {", ".join(company.products[:3]) or "Not found"}
- Culture: {", ".join(company.culture_values[:3]) or "Not found"}
- Best hook to reference: {hook}

LETTER STRUCTURE — follow this precisely:

Paragraph 1 — Hook (2-3 sentences MAX):
Open by referencing {hook} specifically. Connect it immediately to why you are applying for this role.
Do NOT start with "I am writing to apply" or "I am excited to apply".

Paragraph 2 — Proof (3-4 sentences):
Name 1-2 specific experiences from your background. Connect them directly to {jd.job_title} responsibilities.
Use concrete details — numbers, outcomes, technology names. Reference the proof point above if relevant.

Paragraph 3 — Fit (2-3 sentences):
Show you understand {company.name}'s culture or mission. Reference something specific from the company context.
Explain why their environment suits how you work.

Paragraph 4 — Close (1-2 sentences):
Express interest in a conversation. Confident, not desperate.

STRICT RULES:
- Total: 250-350 words
- NEVER use: "passionate", "motivated", "hard worker", "team player", "leverage", "utilize", "synergy", "dynamic"
- No "I am a [adjective] [noun]" openers
- Be specific — a vague sentence is worse than no sentence
- First person throughout
- No subject line, no salutation, no sign-off

Output ONLY the letter body. Nothing else."""


def write_cover_letter(
    resume: ResumeData,
    jd: JobDescription,
    company: CompanyProfile,
    tailored: TailoredResume,
) -> str:
    """
    Generate a personalized cover letter using Groq.

    Uses a higher temperature (0.4) than other calls because cover letters
    need natural, varied prose — not the uniform, fact-extraction output
    we need for resume parsing or JD analysis.
    """
    client = Groq(api_key=GROQ_API_KEY)
    logger.info(f"Writing cover letter — {jd.job_title} at {company.name}")

    prompt = _build_prompt(resume, jd, company, tailored)

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=GROQ_COVER_LETTER_TEMPERATURE,
        )
        letter = response.choices[0].message.content.strip()
        word_count = len(letter.split())
        logger.info(f"Cover letter written: {word_count} words")
        return letter

    except Exception as e:
        logger.error(f"Cover letter generation failed: {e}")
        raise
