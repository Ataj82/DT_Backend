"""Safe downloadable report renderers.

Exporters are presentation-only. They never alter assessment state.
v12.6.3 adds richer role-scoped reporting content: mastery, coverage,
Bloom level, difficulty, evidence strength, conversation, and selected
assessment diagnostics already produced by the canonical assessment layer.
"""
from __future__ import annotations

import html
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def report_to_dict(report) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(report), default=_json_default))


def render_json(report) -> bytes:
    return json.dumps(report_to_dict(report), indent=2, ensure_ascii=False).encode("utf-8")


def _fmt(v, digits=3):
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _pct(v):
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _conversation_rows(conversation):
    rows = []
    for item in conversation or []:
        ev = item.get("evaluation") or {}
        trace = item.get("adaptive_decision_trace") or {}
        continuity = item.get("question_continuity") or {}
        trace_reason = trace.get("decision_reason") or trace.get("selection_source") or trace.get("reason") or ""
        continuity_status = continuity.get("status") or continuity.get("decision") or ""
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('turn_number', '')))}</td>"
            f"<td>{html.escape(str(item.get('goal_id', '') or ''))}</td>"
            f"<td>{html.escape(str(item.get('indicator_id', '') or ''))}</td>"
            f"<td>{html.escape(str(item.get('question', '') or ''))}</td>"
            f"<td>{html.escape(str(item.get('answer', '') or ''))}</td>"
            f"<td>{html.escape(str(ev.get('achievement_level', '—')))}</td>"
            f"<td>{_pct(ev.get('confidence'))}</td>"
            f"<td>{_pct(ev.get('evidence_strength'))}</td>"
            f"<td>{html.escape(str(ev.get('bloom_level', '') or '—'))}</td>"
            f"<td>{html.escape(str(ev.get('difficulty_after', '') or '—'))}</td>"
            f"<td>{html.escape(str(trace_reason))}</td>"
            f"<td>{html.escape(str(continuity_status))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _report_body(data: dict[str, Any]) -> str:
    metrics = data.get("metrics") or {}
    goals = metrics.get("goal_metrics") or []
    indicators = metrics.get("indicator_metrics") or []
    metadata = data.get("metadata") or {}
    conversation = metadata.get("conversation") or []
    # v12.6.4: AssessmentResultBuilder stores these additive diagnostics
    # directly in result.metadata. Keep compatibility with older nested reports.
    assessment_meta = metadata.get("assessment_metadata") or metadata
    integrity = assessment_meta.get("assessment_integrity") or {}
    fairness = assessment_meta.get("fairness_calibration") or {}
    rubric = assessment_meta.get("rubric_calibration") or {}
    abet = assessment_meta.get("abet_traceability") or {}

    goal_rows = "".join(
        f"<tr><td>{html.escape(str(g.get('goal_id', '')))}</td>"
        f"<td>{html.escape(str(g.get('title', '')))}</td>"
        f"<td>{_fmt(g.get('mastery', g.get('score', 0)))}</td>"
        f"<td>{_pct(g.get('coverage'))}</td>"
        f"<td>{_pct(g.get('confidence'))}</td>"
        f"<td>{'Yes' if g.get('completed') else 'No'}</td>"
        f"<td>{_fmt(g.get('time_budget_seconds'),1)}s</td>"
        f"<td>{_fmt(g.get('time_elapsed_seconds'),1)}s</td>"
        f"<td>{_fmt(g.get('time_remaining_seconds'),1)}s</td></tr>"
        for g in goals
    )
    indicator_rows = "".join(
        f"<tr><td>{html.escape(str(i.get('indicator_id', '')))}</td>"
        f"<td>{html.escape(str(i.get('description', '')))}</td>"
        f"<td>{html.escape(str(i.get('bloom_level', '') or '—'))}</td>"
        f"<td>{html.escape(str(i.get('achievement_level', i.get('achieved_level', '—'))))}</td>"
        f"<td>{_pct(i.get('mastery'))}</td>"
        f"<td>{_pct(i.get('confidence'))}</td>"
        f"<td>{_pct(i.get('evidence_strength'))}</td>"
        f"<td>{html.escape(str(i.get('required', False)))}</td>"
        f"<td>{html.escape(str(i.get('feedback', '') or '—'))}</td>"
        f"<td>{int(i.get('attempts', 0))}</td>"
        f"<td>{'Yes' if i.get('demonstrated') else 'No'}</td></tr>"
        for i in indicators
    )
    conversation_rows = _conversation_rows(conversation)
    title = f"Interview Assessment Report — {data.get('session_id', '')}"
    integrity_status = integrity.get("root_hash") or "Not available"
    diagnostic_summary = (
        f"Fairness diagnostics: {len(fairness.get('goals') or {})} goal(s) · "
        f"Rubric calibration: {len(rubric.get('goals') or [])} goal(s) · "
        f"ABET traceability: {'available' if abet else 'not available'}"
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;line-height:1.4;color:#222}}
table{{border-collapse:collapse;width:100%;margin:14px 0 24px;table-layout:auto}}
th,td{{border:1px solid #ccc;padding:7px;text-align:left;vertical-align:top}}
th{{background:#f3f3f3}}
.small{{font-size:12px;color:#555}} .score{{font-size:24px;font-weight:bold}}
.wrap{{word-break:break-word;white-space:pre-wrap}} .section{{page-break-inside:avoid}}
</style></head><body>
<h1>Interview Assessment Report</h1>
<p><b>Session:</b> {html.escape(str(data.get('session_id','')))}<br><b>Student:</b> {html.escape(str(data.get('student_id','')))}<br><b>Completed:</b> {'Yes' if metrics.get('completed') else 'No'}</p>
<p class='score'>Overall mastery: {_pct(metrics.get('overall_score'))}</p>
<p>Overall coverage: {_pct(metrics.get('overall_coverage'))} &nbsp; | &nbsp; Overall confidence: {_pct(metrics.get('overall_confidence'))} &nbsp; | &nbsp; Questions: {int(metrics.get('total_questions',0))}</p>
<div class='section'><h2>Goals — mastery, coverage, confidence and timing</h2>
<table><tr><th>ID</th><th>Goal</th><th>Mastery</th><th>Coverage</th><th>Confidence</th><th>Completed</th><th>Budget</th><th>Used</th><th>Remaining</th></tr>{goal_rows}</table></div>
<div class='section'><h2>Indicators — Bloom level and evidence</h2>
<table><tr><th>ID</th><th>Indicator</th><th>Bloom</th><th>Achievement</th><th>Mastery</th><th>Confidence</th><th>Evidence strength</th><th>Attempts</th><th>Demonstrated</th><th>Required</th><th>Feedback</th></tr>{indicator_rows}</table></div>
<div class='section'><h2>Interview conversation</h2>
<table><tr><th>Turn</th><th>Goal</th><th>Indicator</th><th>Question</th><th>Student answer</th><th>Achievement</th><th>Confidence</th><th>Evidence</th><th>Bloom</th><th>Difficulty after</th><th>Adaptive reason</th><th>Continuity</th></tr>{conversation_rows}</table></div>
<div class='section'><h2>Assessment diagnostics</h2><p>{html.escape(diagnostic_summary)}</p><p class='small'>Integrity root: {html.escape(str(integrity_status))}</p></div>
<p class='small'>Generated from the canonical assessment result. Reporting/export layers do not modify assessment state.</p>
</body></html>"""


def render_html(report) -> bytes:
    return _report_body(report_to_dict(report)).encode("utf-8")


def _report_language(data: dict[str, Any]) -> str:
    """Resolve report presentation language without changing assessment state."""
    metadata = data.get("metadata") or {}
    assessment_metadata = metadata.get("assessment_metadata") or {}

    candidates = (
        assessment_metadata.get("language"),
        metadata.get("language"),
        (metadata.get("configuration") or {}).get("language")
        if isinstance(metadata.get("configuration"), dict)
        else getattr(metadata.get("configuration"), "language", None),
    )

    for value in candidates:
        if value is None:
            continue
        raw = getattr(value, "value", value)
        normalized = str(raw).strip().casefold()
        if normalized in {"fa", "persian", "farsi", "interviewlanguage.persian"}:
            return "fa"
        if normalized in {"en", "english", "interviewlanguage.english"}:
            return "en"

    return "en"


def render_pdf(report) -> bytes:
    raise ValueError(
        "PDF export is not supported on the backend. "
        "Exam reports are served as structured JSON for frontend rendering."
    )

