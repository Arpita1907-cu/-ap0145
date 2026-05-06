"""
PsycheNova AI — Premium personality prediction & analysis (Streamlit).
Python + Streamlit only; modular design with questions, scoring, results, chart, PDF.
"""

from __future__ import annotations

import io
import os
import random
import time
from pathlib import Path

# Non-interactive backend for Streamlit / headless (radar chart export)
os.environ.setdefault("MPLBACKEND", "Agg")
from dataclasses import dataclass
from typing import Any

# Brain Buzz / PsycheNova logo (same folder as app.py — shareable with the project)
_LOGO_NAME = "c3279092-b906-45b5-bdfe-1f6d7b8e03a0.jpeg"


def resolve_logo_path() -> Path | None:
    """Streamlit uses the logo next to app.py only. (web/ may hold a duplicate for web/index.html + file://.)"""
    p = Path(__file__).resolve().parent / _LOGO_NAME
    return p if p.is_file() else None


def _safe_logo_image(path: Path, width: int) -> None:
    """Show logo; avoid crashing the app if the image cannot load."""
    try:
        st.image(str(path), width=width)
    except Exception:
        st.warning(f"Could not load logo ({path.name}). Place it next to app.py.")

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from streamlit.errors import StreamlitAPIException
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ---------------------------------------------------------------------------
# Constants & type profiles (normalized 0–1 targets for classification)
# ---------------------------------------------------------------------------

PERSONALITY_TYPES = ("Explorer", "Leader", "Thinker", "Creator", "Analyst")

TYPE_PROFILES: dict[str, tuple[float, float, float, float]] = {
    # (extroversion, emotion, spontaneity, creativity) each 0–1
    "Explorer": (0.62, 0.48, 0.82, 0.72),
    "Leader": (0.88, 0.52, 0.38, 0.42),
    "Thinker": (0.38, 0.35, 0.42, 0.68),
    "Creator": (0.58, 0.78, 0.68, 0.88),
    "Analyst": (0.42, 0.32, 0.28, 0.38),
}

TYPE_BADGES = {
    "Explorer": "🧭 Pathfinder",
    "Leader": "👑 Vanguard",
    "Thinker": "🔭 Sage",
    "Creator": "🎨 Visionary",
    "Analyst": "📐 Architect",
}


@dataclass(frozen=True)
class Option:
    text: str
    # Cumulative trait deltas (roughly -3 to +3 per answer; summed then normalized)
    extroversion: float  # higher = more extroverted
    emotion: float  # higher = more emotion-led
    spontaneity: float  # higher = more spontaneous
    creativity: float  # higher = more creative


