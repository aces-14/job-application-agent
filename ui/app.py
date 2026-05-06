"""
ui/app.py — Gradio frontend for the Job Application Assistant.

Layout:
- Two-column: left = inputs, right = progress + results tabs (side by side)
- Progress tracker is hidden until pipeline starts, hidden again on success
- Results tab fills the right column — user sees output immediately
"""

import gradio as gr

from agent.orchestrator import PIPELINE_STEPS, run_streaming

# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
/* ── Header ───────────────────────────────────────────────── */
.app-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    padding: 28px 36px;
    border-radius: 12px;
    margin-bottom: 20px;
    text-align: center;
}
.app-title {
    color: #f8fafc;
    font-size: 26px;
    font-weight: 700;
    margin: 0 0 6px 0;
    letter-spacing: -0.5px;
}
.app-subtitle {
    color: #94a3b8;
    font-size: 13px;
    margin: 0 0 12px 0;
}
.app-pills {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: center;
}
.pill {
    background: rgba(255,255,255,0.1);
    color: #cbd5e1;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.15);
}

/* ── Progress tracker ─────────────────────────────────────── */
.progress-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 18px 20px;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13.5px;
    margin-bottom: 12px;
}
.progress-title {
    font-weight: 700;
    color: #0f172a;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid #e2e8f0;
}
.step-row { padding: 5px 0; display: flex; align-items: center; gap: 10px; }
.step-pending  { color: #94a3b8; }
.step-running  { color: #2563eb; font-weight: 600; }
.step-done     { color: #16a34a; font-weight: 600; }
.step-error    { color: #dc2626; font-weight: 600; }
.step-icon     { font-size: 15px; width: 18px; text-align: center; }

/* ── Match score ──────────────────────────────────────────── */
.score-card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 12px;
}
.score-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}
.score-label { font-weight: 700; color: #0f172a; font-size: 14px; }
.score-value { font-size: 20px; font-weight: 800; }
.score-bar-bg {
    background: #e2e8f0;
    border-radius: 6px;
    height: 10px;
    margin-bottom: 16px;
}
.score-bar-fill { height: 10px; border-radius: 6px; }
.skill-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    font-size: 13px;
}
.skill-box { background: #f8fafc; border-radius: 8px; padding: 12px 14px; }
.skill-box-title { font-weight: 700; margin-bottom: 6px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.3px; }
.skill-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    margin: 2px;
    font-size: 12px;
}
.tag-matched  { background: #dcfce7; color: #15803d; }
.tag-missing  { background: #fee2e2; color: #b91c1c; }
.tag-notadded { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

/* ── Changelog ────────────────────────────────────────────── */
.changelog-card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 20px 24px;
}
.changelog-title {
    font-weight: 700;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #0f172a;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid #e2e8f0;
}
.change-entry {
    border-left: 3px solid #e2e8f0;
    padding: 10px 14px;
    margin-bottom: 10px;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
}
.change-high   { border-left-color: #16a34a; background: #f0fdf4; }
.change-medium { border-left-color: #d97706; background: #fffbeb; }
.change-low    { border-left-color: #dc2626; background: #fef2f2; }
.change-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.change-section { font-weight: 600; color: #0f172a; font-size: 12px; text-transform: uppercase; }
.badge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 3px;
    text-transform: uppercase;
    white-space: nowrap;
}
.badge-high   { background: #dcfce7; color: #14532d; }
.badge-medium { background: #fef9c3; color: #713f12; }
.badge-low    { background: #fee2e2; color: #7f1d1d; }
.change-original { color: #6b7280; font-size: 12px; margin-bottom: 3px; }
.change-revised  { color: #0f172a; font-size: 12.5px; margin-bottom: 4px; font-weight: 500; }
.change-reason   { color: #475569; font-size: 11.5px; font-style: italic; }
.ats-tags        { margin-top: 4px; }
.ats-tag { background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 3px; font-size: 11px; margin: 1px; display: inline-block; }

/* ── Warnings ─────────────────────────────────────────────── */
.warning-card {
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 12px;
    font-size: 13px;
}
.warning-title { font-weight: 700; color: #92400e; margin-bottom: 8px; font-size: 12px; text-transform: uppercase; }
.warning-item { color: #78350f; padding: 3px 0; }

/* ── Error ────────────────────────────────────────────────── */
.error-card {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    padding: 16px 20px;
    font-size: 13.5px;
    color: #7f1d1d;
    margin-bottom: 12px;
}
.error-title { font-weight: 700; margin-bottom: 6px; font-size: 14px; }

/* ── Generate button ──────────────────────────────────────── */
#generate-btn {
    background: #1e3a5f !important;
    border: none !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    padding: 14px !important;
    border-radius: 8px !important;
}
#generate-btn:hover { background: #2563eb !important; }
"""

# ── HTML render helpers ───────────────────────────────────────────────────────

_STEP_LABEL = {k: label for k, label in PIPELINE_STEPS}


def _progress_html(
    completed: list[str],
    current: str,
    error: bool = False,
) -> str:
    rows = []
    for key, label in PIPELINE_STEPS:
        if error and key == current:
            icon, cls = "✗", "step-error"
        elif key in completed:
            icon, cls = "✓", "step-done"
        elif key == current:
            icon, cls = "⟳", "step-running"
        else:
            icon, cls = "○", "step-pending"

        rows.append(
            f'<div class="step-row {cls}">'
            f'<span class="step-icon">{icon}</span>'
            f'<span>{label}</span>'
            f'</div>'
        )

    return (
        '<div class="progress-card">'
        '<div class="progress-title">Pipeline Progress</div>'
        + "".join(rows)
        + "</div>"
    )


def _score_html(match_matrix: dict, warnings: list[str]) -> str:
    score_pct = int(match_matrix["overall_score"] * 100)
    level = match_matrix["match_level"]
    color = (
        "#16a34a" if level == "Strong"
        else "#d97706" if level == "Moderate"
        else "#dc2626"
    )

    def _tags(skills: list[str], css_class: str) -> str:
        if not skills:
            return '<span style="color:#94a3b8;font-size:12px;">None</span>'
        return "".join(
            f'<span class="skill-tag {css_class}">{s}</span>'
            for s in sorted(skills)
        )

    warnings_html = ""
    if warnings:
        items = "".join(f'<div class="warning-item">• {w}</div>' for w in warnings)
        warnings_html = (
            f'<div class="warning-card">'
            f'<div class="warning-title">⚠ Warnings</div>'
            f"{items}</div>"
        )

    return f"""
{warnings_html}
<div class="score-card">
    <div class="score-header">
        <span class="score-label">Resume–JD Match Score</span>
        <span class="score-value" style="color:{color};">{score_pct}% — {level}</span>
    </div>
    <div class="score-bar-bg">
        <div class="score-bar-fill" style="background:{color};width:{score_pct}%;"></div>
    </div>
    <div class="skill-grid">
        <div class="skill-box">
            <div class="skill-box-title" style="color:#15803d;">✓ Matched Required</div>
            {_tags(match_matrix.get("matched_required", []), "tag-matched")}
        </div>
        <div class="skill-box">
            <div class="skill-box-title" style="color:#b91c1c;">✗ Missing Required</div>
            {_tags(match_matrix.get("missing_required", []), "tag-missing")}
        </div>
        <div class="skill-box">
            <div class="skill-box-title" style="color:#15803d;">✓ Matched Preferred</div>
            {_tags(match_matrix.get("matched_preferred", []), "tag-matched")}
        </div>
        <div class="skill-box">
            <div class="skill-box-title" style="color:#475569;">— Not Added (not in resume)</div>
            {_tags(match_matrix.get("missing_preferred", []), "tag-notadded")}
        </div>
    </div>
</div>
"""


def _changelog_html(tailored) -> str:
    changelog = tailored.changelog
    not_added = tailored.not_added

    if not changelog:
        return '<div class="changelog-card"><div class="changelog-title">Resume Changes</div><p style="color:#94a3b8;font-size:13px;">No changes recorded.</p></div>'

    confidence_counts = {
        "high":   sum(1 for c in changelog if c.confidence == "high"),
        "medium": sum(1 for c in changelog if c.confidence == "medium"),
        "low":    sum(1 for c in changelog if c.confidence == "low"),
    }
    summary = (
        f'<div style="font-size:12px;color:#475569;margin-bottom:14px;">'
        f'{len(changelog)} changes — '
        f'<span style="color:#15803d;">●</span> {confidence_counts["high"]} high &nbsp;'
        f'<span style="color:#d97706;">●</span> {confidence_counts["medium"]} medium &nbsp;'
        f'<span style="color:#dc2626;">●</span> {confidence_counts["low"]} low confidence'
        f'</div>'
    )

    entries = []
    for c in changelog:
        badge_cls = f"badge-{c.confidence}"
        entry_cls = f"change-{c.confidence}"
        badge_label = {
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW — Review",
        }[c.confidence]

        ats_html = ""
        if c.ats_keywords_added:
            tags = "".join(f'<span class="ats-tag">{k}</span>' for k in c.ats_keywords_added)
            ats_html = f'<div class="ats-tags">ATS injected: {tags}</div>'

        entries.append(f"""
<div class="change-entry {entry_cls}">
    <div class="change-header">
        <span class="change-section">{c.section} · {c.change_type}</span>
        <span class="badge {badge_cls}">{badge_label}</span>
    </div>
    <div class="change-original">Before: {c.original}</div>
    <div class="change-revised">After: {c.revised}</div>
    <div class="change-reason">Why: {c.reason}</div>
    <div class="change-reason" style="color:#94a3b8;">Confidence note: {c.confidence_reason}</div>
    {ats_html}
</div>""")

    not_added_html = ""
    if not_added:
        tags = "".join(f'<span class="skill-tag tag-notadded">{s}</span>' for s in not_added)
        not_added_html = f"""
<div style="margin-top:16px;padding-top:14px;border-top:1px solid #e2e8f0;">
    <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#475569;margin-bottom:6px;">
        JD Skills NOT Added (not in original resume)
    </div>
    <div style="font-size:12px;color:#64748b;margin-bottom:8px;">
        These were required/preferred by the JD but do not exist in your resume —
        they were intentionally excluded to preserve integrity.
    </div>
    {tags}
</div>"""

    return (
        '<div class="changelog-card">'
        '<div class="changelog-title">Resume Changes</div>'
        + summary
        + "".join(entries)
        + not_added_html
        + "</div>"
    )


def _error_html(message: str) -> str:
    return (
        f'<div class="error-card">'
        f'<div class="error-title">Something went wrong</div>'
        f"{message}"
        f"</div>"
    )


# ── Header HTML ───────────────────────────────────────────────────────────────

HEADER_HTML = """
<div class="app-header">
    <div class="app-title">Job Application Assistant</div>
    <div class="app-subtitle">AI-powered resume tailoring, cover letter &amp; LinkedIn outreach — in one click</div>
    <div class="app-pills">
        <span class="pill">Groq LLM</span>
        <span class="pill">Tavily Web Search</span>
        <span class="pill">ATS Optimization</span>
        <span class="pill">Integrity Enforced</span>
        <span class="pill">Fully Auditable</span>
    </div>
</div>
"""

# ── Main generator function ───────────────────────────────────────────────────

def generate(resume_path: str, jd_text: str, company_name: str):
    """
    Gradio generator — yields 8-value tuples matching the outputs list.
    Progress display appears during the run and clears on success.
    On error it stays visible showing the error card.
    """
    if resume_path is None:
        yield (
            _error_html("Please upload a resume PDF before generating."),
            "", "", "", None, "", None, None,
        )
        return

    if not jd_text or not jd_text.strip():
        yield (
            _error_html("Please paste a job description before generating."),
            "", "", "", None, "", None, None,
        )
        return

    try:
        with open(resume_path, "rb") as f:
            resume_bytes = f.read()
    except Exception as e:
        yield (
            _error_html(f"Could not read the uploaded file: {e}"),
            "", "", "", None, "", None, None,
        )
        return

    for update in run_streaming(resume_bytes, jd_text.strip(), company_name.strip()):

        if update.status == "error":
            yield (
                _error_html(update.error_message),
                "", "", "", None, "", None, None,
            )
            return

        if update.package is None:
            yield (
                _progress_html(update.completed, update.current_step),
                "", "", "", None, "", None, None,
            )

        else:
            pkg = update.package
            yield (
                "",  # clear progress tracker — results are now visible
                _score_html(pkg.match_matrix, pkg.warnings),
                _changelog_html(pkg.tailored_resume),
                pkg.cover_letter,
                pkg.cover_letter_path,
                pkg.outreach_message,
                pkg.outreach_path,
                pkg.resume_docx_path,
            )


# ── Build the Gradio app ──────────────────────────────────────────────────────

def build_app() -> gr.Blocks:
    with gr.Blocks(
        theme=gr.themes.Soft(
            primary_hue="blue",
            neutral_hue="slate",
            font=gr.themes.GoogleFont("Inter"),
        ),
        css=CSS,
        title="Job Application Assistant",
    ) as app:

        gr.HTML(HEADER_HTML)

        with gr.Row(equal_height=False):

            # Left column — inputs
            with gr.Column(scale=2):
                resume_upload = gr.File(
                    label="Resume (.docx)",
                    file_types=[".docx"],
                    type="filepath",
                )
                jd_input = gr.Textbox(
                    label="Job Description",
                    placeholder="Paste the full job description here...",
                    lines=12,
                    max_lines=30,
                )
                company_input = gr.Textbox(
                    label="Company Name",
                    placeholder="e.g. Stripe, Airbnb, OpenAI (optional but recommended)",
                    lines=1,
                )
                generate_btn = gr.Button(
                    "Generate Application Package",
                    variant="primary",
                    size="lg",
                    elem_id="generate-btn",
                )

            # Right column — progress (while running) + results tabs
            with gr.Column(scale=3):
                progress_display = gr.HTML(value="")

                with gr.Tabs():

                    with gr.Tab("Match Report"):
                        score_display = gr.HTML(label="")

                    with gr.Tab("Tailored Resume"):
                        changelog_display = gr.HTML(label="")
                        resume_download = gr.File(
                            label="Download Tailored Resume (.docx)",
                            interactive=False,
                        )

                    with gr.Tab("Cover Letter"):
                        cover_letter_display = gr.Textbox(
                            label="Cover Letter",
                            lines=18,
                            interactive=False,
                        )
                        cover_letter_download = gr.File(
                            label="Download Cover Letter (.txt)",
                            interactive=False,
                        )

                    with gr.Tab("LinkedIn Outreach"):
                        outreach_display = gr.Textbox(
                            label="LinkedIn Message",
                            lines=8,
                            interactive=False,
                        )
                        outreach_download = gr.File(
                            label="Download Outreach Message (.txt)",
                            interactive=False,
                        )

        generate_btn.click(
            fn=generate,
            inputs=[resume_upload, jd_input, company_input],
            outputs=[
                progress_display,
                score_display,
                changelog_display,
                cover_letter_display,
                cover_letter_download,
                outreach_display,
                outreach_download,
                resume_download,
            ],
        )

    return app


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
