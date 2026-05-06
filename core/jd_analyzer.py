import re
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from groq import Groq
from core.config import GROQ_API_KEY, GROQ_MODEL
from core.logger import setup_logger

logger = setup_logger(__name__)

class JobRequirement(BaseModel):
    skill: str
    is_required: bool
    is_preferred: bool
    context: str

class JobDescription(BaseModel):
    job_title: str
    company_name: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    ats_keywords: List[str] = Field(default_factory=list)
    company_values: List[str] = Field(default_factory=list)
    raw_text: str = ""
    is_vague: bool = False
    vague_reasons: List[str] = Field(default_factory=list)

def analyze_job_description(jd_text: str) -> JobDescription:
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""Analyze this job description and return ONLY valid JSON.

Return this exact structure:
{{
    "job_title": "string",
    "company_name": "string or null",
    "location": "string or null",
    "employment_type": "full-time/part-time/contract or null",
    "experience_required": "string or null",
    "required_skills": ["skills marked as required or must-have"],
    "preferred_skills": ["skills marked as preferred or nice-to-have"],
    "responsibilities": ["key responsibilities"],
    "ats_keywords": ["important keywords for ATS systems"],
    "company_values": ["company culture and values mentioned"],
    "is_vague": true or false,
    "vague_reasons": ["list reasons if vague, empty if not"]
}}

A job description is VAGUE if:
- Required experience is unclear
- Skills are too generic (e.g. "good communication skills" only)
- No specific technical requirements mentioned
- Responsibilities are too broad

JOB DESCRIPTION:
{jd_text}

Return ONLY the JSON object."""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.0
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\n?', '', content)
            content = re.sub(r'\n?```$', '', content)

        parsed = json.loads(content)
        jd = JobDescription(**parsed, raw_text=jd_text)

        logger.info(
            f"JD analyzed: {jd.job_title}, "
            f"{len(jd.required_skills)} required skills, "
            f"vague={jd.is_vague}"
        )
        return jd

    except Exception as e:
        logger.error(f"JD analysis failed: {str(e)}")
        raise