def questions() -> list[dict[str, Any]]:
    """
    Return 12 MCQs. Each has 4 options with trait deltas.
    Axes: extroversion, emotion (vs logic), spontaneity (vs planning), creativity (vs practical).
    """
    return [
        {
            "id": 1,
            "prompt": "Friday evening appears — no plans yet. What sounds most like you?",
            "options": [
                Option("Host or join a lively group outing", 2.2, 0.8, 1.0, 0.4),
                Option("Quiet project at home with a close friend", -1.0, 0.2, -0.6, 0.8),
                Option("Spontaneous adventure — maps optional", 1.2, 0.6, 2.4, 1.2),
                Option("Structured evening: goals, timer, checklist", -0.8, -0.4, -2.0, -0.6),
            ],
        },
        {
            "id": 2,
            "prompt": "When a decision is emotionally heavy, you usually…",
            "options": [
                Option("Talk it through with people you trust", 1.4, 1.8, 0.2, 0.2),
                Option("Write pros/cons until the pattern is clear", -0.6, -1.6, -0.8, -0.4),
                Option("Move fast — clarity comes from doing", 0.8, 0.4, 1.6, 0.6),
                Option("Seek a creative reframing or metaphor", -0.2, 1.0, 0.4, 1.8),
            ],
        },
        {
            "id": 3,
            "prompt": "Your ideal workspace vibe is…",
            "options": [
                Option("Open floor, buzz, quick collisions", 2.0, 0.2, 0.4, 0.6),
                Option("Calm corner, headphones, deep focus", -1.8, -0.6, -0.2, 0.4),
                Option("Rotating spots — novelty keeps you sharp", 0.6, 0.4, 1.4, 1.0),
                Option("Clean desk, labeled systems, minimal clutter", -1.0, -1.0, -1.6, -1.0),
            ],
        },
        {
            "id": 4,
            "prompt": "Learning something new, you prefer…",
            "options": [
                Option("Workshops, cohorts, live Q&A", 1.6, 0.6, 0.2, 0.4),
                Option("Books, papers, self-paced modules", -1.2, -0.8, -0.6, 0.2),
                Option("Jump in and fix real problems as they appear", 0.4, 0.2, 1.8, 0.8),
                Option("Sketch, prototype, storyboard, remix ideas", 0.2, 0.8, 0.8, 2.2),
            ],
        },
        {
            "id": 5,
            "prompt": "Conflict on a team — your first instinct is…",
            "options": [
                Option("Facilitate, align, keep energy constructive", 1.8, 1.2, 0.2, 0.2),
                Option("Step back, analyze root cause, propose a fix", -0.8, -1.2, -0.4, -0.2),
                Option("Address it quickly before it hardens", 0.8, 0.4, 1.2, 0.2),
                Option("Reframe the problem so new options appear", -0.2, 0.8, 0.6, 1.4),
            ],
        },
        {
            "id": 6,
            "prompt": "Deadlines: which line fits you best?",
            "options": [
                Option("I rally people and communicate shifts early", 1.4, 0.4, -0.6, 0.2),
                Option("I build buffer time and quality gates", -0.6, -0.8, -1.8, -0.6),
                Option("I thrive when the clock adds adrenaline", 0.6, 0.6, 2.0, 0.4),
                Option("I iterate until it feels right, even if tight", -0.2, 1.0, 0.4, 1.4),
            ],
        },
        {
            "id": 7,
            "prompt": "Praise that hits hardest for you is…",
            "options": [
                Option("You made the room better today", 1.6, 1.0, 0.2, 0.4),
                Option("Your reasoning was airtight", -0.4, -1.4, -0.6, -0.2),
                Option("You moved when others hesitated", 0.8, 0.4, 1.4, 0.6),
                Option("That idea was unexpected and useful", 0.2, 0.8, 0.6, 1.8),
            ],
        },
        {
            "id": 8,
            "prompt": "Travel style — pick the closest match:",
            "options": [
                Option("Group trip, shared stories, social energy", 2.0, 0.8, 0.6, 0.4),
                Option("Solo itinerary, museums, long reads", -1.6, -0.4, -0.8, 0.6),
                Option("One-way ticket energy — plans emerge on the road", 0.8, 0.6, 2.2, 1.0),
                Option("Optimized route, reservations, backup plans", -0.6, -0.6, -1.8, -0.8),
            ],
        },
        {
            "id": 9,
            "prompt": "When you explain a concept, you lean toward…",
            "options": [
                Option("Stories, analogies, audience interaction", 1.2, 1.4, 0.4, 0.8),
                Option("Definitions, structure, edge cases", -0.8, -1.2, -0.8, -0.4),
                Option("Live demo — show, don’t tell", 0.6, 0.2, 1.2, 0.8),
                Option("Metaphors, visuals, playful examples", 0.2, 0.8, 0.6, 1.6),
            ],
        },
        {
            "id": 10,
            "prompt": "Risk — your relationship with it is…",
            "options": [
                Option("Shared bets with a team I trust", 1.4, 0.6, 0.4, 0.2),
                Option("Measured risk after careful modeling", -0.6, -1.0, -1.4, -0.6),
                Option("I’d rather act than overthink", 0.8, 0.4, 1.8, 0.4),
                Option("I take risks for originality, not speed", -0.2, 0.8, 0.6, 1.8),
            ],
        },
        {
            "id": 11,
            "prompt": "After a big week, recovery looks like…",
            "options": [
                Option("People, laughter, something celebratory", 1.8, 1.0, 0.4, 0.2),
                Option("Silence, routine, low-stimulation reset", -1.8, -0.4, -0.6, 0.2),
                Option("Impulse plan — new place, new food", 0.8, 0.6, 1.8, 0.8),
                Option("Creative play: music, art, writing", -0.2, 0.8, 0.4, 1.6),
            ],
        },
        {
            "id": 12,
            "prompt": "Your north star in work/life is closest to…",
            "options": [
                Option("Impact through people and momentum", 1.6, 0.8, 0.4, 0.4),
                Option("Truth, mastery, and elegant systems", -0.8, -1.0, -0.8, 0.0),
                Option("Freedom to explore and pivot fast", 0.6, 0.4, 1.6, 1.0),
                Option("Making things that feel alive and new", 0.2, 1.0, 0.6, 2.0),
            ],
        },
    ]


