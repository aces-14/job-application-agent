# Job Application Assistant Agent — Project Plan

> This document is the single source of truth for the project. Read it before touching any file.
> Last updated: 2026-05-06

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Current State — What's Already Built](#2-current-state--whats-already-built)
3. [Full Architecture](#3-full-architecture)
4. [What Still Needs to Be Built](#4-what-still-needs-to-be-built)
5. [Build Order — Step by Step](#5-build-order--step-by-step)
6. [Tech Decisions Explained](#6-tech-decisions-explained)
7. [The Agent Pattern — How It Works](#7-the-agent-pattern--how-it-works)
8. [Project Rules — Non-Negotiable](#8-project-rules--non-negotiable)
9. [API Keys and Security](#9-api-keys-and-security)
10. [Cost Estimate](#10-cost-estimate)
11. [Deployment Guide — Hugging Face Spaces](#11-deployment-guide--hugging-face-spaces)
12. [UI Design Spec](#12-ui-design-spec)
13. [Testing Plan](#13-testing-plan)

---

## 1. What This Project Is

A job application agent that takes three inputs — a resume PDF, a job description, and a company name — and produces three outputs: a tailored resume, a personalized cover letter, and a LinkedIn outreach message. It does this by reasoning through a series of steps, using web search, LLM writing, and integrity checks to ensure the resume is never falsified.

**Why it's an "agent" and not just a script:** A regular script has hardcoded steps. An agent reasons about which steps to take and in what order. If company research reveals a specific tech stack, the agent adjusts the resume emphasis without being told to. That's the core difference.

---

## 2. Current State — What's Already Built

### core/config.py ✅
Loads environment variables, defines model names and integrity rules. The integrity rules are the guard rails:
- `ALLOW_REWORDING = True` — can rephrase existing content
- `ALLOW_REORDERING = True` — can reorder bullet points for emphasis
- `ALLOW_ADDING_SKILLS = False` — cannot add skills the candidate does not have
- `ALLOW_ADDING_EXPERIENCE = False` — cannot fabricate experience

**Note:** We switched from OpenAI GPT-4o-mini to Groq (free tier). We still use Anthropic Claude for cover letter writing.

### core/logger.py ✅
Structured logger with a `SensitiveFilter` that scrubs API keys from logs. Both console and file output. This is production-level hygiene.

### core/resume_parser.py ✅
Reads a PDF, extracts raw text with pypdf, then sends it to Groq LLM with a strict prompt that forbids hallucination. Returns a validated `ResumeData` Pydantic model (structured JSON). This is the single source of truth for all downstream steps.

**Key models:**
- `ResumeData` — the full resume as structured data
- `WorkExperience` — one job entry
- `Education` — one education entry

### core/jd_analyzer.py ✅
Analyzes a job description text and returns a `JobDescription` Pydantic model. Detects if the JD is vague (too generic to extract useful requirements). Extracts ATS keywords separately from skills.

### core/validator.py ✅
Three functions:
- `validate_resume_input()` — checks the resume has minimum required fields
- `validate_jd_input()` — checks the JD is usable, warns if vague
- `check_integrity()` — after tailoring, verifies no skills were added that weren't in the original
- `calculate_match_score()` — produces a 0.0–1.0 score with a breakdown matrix

### core/audit_log.py ✅
Records every step the agent takes in a structured JSON log. Each entry has: timestamp, step name, action taken, reasoning, confidence level, warnings. Saved to `outputs/audit_<session_id>.json`.

---

## 3. Full Architecture

```
job-application-agent/
│
├── core/                          ← Business logic layer
│   ├── config.py                  ✅ Config + env validation
│   ├── logger.py                  ✅ Secure structured logging
│   ├── resume_parser.py           ✅ PDF → ResumeData (Pydantic)
│   ├── jd_analyzer.py             ✅ JD text → JobDescription (Pydantic)
│   ├── validator.py               ✅ Input validation + integrity check + match score
│   ├── audit_log.py               ✅ Full audit trail for every step
│   ├── company_researcher.py      ← TODO: Tavily web search → CompanyProfile
│   ├── resume_tailor.py           ← TODO: Rewrite resume using Groq
│   ├── cover_letter.py            ← TODO: Write cover letter using Claude
│   ├── outreach.py                ← TODO: LinkedIn message using Groq
│   └── output_generator.py       ← TODO: Export to .docx and .txt
│
├── agent/
│   └── orchestrator.py            ← TODO: Main ReAct loop, coordinates all steps
│
├── ui/
│   └── app.py                     ← TODO: Gradio SaaS-looking frontend
│
├── sample_data/                   ← Test resume PDF and JD text
├── outputs/                       ← Generated files (gitignored)
├── logs/                          ← Log files (gitignored)
│
├── .env                           ← API keys (gitignored, never commit)
├── .env.example                   ← Template (safe to commit)
├── .gitignore                     ✅
├── requirements.txt               ← TODO
└── PLAN.md                        ← This file
```

### Data Flow

```
User uploads PDF + pastes JD + types company name
          │
          ▼
    [resume_parser]  ──── raw PDF bytes
          │               PDF → text → Groq LLM → ResumeData (JSON)
          ▼
    [jd_analyzer]   ──── JD text
          │               text → Groq LLM → JobDescription (JSON)
          ▼
    [validator]     ──── ResumeData + JobDescription
          │               → match score + matrix
          │               → vague JD warning (ask clarifying questions)
          ▼
    [company_researcher] ── company name + job title
          │               → Tavily web search (3–5 queries)
          │               → CompanyProfile (culture, tech stack, news)
          ▼
    [resume_tailor]  ──── ResumeData + JobDescription + CompanyProfile
          │               → Groq LLM rewrites resume
          │               → integrity check (no new skills added)
          │               → changelog (what changed and WHY)
          ▼
    [cover_letter]   ──── ResumeData + JobDescription + CompanyProfile
          │               → Claude (Anthropic) writes the cover letter
          │               → human-sounding, not AI-sounding
          ▼
    [outreach]       ──── ResumeData + JobDescription + CompanyProfile
          │               → Groq writes LinkedIn outreach message
          │               → Short, direct, professional
          ▼
    [output_generator] ── all outputs
          │               → tailored_resume.docx
          │               → cover_letter.txt
          │               → outreach_message.txt
          │               → match_report.json
          │               → audit_log.json
          ▼
    Gradio UI displays results + download buttons
```

---

## 4. What Still Needs to Be Built

### core/company_researcher.py
**What it does:** Takes the company name and job title, runs 3–5 Tavily web searches, and returns a structured `CompanyProfile` with:
- Products and services
- Tech stack (languages, frameworks, tools they use)
- Company culture and values
- Recent news (last 6 months)
- Size and stage (startup, enterprise, etc.)

**Why it matters:** This is what makes the cover letter personal. "I'm excited about [specific product]" is infinitely better than "I'm excited about your company."

**Model:**
```python
class CompanyProfile(BaseModel):
    name: str
    products: List[str]
    tech_stack: List[str]
    culture_values: List[str]
    recent_news: List[str]
    company_stage: Optional[str]
    search_queries_used: List[str]
```

### core/resume_tailor.py
**What it does:** The most critical and complex module. Takes the original `ResumeData`, the `JobDescription`, and the `CompanyProfile`, then:
1. Decides which experiences are most relevant to this specific role
2. Reorders bullet points to lead with the most relevant
3. Rewords bullets to use JD language (ATS keyword injection — but ONLY into bullets that already describe that skill)
4. Produces a tailored resume dict AND a changelog explaining each change

**Why the changelog matters:** It shows the recruiter-facing reviewer (or the portfolio reviewer) that the agent is not just making random changes — every change has a reason.

**Output:**
```python
class TailoredResume(BaseModel):
    resume_data: dict           # The modified resume
    changelog: List[ChangeEntry]  # What changed and why
    not_added: List[str]        # JD skills NOT added (proof of integrity)
```

### core/cover_letter.py
**What it does:** Uses Anthropic Claude (not Groq) to write the cover letter. Claude is used here specifically because it produces more natural, less robotic long-form prose than most models.

**Inputs:** ResumeData + JobDescription + CompanyProfile
**Output:** A 3–4 paragraph cover letter that:
- Opens with a hook connected to something specific about the company
- Connects 2–3 specific experiences to the role's requirements
- References company culture/values from the research
- Closes with a clear call to action

### core/outreach.py
**What it does:** Writes a short LinkedIn outreach message (150–250 words). The goal is a message that doesn't sound like a template.

**Pattern:**
- Sentence 1: something specific about their company/work
- Sentence 2–3: quick self-intro relevant to them
- Sentence 4: the ask (conversation, not a job)

### core/output_generator.py
**What it does:** Takes all generated content and exports it to files:
- `tailored_resume.docx` — formatted Word document with proper headings
- `cover_letter.txt` — plain text
- `outreach_message.txt` — plain text
- `match_report.json` — the full match matrix with scores
- `audit_log.json` — already handled by audit_log.py

Uses `python-docx` for the Word document.

### agent/orchestrator.py
**What it does:** The main coordinator. This is the "brain" — it runs all steps in order, handles errors gracefully, updates the audit log, and returns the final result package.

It also handles:
- Clarifying questions when the JD is vague
- Weak match warnings when score < 0.6 (the user still gets output, but with warnings)
- Retry logic if an LLM call fails

### ui/app.py
**What it does:** The Gradio frontend. Designed to look like a real SaaS product, not a demo. See [UI Design Spec](#12-ui-design-spec).

### .env.example
Template showing which keys are needed, without actual values.

### requirements.txt
All Python dependencies with pinned versions.

---

## 5. Build Order — Step by Step

Build in this exact order. Each step is a working increment.

```
Phase 1 — Foundation (DONE)
  [✅] core/config.py
  [✅] core/logger.py
  [✅] core/resume_parser.py
  [✅] core/jd_analyzer.py
  [✅] core/validator.py
  [✅] core/audit_log.py

Phase 2 — Remaining Core Modules
  [✅] core/company_researcher.py
  [✅] core/resume_tailor.py        (with confidence scoring per change)
  [✅] core/cover_letter.py         (Groq, temperature=0.4 for natural prose)
  [✅] core/outreach.py
  [✅] core/output_generator.py

Phase 3 — Orchestration
  [✅] agent/orchestrator.py    (generator-based, yields ProgressUpdate per step)

Phase 4 — UI
  [✅] ui/app.py                (Gradio Blocks, real-time progress, tabs, confidence badges)
  [✅] app.py                   (root entry point for Hugging Face Spaces)

Phase 5 — Packaging
  [✅] requirements.txt
  [✅] .env.example
  [ ] sample_data/ (test resume + JD)

Phase 6 — Deployment
  [ ] Hugging Face Spaces setup
  [ ] README.md (for HF + GitHub)
```

---

## 6. Tech Decisions Explained

### Why Groq instead of OpenAI for the main LLM?
Groq offers a free tier (up to a generous daily limit) with extremely fast inference. For a portfolio project, this means you can test hundreds of times without any cost. The model we use (`llama-3.1-70b-versatile`) is comparable to GPT-4o-mini for structured extraction tasks. The tradeoff is that Groq's free tier has rate limits — for production this would be a concern, but not for a portfolio project.

### Why Groq for cover letters instead of Claude?
We use Groq for all LLM calls (Groq + Tavily are the only APIs required). The cover letter uses a **higher temperature (0.4)** compared to all other calls (0.1), which makes the output more varied and natural-sounding. A carefully crafted prose-focused prompt compensates for not having a separate model — the key insight is that temperature and prompt design matter more than the model choice for this task.

### Why Pydantic models everywhere?
Pydantic validates data at runtime. If the LLM returns malformed JSON or the wrong structure, Pydantic catches it immediately with a clear error rather than a cryptic KeyError deep in your code. It also gives you type safety and auto-documentation for free.

### Why a custom orchestrator instead of LangChain's AgentExecutor?
LangChain is powerful but adds a lot of abstraction. Building the orchestrator from scratch means:
1. You understand every line of what the agent does
2. Easier to debug when something goes wrong
3. Better for a portfolio — shows you understand the pattern, not just the library
4. More control over error handling and audit logging

### Why Tavily for search?
Tavily is purpose-built for AI agents. It returns clean, structured results rather than raw HTML. It also has a generous free tier (1,000 searches/month). Alternatives like SerpAPI or DuckDuckGo require more parsing work.

### Why Gradio for the UI?
Gradio is natively supported by Hugging Face Spaces — zero configuration needed for deployment. It also looks professional when themed properly. The tradeoff vs. a React/Next.js frontend is less control over design, but for a portfolio deployment this is the right tradeoff.

---

## 7. The Agent Pattern — How It Works

### ReAct Loop (Reason + Act)

The agent doesn't blindly execute steps. It reasons before each action:

```
THOUGHT: I need to understand what skills this company values most before tailoring the resume.
ACTION: search_company("Stripe", "engineering culture tech stack")
OBSERVATION: Stripe uses Go, Ruby, TypeScript. Heavy emphasis on distributed systems.
THOUGHT: The candidate has distributed systems experience. I should emphasize that in the resume.
ACTION: tailor_resume(emphasize=["distributed systems", "Go"])
...
```

This is what makes it an agent. The thought-action-observation cycle continues until the agent has everything it needs.

### Error Handling Pattern

Every step can fail. The orchestrator handles this gracefully:
- LLM call fails → retry up to `MAX_RETRIES` times with exponential backoff
- Company research fails → continue without company data, note in audit log
- Integrity check fails → reject the tailored resume, log violation, regenerate
- Match score < 0.6 → warn user but still produce output

---

## 8. Project Rules — Non-Negotiable

These rules are enforced in code, not just guidelines:

| Rule | Where Enforced |
|------|---------------|
| No adding skills not in original resume | `validator.check_integrity()` |
| No adding experience not in original | `validator.check_integrity()` |
| Resume is parsed to JSON first, writing comes later | Architecture (parse → analyze → write) |
| Every change must have a reason | `TailoredResume.changelog` |
| Show what was NOT added (proof of integrity) | `IntegrityReport.not_added` |
| Vague JD triggers clarifying questions | `jd_analyzer.is_vague` flag |
| Weak match (<60%) triggers warning | `validator.calculate_match_score()` |
| All LLM calls logged in audit trail | `audit_log.py` |
| API keys never in code | `config.py` uses `os.getenv()` |

### One rule to add (recommendation)
Consider adding **confidence scoring per change** in the changelog. For each bullet rewritten, the agent notes how confident it is that the change is appropriate (high/medium/low). Low confidence changes are flagged for user review. This is the kind of detail that impresses technical reviewers.

---

## 9. API Keys and Security

### What keys you need

Create a `.env` file in the project root (it's already in `.gitignore`):

```
GROQ_API_KEY=gsk_your_key_here
TAVILY_API_KEY=tvly-your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

### Where to get them
- **Groq:** https://console.groq.com — free, no credit card required
- **Tavily:** https://tavily.com — free tier, 1,000 searches/month
- **Anthropic:** https://console.anthropic.com — requires payment, but cover letter uses ~2K tokens per run (~$0.018/run)

### Spending limits (do this before adding credits)
- OpenAI: Dashboard → Settings → Limits → set a hard limit
- Anthropic: Console → Settings → Usage limits

### For Hugging Face deployment
HF Spaces has "Secrets" — environment variables that are encrypted and injected at runtime. You add your keys there, not in code.

---

## 10. Cost Estimate

| Component | Provider | Cost per run | 50 runs |
|-----------|----------|-------------|---------|
| Resume parsing | Groq (free) | $0 | $0 |
| JD analysis | Groq (free) | $0 | $0 |
| Company research | Tavily (free tier) | $0 | $0 |
| Resume tailoring | Groq (free) | $0 | $0 |
| Cover letter | Groq (free) | $0 | $0 |
| LinkedIn outreach | Groq (free) | $0 | $0 |
| **Total** | | **$0** | **$0** |

**Stack: Groq + Tavily only. No Anthropic API required.**
Groq free tier: ~14,400 requests/day. You will not hit this.
Tavily free tier: 1,000 searches/month. 4 searches per run = ~250 runs before hitting limit.

---

## 11. Deployment Guide — Hugging Face Spaces

### Why Hugging Face Spaces?
- Free hosting for Gradio apps
- No server management
- Built-in GPU support if you need it (we don't)
- Public URL that looks professional: `https://huggingface.co/spaces/your-username/job-application-agent`

### Deployment steps (do this last, after everything works locally)

1. Create a free account at huggingface.co
2. Create a new Space: New → Space → Gradio → Public
3. The Space is a Git repo — clone it locally
4. Copy your project files into the Space repo (exclude `.env`, `venv/`, `outputs/`)
5. Add a `requirements.txt` at the root
6. Add your API keys as Secrets: Space Settings → Secrets → Add Secret
7. The main file must be named `app.py` at the root (or configure in Space settings)
8. Commit and push — HF automatically builds and deploys

### Required files for HF deployment

```
app.py              ← Gradio app (must be at root or configured)
requirements.txt    ← Dependencies
core/               ← All core modules
agent/              ← Orchestrator
```

### The key constraint
Hugging Face Spaces are stateless — each request starts fresh. This is fine for our use case since we generate everything in one run and return it to the user immediately.

---

## 12. UI Design Spec

The goal is "internal HR tool" feel — professional, functional, not a toy.

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  [Logo] Job Application Assistant        [Status: Ready] │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  INPUTS                          PROGRESS               │
│  ┌─────────────────────┐        ┌────────────────────┐  │
│  │ Upload Resume PDF   │        │ ○ Parse Resume     │  │
│  │ [Drop or click]     │        │ ○ Analyze JD       │  │
│  └─────────────────────┘        │ ○ Research Company │  │
│                                  │ ○ Calculate Match  │  │
│  ┌─────────────────────┐        │ ○ Tailor Resume    │  │
│  │ Job Description     │        │ ○ Write Cover Ltr  │  │
│  │ [Paste text here]   │        │ ○ Write Outreach   │  │
│  └─────────────────────┘        └────────────────────┘  │
│                                                          │
│  Company Name: [____________]                            │
│                                                          │
│              [Generate Application Package]              │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  RESULTS                                                 │
│  ┌──────────┬───────────┬──────────┬────────────────┐   │
│  │ Match    │ Tailored  │ Cover    │ LinkedIn       │   │
│  │ Report   │ Resume    │ Letter   │ Outreach       │   │
│  └──────────┴───────────┴──────────┴────────────────┘   │
│                                                          │
│  Match Score: 78% (Strong)  ████████░░                   │
│                                                          │
│  ✓ Matched: Python, FastAPI, PostgreSQL                  │
│  ✗ Missing: Kubernetes (not added — not in your resume)  │
│                                                          │
│  Changelog:                                              │
│  • Moved "built scalable APIs" bullet to top (ATS match) │
│  • Reworded "worked on databases" → "designed PostgreSQL  │
│    schemas" (JD uses "schema design")                    │
│                                                          │
│  [↓ Download Resume.docx] [↓ Download Cover Letter]      │
└─────────────────────────────────────────────────────────┘
```

### Key UI components
- **Progress tracker** — real-time step indicators (shows the agent working)
- **Match score bar** — visual 0–100% with color coding (red/yellow/green)
- **Changelog panel** — every change explained
- **"Not Added" section** — shows JD skills NOT injected, proving integrity
- **Download buttons** — one click to get the files
- **Tabs for outputs** — switch between resume, cover letter, outreach

---

## 13. Testing Plan

### Manual testing order
1. Test each core module in isolation with a sample resume PDF and JD text
2. Test the orchestrator with a real job posting
3. Test edge cases: vague JD, weak match, scanned PDF (should fail gracefully)
4. Test UI end-to-end locally before deploying

### Edge cases to test
| Case | Expected behavior |
|------|-------------------|
| Scanned PDF (image, no text) | Clear error: "Please use a text-based PDF" |
| Vague JD (no specific skills) | Warning + clarifying questions displayed |
| Weak match (<60%) | Warning shown, output still generated |
| Company not found by search | Continue without company data, note in output |
| LLM API down | Retry 3 times, then clear error message |
| Integrity violation (LLM adds skill) | Auto-reject, regenerate, log violation |

---

*This plan is a living document. Update it as decisions change.*
