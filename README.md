---
title: Job Application Assistant
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: mit
---

# Job Application Assistant Agent

An AI agent that takes your resume PDF, a job description, and a company name, then produces a complete tailored application package in under 30 seconds.

## What it produces

| Output | Description |
|--------|-------------|
| **Tailored Resume** | Rewritten for ATS keywords and role relevance — never fabricates skills |
| **Cover Letter** | Personalized to the company using real web research |
| **LinkedIn Outreach** | Short, specific connection message — not a template |
| **Match Report** | Skills gap analysis with a 0–100% match score |
| **Changelog** | Every change explained, with confidence scores (high / medium / low) |

## How it works

The agent runs a 9-step pipeline:

1. **Parse Resume** — DOCX → structured JSON (single source of truth)
2. **Analyze JD** — Extracts required skills, ATS keywords, vagueness flags
3. **Validate** — Checks inputs, warns if JD is too vague
4. **Match Score** — Weighted resume–JD skills matrix (0–100%)
5. **Research Company** — 4 Tavily web searches → company profile
6. **Tailor Resume** — Rewords and reorders bullets using JD language
7. **Write Cover Letter** — Hook-first, company-specific, 250–350 words
8. **Write Outreach** — 80–120 word LinkedIn message
9. **Export Files** — `.docx` resume, `.txt` cover letter and outreach

## Resume integrity rules (non-negotiable)

- Skills not in the original resume are **never added**
- Work experience is **never fabricated**
- Every change has a documented reason and confidence score
- A "Not Added" section shows which JD skills were intentionally excluded

## Tech stack

| Component | Tool | Why |
|-----------|------|-----|
| LLM (all steps) | Groq `llama-3.3-70b-versatile` | Fast, free-tier, accurate |
| Web search | Tavily API | Purpose-built for AI agents |
| Resume input/output | python-docx | Reads and writes native Word format |
| Frontend | Gradio | Native HF Spaces support |

## Running locally

```bash
# 1. Clone the repo
git clone https://github.com/aces-14/job-application-agent
cd job-application-agent

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
# Create a .env file with your API keys:
# GROQ_API_KEY=your_key_here
# TAVILY_API_KEY=your_key_here

# 5. Run smoke tests
python test_pipeline.py

# 6. Launch the UI
python app.py
# Open http://localhost:7860
```

## API keys needed

| Key | Where to get | Cost |
|-----|-------------|------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Free tier |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) | Free (1,000 searches/month) |

## Cost per run

Approximately **$0** — both APIs are used within their free tiers.
Each run uses ~6 Groq calls and ~4 Tavily searches.

---

Built as a portfolio project demonstrating: LLM agent design, multi-step pipeline orchestration, ATS optimization, and resume integrity enforcement.
