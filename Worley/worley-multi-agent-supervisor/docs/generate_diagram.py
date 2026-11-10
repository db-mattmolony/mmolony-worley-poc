"""
Generate Worley Multi-Agent Supervisor Architecture Diagram as PNG.
Uses matplotlib with FancyBboxPatch and annotated arrows for a clean flowchart.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as pe

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
WORLEY_ORANGE = "#E8500A"
DARK_BG       = "#1E2A3A"
MID_BLUE      = "#2E5B9A"
LIGHT_BLUE    = "#4A90D9"
TEAL          = "#2B8C7E"
PURPLE        = "#6B4FA0"
GREEN         = "#3A8A4A"
WHITE         = "#FFFFFF"
OFF_WHITE     = "#F5F7FA"
LIGHT_GREY    = "#D0D8E4"
DARK_TEXT     = "#1A1A2E"
ARROW_COLOR   = "#5A6A7E"
LABEL_BG      = "#EFF3FA"

FIG_W, FIG_H = 20, 26

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
fig.patch.set_facecolor(OFF_WHITE)
ax.set_facecolor(OFF_WHITE)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def node(ax, cx, cy, w, h, title, subtitle=None,
         fc=MID_BLUE, tc=WHITE, radius=0.35, fontsize=11,
         subtitle_fontsize=9):
    shadow = FancyBboxPatch(
        (cx - w / 2 + 0.09, cy - h / 2 - 0.09), w, h,
        boxstyle=f"round,pad=0.05,rounding_size={radius}",
        linewidth=0, facecolor="#00000030", zorder=2,
    )
    box = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle=f"round,pad=0.05,rounding_size={radius}",
        linewidth=1.8, edgecolor=WHITE, facecolor=fc, zorder=3,
    )
    ax.add_patch(shadow)
    ax.add_patch(box)

    title_y = cy + (0.2 if subtitle else 0)
    ax.text(cx, title_y, title, ha="center", va="center",
            fontsize=fontsize, fontweight="bold", color=tc, zorder=4,
            multialignment="center")

    if subtitle:
        ax.text(cx, cy - 0.3, subtitle, ha="center", va="center",
                fontsize=subtitle_fontsize, color=tc, alpha=0.85, zorder=4,
                multialignment="center", style="italic")


def straight_arrow(ax, x1, y1, x2, y2, label="", color=ARROW_COLOR,
                   lw=1.9, label_offset_x=0.0, label_offset_y=0.18):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color, lw=lw,
            mutation_scale=14,
            connectionstyle="arc3,rad=0.0",
        ),
        zorder=5,
    )
    if label:
        mx = (x1 + x2) / 2 + label_offset_x
        my = (y1 + y2) / 2 + label_offset_y
        ax.text(mx, my, label, ha="center", va="center",
                fontsize=8.5, color=color, fontweight="bold",
                bbox=dict(fc=LABEL_BG, ec="none", boxstyle="round,pad=2", alpha=0.9),
                zorder=6)


def elbow_arrow(ax, x1, y1, x2, y2, label="", color=ARROW_COLOR, lw=1.9,
                rad=0.15, label_offset_x=0.0, label_offset_y=0.18):
    """Arrow with a slight curve (used for diagonal routes)."""
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color, lw=lw,
            mutation_scale=14,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=5,
    )
    if label:
        mx = (x1 + x2) / 2 + label_offset_x
        my = (y1 + y2) / 2 + label_offset_y
        ax.text(mx, my, label, ha="center", va="center",
                fontsize=8.5, color=color, fontweight="bold",
                bbox=dict(fc=LABEL_BG, ec="none", boxstyle="round,pad=2", alpha=0.9),
                zorder=6)


def section_bg(ax, x, y, w, h, label, fc="#00000008", lc=LIGHT_GREY):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.05,rounding_size=0.4",
        linewidth=1.3, linestyle="--",
        edgecolor=lc, facecolor=fc, zorder=1,
    )
    ax.add_patch(rect)
    ax.text(x + 0.3, y + h - 0.15, label,
            ha="left", va="top", fontsize=8.5, color="#7A8FA8",
            fontweight="bold", zorder=2)


# ---------------------------------------------------------------------------
# Title banner
# ---------------------------------------------------------------------------
title_bar = FancyBboxPatch(
    (0, FIG_H - 1.7), FIG_W, 1.7,
    boxstyle="square,pad=0", linewidth=0, facecolor=DARK_BG, zorder=1,
)
ax.add_patch(title_bar)
ax.axhline(FIG_H - 1.7, color=WORLEY_ORANGE, lw=5, zorder=4)

ax.text(FIG_W / 2, FIG_H - 0.72,
        "Worley Multi-Agent Supervisor — System Architecture",
        ha="center", va="center", fontsize=17, fontweight="bold",
        color=WHITE, zorder=3)
ax.text(FIG_W / 2, FIG_H - 1.28,
        "Data flow from user interaction through agent routing to trace storage",
        ha="center", va="center", fontsize=10.5, color=LIGHT_GREY, zorder=3)

# ---------------------------------------------------------------------------
# Coordinate layout
# ---------------------------------------------------------------------------
#  Row 1  y=22.8  Application
#  Row 2  y=19.8  Public Supervisor (left)  |  Multi-Agent Supervisor (centre)
#  Row 3  y=16.4  RAG Agent (left-centre)   |  Foundry Endpoint (right-centre)
#  Row 4  y=13.0  Experiment #1 (left)      |  Experiment #2 (right)
#  Row 5  y= 9.6  Delta Table #1 (left)     |  Delta Table #2 (right)
#  Row 6  y= 5.8  Monitoring Dashboard (centre)

R1 = 22.8
R2 = 19.8
R3 = 16.4
R4 = 13.0
R5 =  9.6
R6 =  5.8

C_CENTRE = 10.0
C_LEFT   =  3.2   # public supervisor
C_RAG    =  6.2
C_FOUND  = 13.8
C_EXP1   =  6.2
C_EXP2   = 13.8
C_D1     =  6.2
C_D2     = 13.8

NW = 4.4        # standard node width
NH = 1.4        # standard node height
NW_WIDE = 5.4   # wide node
NH_WIDE = 1.5

# ---------------------------------------------------------------------------
# Section backgrounds (drawn before nodes)
# ---------------------------------------------------------------------------
section_bg(ax, 4.0, 14.5, 12.0, 3.8,  "  Agent Routing",
           fc="#2B8C7E0D", lc=TEAL)
section_bg(ax, 4.0,  7.0, 12.0, 7.2,  "  MLflow Tracing & Storage",
           fc="#2E5B9A0D", lc=LIGHT_BLUE)

# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------

# Row 1 — Application
node(ax, C_CENTRE, R1, NW_WIDE, NH_WIDE,
     "Application",
     subtitle="(Databricks App) — generates trace_id",
     fc=DARK_BG, tc=WHITE, fontsize=12)

# Row 2 — Public Supervisor + Multi-Agent Supervisor
node(ax, C_LEFT, R2, 3.8, NH + 0.5,
     "Public Facing\nInverse Centre\nSupervisor Agent",
     fc=WORLEY_ORANGE, tc=WHITE, fontsize=10)

node(ax, C_CENTRE, R2, NW_WIDE, NH_WIDE,
     "Multi-Agent Supervisor",
     subtitle="(Serving Endpoint)",
     fc=MID_BLUE, tc=WHITE, fontsize=13)

# Row 3 — Sub-agents
node(ax, C_RAG, R3, NW, NH + 0.2,
     "RAG Agent",
     subtitle="(Knowledge Assistant)",
     fc=TEAL, tc=WHITE, fontsize=11)

node(ax, C_FOUND, R3, NW + 0.6, NH + 0.5,
     "Foundry Endpoint\n(Catch-all)",
     subtitle="Azure AI Foundry via AI Gateway",
     fc=PURPLE, tc=WHITE, fontsize=11)

# Row 4 — MLflow Experiments
node(ax, C_EXP1, R4, NW, NH,
     "Databricks\nExperiment #1",
     fc=LIGHT_BLUE, tc=WHITE, fontsize=11)

node(ax, C_EXP2, R4, NW, NH,
     "Databricks\nExperiment #2",
     fc=LIGHT_BLUE, tc=WHITE, fontsize=11)

# Row 5 — Delta Tables
node(ax, C_D1, R5, NW, NH,
     "#1 Traces\nDelta Tables",
     fc=GREEN, tc=WHITE, fontsize=11)

node(ax, C_D2, R5, NW, NH,
     "#2 Traces\nDelta Tables",
     fc=GREEN, tc=WHITE, fontsize=11)

# Row 6 — Monitoring Dashboard
node(ax, C_CENTRE, R6, NW_WIDE + 1.4, NH_WIDE,
     "Application — Page 2",
     subtitle="Monitoring Dashboard",
     fc=DARK_BG, tc=WHITE, fontsize=12)

# ---------------------------------------------------------------------------
# Arrows
# ---------------------------------------------------------------------------

# Application → Multi-Agent Supervisor
straight_arrow(
    ax, C_CENTRE, R1 - NH_WIDE / 2 - 0.05,
        C_CENTRE, R2 + NH_WIDE / 2 + 0.05,
    label="User Request", color=DARK_BG, lw=2.4,
)

# Public Supervisor → Multi-Agent Supervisor (horizontal)
straight_arrow(
    ax, C_LEFT + 3.8 / 2 + 0.05, R2,
        C_CENTRE - NW_WIDE / 2 - 0.05, R2,
    label="Routes requests", color=WORLEY_ORANGE, lw=2.0,
    label_offset_y=0.28,
)

# Multi-Agent Supervisor → RAG Agent
elbow_arrow(
    ax, C_CENTRE - 1.4, R2 - NH_WIDE / 2 - 0.05,
        C_RAG, R3 + (NH + 0.2) / 2 + 0.05,
    label="Knowledge queries", color=TEAL, lw=2.0,
    rad=-0.1, label_offset_x=-0.8, label_offset_y=0.2,
)

# Multi-Agent Supervisor → Foundry Endpoint
elbow_arrow(
    ax, C_CENTRE + 1.4, R2 - NH_WIDE / 2 - 0.05,
        C_FOUND, R3 + (NH + 0.5) / 2 + 0.05,
    label="General queries", color=PURPLE, lw=2.0,
    rad=0.1, label_offset_x=0.8, label_offset_y=0.2,
)

# Multi-Agent Supervisor → Experiment #1
# Route this arrow to the LEFT of the diagram to avoid overlap with agent nodes
# Use a two-segment path via annotate with connectionstyle
ax.annotate(
    "", xy=(C_EXP1, R4 + NH / 2 + 0.05),
    xytext=(C_CENTRE - NW_WIDE / 2 - 0.05, R2 - 0.2),
    arrowprops=dict(
        arrowstyle="-|>", color=LIGHT_BLUE, lw=1.9,
        mutation_scale=13,
        connectionstyle="angle,angleA=0,angleB=90,rad=0.3",
    ),
    zorder=5,
)
ax.text(2.6, (R2 + R4) / 2 + 0.2, "Traces →\nExperiment #1",
        ha="center", va="center", fontsize=8.2, color=LIGHT_BLUE,
        fontweight="bold",
        bbox=dict(fc=LABEL_BG, ec="none", boxstyle="round,pad=2", alpha=0.9),
        zorder=6)

# Multi-Agent Supervisor → Experiment #2
ax.annotate(
    "", xy=(C_EXP2, R4 + NH / 2 + 0.05),
    xytext=(C_CENTRE + NW_WIDE / 2 + 0.05, R2 - 0.2),
    arrowprops=dict(
        arrowstyle="-|>", color=LIGHT_BLUE, lw=1.9,
        mutation_scale=13,
        connectionstyle="angle,angleA=0,angleB=90,rad=0.3",
    ),
    zorder=5,
)
ax.text(17.4, (R2 + R4) / 2 + 0.2, "Traces →\nExperiment #2",
        ha="center", va="center", fontsize=8.2, color=LIGHT_BLUE,
        fontweight="bold",
        bbox=dict(fc=LABEL_BG, ec="none", boxstyle="round,pad=2", alpha=0.9),
        zorder=6)

# Experiment #1 → Delta Table #1
straight_arrow(
    ax, C_EXP1, R4 - NH / 2 - 0.05,
        C_D1, R5 + NH / 2 + 0.05,
    label="Writes", color=GREEN, lw=1.9,
)

# Experiment #2 → Delta Table #2
straight_arrow(
    ax, C_EXP2, R4 - NH / 2 - 0.05,
        C_D2, R5 + NH / 2 + 0.05,
    label="Writes", color=GREEN, lw=1.9,
)

# Delta Table #1 → Monitoring Dashboard
elbow_arrow(
    ax, C_D1, R5 - NH / 2 - 0.05,
        C_CENTRE - 2.2, R6 + NH_WIDE / 2 + 0.05,
    label="Reads traces", color=DARK_TEXT, lw=1.9,
    rad=0.08, label_offset_x=-0.5, label_offset_y=0.22,
)

# Delta Table #2 → Monitoring Dashboard
elbow_arrow(
    ax, C_D2, R5 - NH / 2 - 0.05,
        C_CENTRE + 2.2, R6 + NH_WIDE / 2 + 0.05,
    label="Reads traces", color=DARK_TEXT, lw=1.9,
    rad=-0.08, label_offset_x=0.5, label_offset_y=0.22,
)

# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------
lx, ly = 15.6, 9.8
legend_items = [
    (DARK_BG,       "Application Layer"),
    (MID_BLUE,      "Supervisor / Endpoint"),
    (TEAL,          "RAG Agent"),
    (PURPLE,        "Foundry Endpoint"),
    (WORLEY_ORANGE, "Public Supervisor"),
    (LIGHT_BLUE,    "MLflow Experiment"),
    (GREEN,         "Delta Table Storage"),
]

# Legend background
legend_h = len(legend_items) * 0.58 + 0.8
legend_border = FancyBboxPatch(
    (lx - 0.2, ly - legend_h + 0.5), 3.1, legend_h,
    boxstyle="round,pad=0.1,rounding_size=0.25",
    linewidth=1.1, edgecolor=LIGHT_GREY, facecolor="#FFFFFFCC", zorder=4,
)
ax.add_patch(legend_border)

ax.text(lx + 1.35, ly + 0.15, "Legend",
        ha="center", va="center", fontsize=9.5, fontweight="bold",
        color=DARK_TEXT, zorder=5)

for i, (color, label) in enumerate(legend_items):
    iy = ly - i * 0.58 - 0.25
    rect = FancyBboxPatch(
        (lx + 0.05, iy - 0.14), 0.34, 0.29,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=color, edgecolor=WHITE, linewidth=0.8, zorder=5,
    )
    ax.add_patch(rect)
    ax.text(lx + 0.55, iy, label, ha="left", va="center",
            fontsize=8.5, color=DARK_TEXT, zorder=5)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
ax.axhline(0.62, color=LIGHT_GREY, lw=0.8, zorder=1)
ax.text(0.4, 0.3, "Worley — Multi-Agent Supervisor Architecture",
        ha="left", va="center", fontsize=8.5, color="#8A9AB0")
ax.text(FIG_W - 0.4, 0.3, "Confidential",
        ha="right", va="center", fontsize=8.5, color="#8A9AB0")

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
out = "/Users/matt.molony/Documents/Clients/Worley/worley-multi-agent-supervisor/docs/architecture.png"
plt.tight_layout(pad=0)
plt.savefig(out, dpi=150, bbox_inches="tight",
            facecolor=OFF_WHITE, edgecolor="none")
plt.close()
print(f"Saved: {out}")
