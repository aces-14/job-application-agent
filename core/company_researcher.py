import re
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from tavily import TavilyClient
from groq import Groq
from core.config import GROQ_API_KEY, GROQ_MODEL, TAVILY_API_KEY
from core.logger import setup_logger

logger = setup_logger(__name__)


class CompanyProfile(BaseModel):
    name: str
    products: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    culture_values: List[str] = Field(default_factory=list)
    recent_news: List[str] = Field(default_factory=list)
    company_stage: Optional[str] = None
    hiring_signals: List[str] = Field(default_factory=list)
    search_queries_used: List[str] = Field(default_factory=list)
    research_confidence: str = "low"  # high / medium / low


def _build_search_queries(company_name: str, job_title: str) -> List[str]:
    return [
        f"{company_name} engineering tech stack programming languages tools",
        f"{company_name} company culture values mission team",
        f"{company_name} news 2024 2025",
        f"{company_name} {job_title} engineering team",
    ]


def _run_searches(company_name: str, job_title: str) -> tuple[List[str], List[str]]:
    """Run Tavily searches and return (raw_result_snippets, queries_used)."""
    client = TavilyClient(api_key=TAVILY_API_KEY)
    queries = _build_search_queries(company_name, job_title)

    all_snippets: List[str] = []
    queries_used: List[str] = []

    for query in queries:
        try:
            result = client.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=True,
            )
            if result.get("answer"):
                all_snippets.append(f"[Query: {query}]\n{result['answer']}")
            for r in result.get("results", [])[:2]:
                if r.get("content"):
                    all_snippets.append(
                        f"[{r.get('title', query)}]\n{r['content'][:600]}"
                    )
            queries_used.append(query)
            logger.info(f"Search done: {query}")
        except Exception as e:
            logger.warning(f"Search failed — '{query}': {e}")

    return all_snippets, queries_used


def _synthesize(company_name: str, snippets: List[str]) -> dict:
    """Use Groq to distill raw snippets into a structured CompanyProfile dict."""
    client = Groq(api_key=GROQ_API_KEY)
    combined = "\n\n---\n\n".join(snippets) if snippets else "No results found."

    prompt = f"""Analyze these web search results about {company_name} and extract structured information.

SEARCH RESULTS:
{combined}

Return ONLY valid JSON with this exact structure:
{{
    "products": ["main products or services"],
    "tech_stack": ["programming languages, frameworks, databases, cloud tools they use"],
    "culture_values": ["company values, culture traits, working style mentioned"],
    "recent_news": ["notable events, launches, or news from 2024-2025"],
    "company_stage": "startup / scaleup / enterprise / public — or null if unknown",
    "hiring_signals": ["what they seem to prioritize in new hires based on research"],
    "research_confidence": "high / medium / low"
}}

RULES:
- Only include information actually found in the results above
- Do NOT invent anything not in the results
- Empty list if a field has no data
- research_confidence: high = rich specific info found, medium = some info, low = very little
- Return ONLY the JSON object, no explanation"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.0,
    )

    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\n?", "", content)
        content = re.sub(r"\n?```$", "", content)

    return json.loads(content)


def research_company(company_name: str, job_title: str) -> CompanyProfile:
    """
    Main entry point.

    Runs 4 Tavily web searches, synthesizes results with Groq,
    and returns a structured CompanyProfile.

    If company_name is blank or unknown, returns an empty profile
    with research_confidence="low" — the rest of the pipeline
    continues gracefully without company data.
    """
    logger.info(f"Researching: {company_name!r} for role: {job_title!r}")

    if not company_name or company_name.strip().lower() in ("", "unknown", "n/a"):
        logger.warning("No company name — skipping research")
        return CompanyProfile(name="Unknown", research_confidence="low")

    try:
        snippets, queries_used = _run_searches(company_name, job_title)

        if not snippets:
            logger.warning(f"No search results for {company_name!r}")
            return CompanyProfile(
                name=company_name,
                research_confidence="low",
                search_queries_used=queries_used,
            )

        synthesized = _synthesize(company_name, snippets)

        profile = CompanyProfile(
            name=company_name,
            search_queries_used=queries_used,
            **synthesized,
        )

        logger.info(
            f"Research complete: {company_name!r} | "
            f"confidence={profile.research_confidence} | "
            f"tech_stack={len(profile.tech_stack)} items"
        )
        return profile

    except Exception as e:
        logger.error(f"Company research failed: {e}")
        return CompanyProfile(name=company_name, research_confidence="low")