def _init_session() -> None:
    """Initialize session_state keys once."""
    if "answers" not in st.session_state:
        st.session_state.answers = {}
    if "step" not in st.session_state:
        st.session_state.step = 0  # index of current question
    if "quiz_done" not in st.session_state:
        st.session_state.quiz_done = False
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"
    if "question_started_at" not in st.session_state:
        st.session_state.question_started_at = time.time()
    if "show_timer" not in st.session_state:
        st.session_state.show_timer = True


def calculate_scores(answers: dict[int, int], qs: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Sum option deltas keyed by question index -> selected option index (0-3).
    Returns normalized 0-100 trait values plus raw sums for debugging logic.
    """
    sums = {"extroversion": 0.0, "emotion": 0.0, "spontaneity": 0.0, "creativity": 0.0}
    for i, q in enumerate(qs):
        idx = answers.get(q["id"])
        if idx is None:
            continue
        opt: Option = q["options"][idx]
        sums["extroversion"] += opt.extroversion
        sums["emotion"] += opt.emotion
        sums["spontaneity"] += opt.spontaneity
        sums["creativity"] += opt.creativity

    # Typical per-axis range ~[-24, 24]; map to 0-100 with soft clamp
    def to_0_100(x: float) -> float:
        # ~[-30, 30] -> [0, 100]
        t = (x + 30.0) / 60.0
        return float(max(0.0, min(100.0, t * 100.0)))

    traits = {k: to_0_100(v) for k, v in sums.items()}
    norms = {k: v / 100.0 for k, v in traits.items()}
    return {"sums": sums, "traits": traits, "norms": norms}


def _classify_personality(norms: dict[str, float]) -> tuple[str, float]:
    """Return personality label and confidence (0-100) via distance to ideal profiles."""
    vec = np.array(
        [norms["extroversion"], norms["emotion"], norms["spontaneity"], norms["creativity"]],
        dtype=float,
    )
    best_name = "Thinker"
    best_dist = float("inf")
    for name, profile in TYPE_PROFILES.items():
        p = np.array(profile, dtype=float)
        d = float(np.linalg.norm(vec - p))
        if d < best_dist:
            best_dist = d
            best_name = name
    # Max distance in unit hypercube ~ sqrt(4)=2; map to confidence
    confidence = max(0.0, min(100.0, 100.0 * (1.0 - best_dist / 1.75)))
    return best_name, confidence


def hashlib_hex_seed(s: str) -> int:
    import hashlib

    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def _pick_variant(seed: str, *choices: str) -> str:
    """Deterministic 'variation' from seed + stable hash."""
    rng = random.Random(int(hashlib_hex_seed(seed)))
    return rng.choice(list(choices))


def _dynamic_blurb(
    ptype: str,
    norms: dict[str, float],
    confidence: float,
) -> dict[str, Any]:
    """Build dynamic strings from scores (not static blocks)."""
    e, em, sp, cr = (
        norms["extroversion"],
        norms["emotion"],
        norms["spontaneity"],
        norms["creativity"],
    )
    seed = f"{ptype}|{e:.2f}|{em:.2f}|{sp:.2f}|{cr:.2f}"

    # Title line
    intensity = "Signature" if confidence > 78 else "Emerging" if confidence > 62 else "Balanced"
    title = f"{intensity} {ptype} Profile"

    # Personalized description — clauses depend on dominant axes
    dom = max(
        ("social energy", e),
        ("heart-led choice", em),
        ("adaptive tempo", sp),
        ("imaginative edge", cr),
        key=lambda x: x[1],
    )[0]

    desc = (
        f"Your pattern centers on **{dom}** — "
        f"with extroversion at **{e*100:.0f}%**, emotion-led style **{em*100:.0f}%**, "
        f"spontaneity **{sp*100:.0f}%**, and creative tilt **{cr*100:.0f}%**. "
    )
    desc += _pick_variant(
        seed + "d1",
        "That mix shapes how you recharge, decide, and take risks.",
        "Those weights show up in how you plan, collaborate, and improvise.",
        "The blend explains both your momentum and your friction points.",
    )

    # Strengths / weaknesses from thresholds
    strengths: list[str] = []
    weaknesses: list[str] = []
    if e >= 0.58:
        strengths.append("Energizes groups and keeps dialogue moving")
        weaknesses.append("May under-schedule solo deep work when social demand is high")
    else:
        strengths.append("Sustained focus and reflective processing")
        weaknesses.append("May delay broadcasting wins or asking for help early")

    if em >= 0.52:
        strengths.append("Reads tone well and aligns people through empathy")
        weaknesses.append("Can over-index on harmony when a crisp tradeoff is needed")
    else:
        strengths.append("Cool-headed tradeoffs and structured reasoning")
        weaknesses.append("May feel blunt when warmth would unlock speed")

    if sp >= 0.55:
        strengths.append("Fast iteration and courage to change course")
        weaknesses.append("Risk of scattered priorities without a north-star checkpoint")
    else:
        strengths.append("Reliable sequencing, buffers, and follow-through")
        weaknesses.append("May resist last-minute pivots even when they help")

    if cr >= 0.55:
        strengths.append("Novel framing — turns constraints into prototypes")
        weaknesses.append("Perfection loops if novelty stays ahead of shipping")
    else:
        strengths.append("Pragmatic execution and measurable outcomes")
        weaknesses.append("May trim imagination too early under pressure")

    behavior = [
        _pick_variant(
            seed + "b1",
            "Under stress you likely tighten your preferred lever first — then rebalance.",
            "When overloaded, you revert to your strongest axis — watch the blind spot opposite it.",
            "Your default coping style is consistent — which is powerful if you name it early.",
        ),
        _pick_variant(
            seed + "b2",
            f"Confidence fit: **{confidence:.0f}/100** — {_confidence_note(confidence)}.",
            f"Model confidence sits at **{confidence:.0f}/100**, suggesting {_confidence_note(confidence)}.",
        ),
    ]

    return {
        "title": title,
        "personality": ptype,
        "description": desc,
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "behavior": behavior,
        "confidence": confidence,
    }


def _confidence_note(c: float) -> str:
    if c >= 80:
        return "a sharp archetype match"
    if c >= 65:
        return "a clear lean with room for hybrid habits"
    return "a blended profile — lean into context, not labels"


def generate_result(scores: dict[str, Any]) -> dict[str, Any]:
    """Full result object: classification + narrative + meta."""
    norms = scores["norms"]
    ptype, conf = _classify_personality(norms)
    narrative = _dynamic_blurb(ptype, norms, conf)
    recs = recommendation_engine(ptype, norms)
    final_score = int(round(60 + 0.4 * conf + 0.1 * (norms["extroversion"] + norms["creativity"]) * 100))
    final_score = max(55, min(99, final_score))
    return {
        "personality": ptype,
        "confidence": conf,
        "traits": scores["traits"],
        "norms": norms,
        "narrative": narrative,
        "recommendations": recs,
        "final_score": final_score,
        "badge": TYPE_BADGES.get(ptype, "🏆 Achiever"),
    }


def recommendation_engine(ptype: str, norms: dict[str, float]) -> dict[str, list[str]]:
    """Career, skills, productivity, habits — keyed by personality."""
    base = {
        "Explorer": {
            "careers": [
                "Product discovery / venture scouting",
                "Field research & ethnography",
                "Travel-heavy partnerships or BD",
            ],
            "skills": [
                "Rapid prototyping",
                "Story-driven pitching",
                "Lightweight analytics for fast decisions",
            ],
            "productivity": [
                "Use time-boxed ‘explore blocks’ with a hard stop",
                "Capture insights in a single running log to reduce context loss",
            ],
            "habits": [
                "Weekly ‘north star’ review to anchor spontaneity",
                "Pair novelty with one measurable outcome per sprint",
            ],
        },
        "Leader": {
            "careers": [
                "Program / operations leadership",
                "Customer success leadership",
                "Founder-facing advisory",
            ],
            "skills": [
                "Stakeholder communication",
                "Delegation & RACI clarity",
                "Executive narrative building",
            ],
            "productivity": [
                "Front-load decisions; protect calendars from reactive drift",
                "Use async updates + short live syncs",
            ],
            "habits": [
                "Daily 10-minute team pulse",
                "Friday wins broadcast to lock morale",
            ],
        },
        "Thinker": {
            "careers": [
                "Research science / policy analysis",
                "Quant modeling & risk",
                "Technical writing & architecture",
            ],
            "skills": [
                "Structured argumentation",
                "Statistical reasoning",
                "Systems mapping",
            ],
            "productivity": [
                "Deep-work sprints with prewritten exit criteria",
                "Separate ‘thinking’ and ‘shipping’ modes explicitly",
            ],
            "habits": [
                "Teach-to-learn: one short explainer per week",
                "Time cap analysis loops to avoid infinite refinement",
            ],
        },
        "Creator": {
            "careers": [
                "UX / brand / content direction",
                "Creative technology & design",
                "Innovation labs & R&D storytelling",
            ],
            "skills": [
                "Visual storytelling",
                "Design critique & iteration",
                "Audience research synthesis",
            ],
            "productivity": [
                "Theme days: create vs critique vs ship",
                "Use constraints as prompts, not enemies",
            ],
            "habits": [
                "Ship a small artifact weekly (even rough)",
                "Keep a swipe file for sparks you can recombine later",
            ],
        },
        "Analyst": {
            "careers": [
                "Business intelligence & forecasting",
                "Compliance & process excellence",
                "Technical PM with metrics ownership",
            ],
            "skills": [
                "SQL / dashboards",
                "Root-cause analysis",
                "Scenario planning",
            ],
            "productivity": [
                "Checklists + automated alerts for anomalies",
                "Batch similar analytical tasks to reduce switching",
            ],
            "habits": [
                "Document assumptions beside every conclusion",
                "Schedule ‘challenge sessions’ to stress-test your models",
            ],
        },
    }
    out = dict(base[ptype])
    # Micro-tweaks from norms (dynamic feel)
    if norms["spontaneity"] > 0.62 and ptype in ("Analyst", "Thinker"):
        out["productivity"] = out["productivity"] + [
            "Add one deliberate improvisation hour weekly to avoid over-rigidity"
        ]
    if norms["emotion"] > 0.62 and ptype == "Leader":
        out["habits"] = out["habits"] + [
            "Name feelings in retros — it speeds trust without losing clarity"
        ]
    return out


def plot_chart(traits: dict[str, float]) -> io.BytesIO:
    """
    Matplotlib radar chart for four traits (0-100).
    Returns PNG bytes buffer for display and PDF embedding.
    """
    labels = ["Extroversion", "Emotion-led", "Spontaneity", "Creativity"]
    values = [
        traits["extroversion"],
        traits["emotion"],
        traits["spontaneity"],
        traits["creativity"],
    ]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    values_c = values + values[:1]
    angles_c = angles + angles[:1]

    fig = plt.figure(figsize=(5, 5), facecolor="#0a0a12")
    ax = fig.add_subplot(111, polar=True, facecolor="#0a0a12")
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_thetagrids(np.degrees(angles), labels, color="#b8f4ff", fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], color="#7dd3fc", fontsize=8)
    ax.grid(color="#334155", linestyle="--", linewidth=0.6, alpha=0.8)
    ax.plot(
        angles_c,
        values_c,
        color="#22d3ee",
        linewidth=2.4,
        label="Trait profile",
    )
    ax.fill(angles_c, values_c, color="#6366f1", alpha=0.35)
    ax.set_title("Trait radar — PsycheNova AI", color="#e0f2fe", fontsize=12, pad=16)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


def generate_pdf(result: dict[str, Any], chart_png: io.BytesIO) -> bytes:
    """Build a downloadable PDF via reportlab."""
    chart_png.seek(0)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=48,
        bottomMargin=48,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#312e81"),
        spaceAfter=12,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#4338ca"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "B",
        parent=styles["BodyText"],
        textColor=colors.HexColor("#1e293b"),
        leading=14,
    )

    story: list[Any] = []
    story.append(Paragraph("PsycheNova AI — Personality Report", title_style))
    story.append(Paragraph("<b>PsycheNova AI</b> · Premium personality synthesis", body))
    story.append(Spacer(1, 0.15 * inch))
    nar = result["narrative"]
    story.append(Paragraph(f"<b>Result:</b> {nar['personality']} — {nar['title']}", h2))
    story.append(Paragraph(nar["description"].replace("**", ""), body))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("<b>Trait radar (snapshot)</b>", h2))
    img = RLImage(chart_png, width=4.2 * inch, height=4.2 * inch)
    story.append(img)
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("<b>Strengths</b>", h2))
    for s in nar["strengths"]:
        story.append(Paragraph(f"• {s}", body))
    story.append(Paragraph("<b>Growth edges</b>", h2))
    for w in nar["weaknesses"]:
        story.append(Paragraph(f"• {w}", body))

    rec = result["recommendations"]
    story.append(Paragraph("<b>Recommendations</b>", h2))
    for section, label in (
        ("careers", "Career paths"),
        ("skills", "Skills to learn"),
        ("productivity", "Productivity tips"),
        ("habits", "Habit improvements"),
    ):
        story.append(Paragraph(f"<i>{label}</i>", body))
        for item in rec[section]:
            story.append(Paragraph(f"• {item}", body))
        story.append(Spacer(1, 0.06 * inch))

    story.append(Spacer(1, 0.1 * inch))
    meta = Table(
        [
            ["Final score", str(result["final_score"])],
            ["Badge", result["badge"]],
            ["Confidence fit", f"{result['confidence']:.0f}/100"],
        ],
        colWidths=[2.2 * inch, 3.5 * inch],
    )
    meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2ff")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c7d2fe")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(meta)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def inject_css(theme: str) -> None:
    """Premium dark neon + light theme via Streamlit markdown."""
    dark = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap');
      html, body, [class*="css"]  { font-family: 'Outfit', sans-serif; }
      .stApp {
        background: radial-gradient(1200px 800px at 20% 0%, #1e1b4b 0%, #0f172a 45%, #020617 100%);
        color: #e0f2fe;
      }
      section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e1b4b 100%) !important;
        border-right: 1px solid rgba(56, 189, 248, 0.25);
      }
      div[data-testid="stVerticalBlock"] > div:has(> div.element-container) {
        transition: opacity 220ms ease, transform 220ms ease;
      }
      .nova-card {
        max-width: 720px;
        margin: 0 auto;
        padding: 1.75rem 1.5rem;
        border-radius: 18px;
        background: linear-gradient(145deg, rgba(15,23,42,0.92), rgba(30,27,75,0.75));
        border: 1px solid rgba(56, 189, 248, 0.35);
        box-shadow: 0 0 40px rgba(99, 102, 241, 0.25), inset 0 0 60px rgba(56, 189, 248, 0.06);
        backdrop-filter: blur(8px);
      }
      /* Solid text — gradient + transparent fill often renders invisible in Streamlit/WebKit */
      .nova-title {
        font-size: 2.1rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 0.25rem;
        color: #e0f2fe !important;
        -webkit-text-fill-color: #e0f2fe;
        text-shadow: 0 0 28px rgba(34, 211, 238, 0.45);
      }
      .nova-sub {
        text-align: center;
        color: #bae6fd;
        opacity: 0.9;
        margin-bottom: 1rem;
      }
      .stButton > button {
        border-radius: 999px !important;
        border: 1px solid rgba(56, 189, 248, 0.55) !important;
        background: linear-gradient(90deg, #312e81, #4f46e5 60%, #0ea5e9) !important;
        color: #ecfeff !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.1rem !important;
        box-shadow: 0 0 18px rgba(56, 189, 248, 0.45);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
      }
      .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 0 26px rgba(129, 140, 248, 0.65);
      }
      .stProgress > div > div {
        background: linear-gradient(90deg, #22d3ee, #818cf8) !important;
      }
      .stRadio label { color: #e0f2fe !important; }
      h1, h2, h3 { color: #e0f2fe !important; }
      @media (max-width: 640px) {
        .nova-card { padding: 1.1rem 0.9rem !important; margin: 0 0.25rem !important; }
        .nova-title { font-size: 1.55rem !important; }
      }
    </style>
    """
    light = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap');
      html, body, [class*="css"]  { font-family: 'Outfit', sans-serif; }
      .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e0e7ff 50%, #dbeafe 100%);
        color: #0f172a;
      }
      section[data-testid="stSidebar"] {
        background: #f1f5f9 !important;
        border-right: 1px solid #cbd5e1;
      }
      .nova-card {
        max-width: 720px;
        margin: 0 auto;
        padding: 1.75rem 1.5rem;
        border-radius: 18px;
        background: #ffffffcc;
        border: 1px solid #c7d2fe;
        box-shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
        backdrop-filter: blur(6px);
      }
      .nova-title {
        font-size: 2.1rem;
        font-weight: 700;
        text-align: center;
        color: #1e1b4b !important;
        -webkit-text-fill-color: #1e1b4b;
      }
      .nova-sub { text-align: center; color: #334155; margin-bottom: 1rem; }
      .stButton > button {
        border-radius: 999px !important;
        border: 1px solid #6366f1 !important;
        background: linear-gradient(90deg, #4f46e5, #2563eb) !important;
        color: white !important;
        font-weight: 600 !important;
      }
      h1, h2, h3 { color: #0f172a !important; }
      @media (max-width: 640px) {
        .nova-card { padding: 1.1rem 0.9rem !important; margin: 0 0.25rem !important; }
        .nova-title { font-size: 1.55rem !important; }
      }
    </style>
    """
    st.markdown(dark if theme == "dark" else light, unsafe_allow_html=True)


def render_header() -> None:
    lp = resolve_logo_path()
    if lp is not None:
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            _safe_logo_image(lp, 260)
    st.markdown(
        '<div class="nova-card">'
        '<div class="nova-title">PsycheNova AI 🧠✨</div>'
        '<div class="nova-sub">Brain Buzz · Personality prediction · trait radar · actionable insights 🎯🔥</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    # Must be the first Streamlit call — session_state/widgets before this can blank the app
    try:
        st.set_page_config(
            page_title="PsycheNova AI · Brain Buzz",
            page_icon="🧠",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except StreamlitAPIException:
        pass  # already configured (rerun / multipage)

    _init_session()
    lp = resolve_logo_path()

    qs = questions()
    total = len(qs)

    inject_css(st.session_state.theme)

    with st.sidebar:
        if lp is not None:
            _safe_logo_image(lp, 120)
            st.caption("Brain Buzz · PsycheNova AI")
        st.markdown("### 🌗 Theme")
        theme_choice = st.radio(
            "Appearance",
            ("Dark 🌙", "Light ☀️"),
            index=0 if st.session_state.theme == "dark" else 1,
            horizontal=True,
        )
        st.session_state.theme = "dark" if theme_choice.startswith("Dark") else "light"
        inject_css(st.session_state.theme)

        st.markdown("### ⚙️ Navigation")
        if st.button("🔄 Restart quiz", use_container_width=True):
            st.session_state.answers = {}
            st.session_state.step = 0
            st.session_state.quiz_done = False
            st.session_state.question_started_at = time.time()
            st.rerun()

        st.session_state.show_timer = st.toggle("⏱️ Show per-question timer", value=st.session_state.show_timer)

        st.caption("PsycheNova AI uses trait-weighted MCQs — no chatbot, pure synthesis logic.")

    render_header()
    st.markdown("<br/>", unsafe_allow_html=True)

    if not st.session_state.quiz_done:
        q = qs[st.session_state.step]
        prog = (st.session_state.step + 1) / total
        st.progress(prog)
        st.markdown(f"### Question **{st.session_state.step + 1}** of **{total}**")

        if st.session_state.show_timer:
            elapsed = int(time.time() - st.session_state.question_started_at)
            st.caption(f"⏳ Time on this question: **{elapsed}s** (optional reflection timer)")

        st.markdown(f"#### {q['prompt']}")
        labels = [o.text for o in q["options"]]
        ans_idx = st.session_state.answers.get(q["id"])
        default_idx = (
            ans_idx if isinstance(ans_idx, int) and 0 <= ans_idx < len(labels) else 0
        )

        choice = st.radio(
            "Choose the option that fits you best:",
            labels,
            index=default_idx,
            key=f"q_{q['id']}",
        )

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            if st.button("← Back"):
                if st.session_state.step > 0:
                    st.session_state.step -= 1
                    st.session_state.question_started_at = time.time()
                    st.rerun()
        with col2:
            if st.button("Next →"):
                idx = labels.index(choice)
                st.session_state.answers[q["id"]] = idx
                if st.session_state.step < total - 1:
                    st.session_state.step += 1
                    st.session_state.question_started_at = time.time()
                    st.rerun()
                else:
                    with st.spinner("Synthesizing your PsycheNova profile…"):
                        time.sleep(1.1)
                    st.session_state.quiz_done = True
                    st.rerun()

        # Persist selection when navigating
        st.session_state.answers[q["id"]] = labels.index(choice)

    else:
        answers = st.session_state.answers
        scores = calculate_scores(answers, qs)
        result = generate_result(scores)

        with st.spinner("Rendering analytics…"):
            time.sleep(0.35)
            chart_buf = plot_chart(scores["traits"])

        st.success("🎉 Quiz complete — your profile is ready.")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Final score", f"{result['final_score']}/100")
        with c2:
            st.metric("Personality badge", result["badge"])
        with c3:
            st.metric("Model confidence", f"{result['confidence']:.0f}/100")

        nar = result["narrative"]
        st.markdown(f"## {nar['title']}")
        st.markdown(nar["description"])
        st.markdown("**Strengths**")
        for s in nar["strengths"]:
            st.markdown(f"- {s}")
        st.markdown("**Growth edges**")
        for w in nar["weaknesses"]:
            st.markdown(f"- {w}")
        st.markdown("**Behavior insights**")
        for b in nar["behavior"]:
            st.markdown(f"- {b}")

        st.subheader("📊 Trait radar")
        chart_buf.seek(0)
        st.image(chart_buf, use_container_width=True)

        rec = result["recommendations"]
        st.subheader("🎯 Recommendations")
        st.markdown("**Career paths**")
        for x in rec["careers"]:
            st.markdown(f"- {x}")
        st.markdown("**Skills to learn**")
        for x in rec["skills"]:
            st.markdown(f"- {x}")
        st.markdown("**Productivity tips**")
        for x in rec["productivity"]:
            st.markdown(f"- {x}")
        st.markdown("**Habit improvements**")
        for x in rec["habits"]:
            st.markdown(f"- {x}")

        pdf_bytes = generate_pdf(result, chart_buf)
        st.download_button(
            label="📄 Download PDF report",
            data=pdf_bytes,
            file_name="psychenova_ai_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

        if st.button("🔁 Take the quiz again"):
            st.session_state.answers = {}
            st.session_state.step = 0
            st.session_state.quiz_done = False
            st.session_state.question_started_at = time.time()
            st.rerun()


if __name__ == "__main__":
    main()
