"""DataPilot AI - architecture-style workflow diagram.

Components sit where they belong architecturally; numbered arrows carry the
dataflow, listed out underneath in the Azure reference-architecture convention.
"""
from __future__ import annotations

import html

BLUE = "#0F6CBD"
BLUE_DK = "#0A4C86"
BLUE_LT = "#F2F8FD"
AI = "#7A4FBF"
AI_BG = "#FAF7FE"
ENG = "#0F7B8A"
ENG_BG = "#F2FAFB"
STO = "#8A5A00"
STO_BG = "#FFFBF3"
INK = "#1B1A19"
INK2 = "#4A4845"
MUTE = "#7A7875"
BD = "#D9D7D4"
BD_BLUE = "#BFDCF2"
BAND = "#F7FAFD"
RULE = "#E6E4E2"

W, H = 3000, 2260
M = 60
CWID = W - 2 * M

out: list[str] = []
def e(s): out.append(s)
def esc(s): return html.escape(str(s), quote=True)


def txt(x, y, s, fs=16, col=INK, wt=400, anchor="start", ls=0.0, fam=None):
    f = fam or "Segoe UI, Arial, sans-serif"
    e(f'<text x="{x}" y="{y}" font-family="{f}" font-size="{fs}" font-weight="{wt}" '
      f'fill="{col}" text-anchor="{anchor}" letter-spacing="{ls}">{esc(s)}</text>')


def wrap(s, width, fs):
    lim = max(1, int(width / (fs * 0.515)))
    ws, ls, cur = s.split(), [], ""
    for w_ in ws:
        t = f"{cur} {w_}".strip()
        if len(t) <= lim: cur = t
        else:
            if cur: ls.append(cur)
            cur = w_
    if cur: ls.append(cur)
    return ls


def para(x, y, s, width, fs=14.5, col=INK2, wt=400, lh=19.5):
    ls = wrap(s, width, fs)
    for i, ln in enumerate(ls):
        txt(x, y + i * lh, ln, fs, col, wt)
    return len(ls) * lh


def rrect(x, y, w, h, r=10, fill="#FFFFFF", stroke=BD, sw=1.4, dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
      f'stroke="{stroke}" stroke-width="{sw}"{da}/>')


def icon(kind, cx, cy, s=24, col=BLUE):
    h = s / 2
    x, y = cx - h, cy - h
    a = (f'fill="none" stroke="{col}" stroke-width="1.9" stroke-linecap="round" '
         f'stroke-linejoin="round"')
    g = [f'<g {a}>']
    P = g.append
    if kind == "user":
        P(f'<circle cx="{cx}" cy="{cy-h*0.34}" r="{h*0.36}"/>')
        P(f'<path d="M{x+h*0.2} {y+s} a{h*0.8} {h*0.7} 0 0 1 {s-h*0.4} 0"/>')
    elif kind == "window":
        P(f'<rect x="{x}" y="{y+h*0.14}" width="{s}" height="{s-h*0.28}" rx="3"/>')
        P(f'<path d="M{x} {y+h*0.62} H{x+s}"/>')
    elif kind == "api":
        P(f'<path d="M{cx-h*0.15} {y+h*0.2} h{-h*0.45} a{h*0.36} {h*0.36} 0 0 0 {-h*0.36} {h*0.36} '
          f'v{h*0.44} a{h*0.36} {h*0.36} 0 0 1 {-h*0.36} {h*0.36} a{h*0.36} {h*0.36} 0 0 1 '
          f'{h*0.36} {h*0.36} v{h*0.44} a{h*0.36} {h*0.36} 0 0 0 {h*0.36} {h*0.36} h{h*0.45}"/>')
        P(f'<path d="M{cx+h*0.15} {y+h*0.2} h{h*0.45} a{h*0.36} {h*0.36} 0 0 1 {h*0.36} {h*0.36} '
          f'v{h*0.44} a{h*0.36} {h*0.36} 0 0 0 {h*0.36} {h*0.36} a{h*0.36} {h*0.36} 0 0 0 '
          f'{-h*0.36} {h*0.36} v{h*0.44} a{h*0.36} {h*0.36} 0 0 1 {-h*0.36} {h*0.36} h{-h*0.45}"/>')
    elif kind == "agent":
        P(f'<path d="M{cx} {y} l{h*0.86} {h*0.5} v{h} l{-h*0.86} {h*0.5} l{-h*0.86} {-h*0.5} '
          f'v{-h} z"/>')
        P(f'<circle cx="{cx}" cy="{cy}" r="{h*0.26}"/>')
    elif kind == "gear":
        P(f'<circle cx="{cx}" cy="{cy}" r="{h*0.42}"/>')
        for i in range(6):
            import math
            an = i * math.pi / 3
            P(f'<path d="M{cx+math.cos(an)*h*0.58} {cy+math.sin(an)*h*0.58} '
              f'L{cx+math.cos(an)*h*0.92} {cy+math.sin(an)*h*0.92}"/>')
    elif kind == "db":
        P(f'<ellipse cx="{cx}" cy="{y+h*0.32}" rx="{h*0.8}" ry="{h*0.28}"/>')
        P(f'<path d="M{cx-h*0.8} {y+h*0.32} v{s-h*0.64} a{h*0.8} {h*0.28} 0 0 0 {h*1.6} 0 '
          f'v{-(s-h*0.64)}"/>')
    elif kind == "cube":
        P(f'<path d="M{cx} {y} l{h*0.86} {h*0.5} v{h} l{-h*0.86} {h*0.5} l{-h*0.86} {-h*0.5} '
          f'v{-h} z"/>')
        P(f'<path d="M{cx} {y} v{h} M{cx} {cy} l{h*0.86} {-h*0.5} M{cx} {cy} l{-h*0.86} {-h*0.5}" '
          f'opacity="0.6"/>')
    elif kind == "file":
        P(f'<path d="M{x+h*0.26} {y} h{h*0.88} l{h*0.6} {h*0.6} v{s-h*0.6} h{-h*1.48} z"/>')
    elif kind == "sparkle":
        P(f'<path d="M{cx} {y} l{h*0.27} {h*0.73} l{h*0.73} {h*0.27} l{-h*0.73} {h*0.27} '
          f'l{-h*0.27} {h*0.73} l{-h*0.27} {-h*0.73} l{-h*0.73} {-h*0.27} l{h*0.73} {-h*0.27} z"/>')
    elif kind == "chat":
        P(f'<path d="M{x} {y+h*0.22} h{s} v{s*0.6} h{-s*0.55} l{-h*0.48} {h*0.48} v{-h*0.48} '
          f'h{-h*0.2} z"/>')
    elif kind == "chart":
        P(f'<path d="M{x+h*0.12} {y+s-h*0.1} V{cy}"/><path d="M{cx} {y+s-h*0.1} V{y+h*0.28}"/>'
          f'<path d="M{x+s-h*0.12} {y+s-h*0.1} V{cy+h*0.36}"/>')
    elif kind == "search":
        P(f'<circle cx="{cx-h*0.16}" cy="{cy-h*0.16}" r="{h*0.58}"/>')
        P(f'<path d="M{cx+h*0.28} {cy+h*0.28} L{x+s} {y+s}"/>')
    elif kind == "check":
        P(f'<circle cx="{cx}" cy="{cy}" r="{h*0.82}"/>')
        P(f'<path d="M{cx-h*0.38} {cy} l{h*0.3} {h*0.32} l{h*0.54} {-h*0.6}"/>')
    elif kind == "shield":
        P(f'<path d="M{cx} {y} l{h*0.82} {h*0.34} v{h*0.72} q0 {h*0.62} {-h*0.82} {h*0.94} '
          f'q{-h*0.82} {-h*0.32} {-h*0.82} {-h*0.94} v{-h*0.72} z"/>')
    elif kind == "wrench":
        P(f'<path d="M{x+h*0.1} {y+s-h*0.1} L{cx+h*0.2} {cy-h*0.2}"/>')
        P(f'<path d="M{cx+h*0.16} {cy-h*0.26} a{h*0.5} {h*0.5} 0 1 0 {h*0.66} {-h*0.66} '
          f'l{-h*0.4} {h*0.4} l{-h*0.3} {-h*0.3} z"/>')
    elif kind == "layers":
        P(f'<path d="M{cx} {y+h*0.12} l{h*0.88} {h*0.44} l{-h*0.88} {h*0.44} l{-h*0.88} {-h*0.44} z"/>')
        P(f'<path d="M{cx-h*0.88} {cy+h*0.34} l{h*0.88} {h*0.44} l{h*0.88} {-h*0.44}" opacity="0.65"/>')
    g.append('</g>')
    return "".join(g)


def tag(x, y, label, col, fs=12.5, h=24):
    tw = len(label) * (fs * 0.63) + 22
    e(f'<rect x="{x}" y="{y}" width="{tw}" height="{h}" rx="{h/2}" fill="{col}"/>')
    txt(x + tw / 2, y + h / 2 + 4.6, label, fs, "#FFFFFF", 700, "middle", 0.9)
    return tw


def boundary(x, y, w, h, label, col=BLUE, fill=BAND):
    rrect(x, y, w, h, 14, fill, col, 1.6, "8 6")
    tw = len(label) * 8.7 + 34
    e(f'<rect x="{x+18}" y="{y-15}" width="{tw}" height="30" rx="15" fill="{col}"/>')
    txt(x + 18 + tw / 2, y + 5, label, 14.5, "#FFFFFF", 700, "middle", 1.2)


def card(x, y, w, h, title, sub=None, ic=None, col=BLUE, fs=17, mono=False):
    rrect(x, y, w, h, 9)
    e(f'<rect x="{x}" y="{y}" width="4.5" height="{h}" rx="2.2" fill="{col}"/>')
    tx = x + 20
    if ic:
        e(icon(ic, x + 34, y + h / 2, 25, col))
        tx = x + 58
    fam = "Consolas, monospace" if mono else None
    if sub:
        ls = wrap(title, w - (tx - x) - 16, fs)
        ty = y + h / 2 - (len(ls) * (fs + 3) + 17) / 2 + fs
        for i, ln in enumerate(ls):
            txt(tx, ty + i * (fs + 3), ln, fs, INK, 600, fam=fam)
        txt(tx, ty + len(ls) * (fs + 3) + 3, sub, 13.5, INK2)
    else:
        ls = wrap(title, w - (tx - x) - 16, fs)
        ty = y + h / 2 - (len(ls) - 1) * (fs + 3) / 2 + fs * 0.35
        for i, ln in enumerate(ls):
            txt(tx, ty + i * (fs + 3), ln, fs, INK, 600, fam=fam)


def chip(x, y, w, h, label, col=BLUE, fs=14.5, fill="#FFFFFF"):
    rrect(x, y, w, h, 7, fill, BD, 1.3)
    e(f'<rect x="{x}" y="{y}" width="3.5" height="{h}" rx="1.8" fill="{col}"/>')
    ls = wrap(label, w - 26, fs)
    ty = y + h / 2 - (len(ls) - 1) * 8.5 + 5
    for i, ln in enumerate(ls):
        txt(x + 14, ty + i * 17, ln, fs, INK, 600)


def flow(pts, n=None, col=BLUE, sw=2.5, dash=False, side="right"):
    d = f'M{pts[0][0]} {pts[0][1]}' + "".join(f' L{a} {b}' for a, b in pts[1:])
    da = ' stroke-dasharray="8 6"' if dash else ""
    e(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linejoin="round" '
      f'stroke-linecap="round" marker-end="url(#m{col.lstrip("#")})"{da}/>')
    if n is not None:
        i = len(pts) // 2
        (x1, y1), (x2, y2) = pts[i - 1], pts[i]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if abs(x2 - x1) < 2:
            bx = mx + (17 if side == "right" else -17)
            by = my
        else:
            bx, by = mx, my - 17
        e(f'<circle cx="{bx}" cy="{by}" r="14" fill="{col}" stroke="#FFFFFF" stroke-width="2"/>')
        txt(bx, by + 5.5, n, 14.5, "#FFFFFF", 700, "middle")


# =============================================================== document ====
e(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="__H__" '
  f'viewBox="0 0 {W} __H__" font-family="Segoe UI, Arial, sans-serif">')
e('<defs>')
for c in (BLUE, AI, ENG, STO, MUTE):
    e(f'<marker id="m{c.lstrip("#")}" viewBox="0 0 12 12" refX="9.5" refY="6" markerWidth="8" '
      f'markerHeight="8" orient="auto-start-reverse">'
      f'<path d="M1 1.6 L10.5 6 L1 10.4 z" fill="{c}"/></marker>')
e('</defs>')
e(f'<rect width="{W}" height="100%" fill="#FFFFFF"/>')

# header
e(f'<rect x="{M}" y="46" width="7" height="60" rx="3.5" fill="{BLUE}"/>')
txt(M + 26, 80, "DataPilot AI — workflow architecture", 38, INK, 700)
txt(M + 26, 110, "Components in their architectural place; numbered arrows carry the dataflow.",
    18, INK2)
txt(W - M, 78, "Workflow diagram", 17, INK2, 600, "end")
txt(W - M, 104, "As built · backend/app", 15, MUTE, 400, "end")
e(f'<path d="M{M} 132 H{W-M}" stroke="{RULE}" stroke-width="1.6"/>')

# ------------------------------------------------------ layout constants -----
COLW, GAP = 749, 36
C1, C2, C3 = M, M + COLW + GAP, M + 2 * (COLW + GAP)
RAILX = C3 + COLW + 40
RAILW = W - M - RAILX

CLI_Y, CLI_H = 190, 196
COL_Y, COL_H = 452, 806
LANE_Y = COL_Y + 768          # orthogonal routing lane along the column floor
STO_Y, STO_H = 1306, 238
DF_Y = 1606

# ------------------------------------------------------------- client band ---
boundary(M, CLI_Y, CWID, CLI_H, "CLIENT  ·  REACT SPA")
card(M + 24, CLI_Y + 52, 300, 118, "Business user", "Analyst · Steward", "user")
txt(M + 348, CLI_Y + 76, "Dataset workspace — one tab per job", 16.5, INK, 700)
tabs = ["Overview", "Quality", "Edit data", "Dashboard", "Chat", "Governance", "Reports"]
tw_ = (CWID - 24 - 348 - 24) / 7
for i, t in enumerate(tabs):
    chip(M + 348 + i * tw_, CLI_Y + 96, tw_ - 12, 56, t, BLUE, 15, BLUE_LT)

# ------------------------------------------------------------- 3 workflow ----
boundary(C1, COL_Y, COLW, COL_H, "1 · INGEST")
boundary(C2, COL_Y, COLW, COL_H, "2 · AUTOMATIC ANALYSIS")
boundary(C3, COL_Y, COLW, COL_H, "3 · INTERACTIVE WORK")
boundary(RAILX, COL_Y, RAILW, COL_H, "EXTERNAL AI", AI, AI_BG)

# --- column 1 : ingest
y1 = COL_Y + 54
card(C1 + 22, y1, COLW - 44, 74, "POST /api/v1/datasets", "FastAPI · multipart upload", "api",
     fs=16, mono=True)
card(C1 + 22, y1 + 108, COLW - 44, 84, "UploadAgent", "validate · then hand to the loader",
     "agent", AI)
card(C1 + 22, y1 + 226, COLW - 44, 96, "DataLoader",
     "chardet encoding · Sniffer delimiter · CSV/Excel/JSON/Parquet", "gear", ENG)
rrect(C1 + 22, y1 + 348, COLW - 44, 118, 9, BLUE_LT, BD_BLUE, 1.4)
txt(C1 + 42, y1 + 376, "Then three writes", 15.5, BLUE_DK, 700)
for i, t in enumerate(["Original file → uploads/", "Working copy → parquet/",
                       "Facts about it → SQLite"]):
    txt(C1 + 42, y1 + 402 + i * 22, "· " + t, 14.5, INK2)
flow([(C1 + COLW / 2, y1 + 74), (C1 + COLW / 2, y1 + 106)], "2")
flow([(C1 + COLW / 2, y1 + 192), (C1 + COLW / 2, y1 + 224)], "3")
flow([(C1 + COLW / 2, y1 + 322), (C1 + COLW / 2, y1 + 346)], "4")

rrect(C1 + 22, y1 + 500, COLW - 44, 104, 9, "#FFFFFF", BD_BLUE, 1.4)
txt(C1 + 42, y1 + 528, "Handoff", 16.5, BLUE_DK, 700)
para(C1 + 42, y1 + 552, "Nothing else is asked of the user — the working copy becomes the input "
                        "to column 2 and analysis starts on its own.", COLW - 84, 14, INK2)
rrect(C1 + 22, y1 + 624, COLW - 44, 124, 9, "#FFFFFF", BD, 1.4)
txt(C1 + 42, y1 + 652, "Rejected before any parsing", 16.5, INK, 700)
for i, t in enumerate(["Extension outside csv · xlsx · xls · json · parquet",
                       "Larger than 50 MB", "Empty body, or no data rows once parsed"]):
    txt(C1 + 42, y1 + 678 + i * 22, "· " + t, 14, INK2)
flow([(C1 + COLW / 2, y1 + 466), (C1 + COLW / 2, y1 + 498)], None, BLUE, 2.2)

# --- column 2 : analysis
y2 = COL_Y + 54
card(C2 + 22, y2, COLW - 44, 74, "POST /datasets/{id}/analyze", "also re-runs after every change",
     "api", fs=16, mono=True)
rrect(C2 + 22, y2 + 108, COLW - 44, 344, 10, AI_BG, AI, 1.8)
tg = tag(C2 + 42, y2 + 126, "ORCHESTRATOR", AI)
txt(C2 + 42 + tg + 14, y2 + 145, "SimpleCoordinator", 18, INK, 700)
txt(C2 + 42, y2 + 178, "one shared context · failures isolated", 14, AI, 600)
ag = [("Profiling agent", "column types + statistics", "search"),
      ("Quality agent", "20+ checks → 6-part score", "check"),
      ("Governance agent", "sensitivity + tier", "shield")]
for i, (nm, sb, ic) in enumerate(ag):
    card(C2 + 42, y2 + 196 + i * 80, COLW - 84, 68, nm, sb, ic, AI, fs=16)
    if i:
        flow([(C2 + COLW / 2, y2 + 196 + i * 80 - 12), (C2 + COLW / 2, y2 + 196 + i * 80)],
             col=AI, sw=2.2)
card(C2 + 22, y2 + 476, (COLW - 60) / 2, 88, "Profiler", "types · stats", "gear", ENG, fs=16)
card(C2 + 22 + (COLW - 60) / 2 + 16, y2 + 476, (COLW - 60) / 2, 88, "QualityEngine + Scorer",
     "checks · weighting", "gear", ENG, fs=16)
rrect(C2 + 22, y2 + 588, COLW - 44, 106, 9, "#FFFBF3", "#E8C48A", 1.5)
txt(C2 + 42, y2 + 616, "Approval gate", 16.5, STO, 700)
para(C2 + 42, y2 + 640, "Score 75+ cleared automatically. Below 75 the dataset is held as "
                        "pending until a human approves or rejects it.", COLW - 84, 14, INK2)
flow([(C2 + COLW / 2, y2 + 74), (C2 + COLW / 2, y2 + 106)], "5")
flow([(C2 + COLW / 2, y2 + 452), (C2 + COLW / 2, y2 + 474)], "6")
flow([(C2 + COLW / 2, y2 + 564), (C2 + COLW / 2, y2 + 586)], "8")

# --- column 3 : interactive
y3 = COL_Y + 54
apis = ["POST /quality/issues/{id}/fix", "POST /validations/propose",
        "POST /chat", "POST /dashboard/command"]
rrect(C3 + 22, y3, COLW - 44, 108, 9, BLUE_LT, BD_BLUE, 1.4)
txt(C3 + 42, y3 + 26, "On-demand endpoints", 15.5, BLUE_DK, 700)
for i, a in enumerate(apis):
    txt(C3 + 42, y3 + 50 + i * 19, "· " + a, 13.5, INK2, fam="Consolas, monospace")
ag3 = [("Fix path", "guarded · undoable · re-analyses", "wrench", ENG),
       ("Validation path", "AI drafts the rule, you approve it", "check", AI),
       ("ChatAgent", "plan → query → narrate", "chat", AI),
       ("DashboardAgent", "recommends, then builds on request", "chart", AI)]
for i, (nm, sb, ic, cc) in enumerate(ag3):
    card(C3 + 22, y3 + 142 + i * 82, COLW - 44, 70, nm, sb, ic, cc, fs=16)
card(C3 + 22, y3 + 476, COLW - 44, 88, "DuckDB  ·  Fixer  ·  ChartRecommender",
     "read-only SQL · fixed repair strategies · chart specs", "gear", ENG, fs=16)
rrect(C3 + 22, y3 + 588, COLW - 44, 106, 9, "#FFFFFF", BD, 1.4)
txt(C3 + 42, y3 + 616, "Every change loops back", 16.5, BLUE_DK, 700)
para(C3 + 42, y3 + 640, "A fix, an edit or a new rule rewrites the working copy and re-triggers "
                        "step 5, so the score is never stale.", COLW - 84, 14, INK2)
flow([(C3 + COLW / 2, y3 + 108), (C3 + COLW / 2, y3 + 140)], "9")
flow([(C3 + COLW / 2, y3 + 452), (C3 + COLW / 2, y3 + 474)], "10")

# --- AI rail
ry = COL_Y + 54
card(RAILX + 22, ry, RAILW - 44, 96, "Groq LLM", "langchain-groq · single client", "sparkle", AI,
     fs=18)
rrect(RAILX + 22, ry + 120, RAILW - 44, 250, 9, "#FFFFFF", AI, 1.4)
txt(RAILX + 42, ry + 148, "Called for", 15, AI, 700)
for i, t in enumerate(["Governance descriptions", "Issue explanations", "Data story",
                       "Rule from a sentence", "Chat plan + narration", "Dashboard command"]):
    txt(RAILX + 42, ry + 176 + i * 27, "· " + t, 14.5, INK2)
rrect(RAILX + 22, ry + 390, RAILW - 44, 176, 9, "#FFFFFF", AI, 1.4)
txt(RAILX + 42, ry + 418, "Never called for", 15, AI, 700)
for i, t in enumerate(["The quality score", "The classification", "What a fix changes",
                       "Manual cell edits"]):
    txt(RAILX + 42, ry + 446 + i * 27, "· " + t, 14.5, INK2)
rrect(RAILX + 22, ry + 586, RAILW - 44, 108, 9, AI_BG, AI, 1.6)
txt(RAILX + 42, ry + 614, "If it is unavailable", 15.5, AI, 700)
para(RAILX + 42, ry + 638, "Every path above falls back to fixed code. Nothing in the product "
                           "becomes unusable.", RAILW - 84, 14, INK2)
# Governance agent -> LLM: down the col2/col3 gutter, along the floor lane, up to the card.
flow([(C2 + COLW - 42, y2 + 390), (C2 + COLW + 18, y2 + 390), (C2 + COLW + 18, LANE_Y),
      (RAILX - 20, LANE_Y), (RAILX - 20, ry + 48), (RAILX + 22, ry + 48)], "7", AI, dash=True)
# Interactive paths that call the model: short hops straight into "Called for".
for hy in (y3 + 259, y3 + 341):
    flow([(C3 + COLW - 22, hy), (RAILX + 22, hy)], None, AI, 2.2, True)

# ------------------------------------------------------------ storage band ---
boundary(M, STO_Y, CWID, STO_H, "STORAGE", STO, STO_BG)
sw_ = (CWID - 48 - 2 * 30) / 3
sto = [("Original uploads", "data/uploads/", "Exact copy of what was sent. Proof only — never "
        "read again, never changed.", "file"),
       ("Working copy", "data/parquet/<id>.parquet", "Columnar. Every read, query and rewrite "
        "goes through this file.", "cube"),
       ("Catalogue", "SQLite", "Datasets, findings, fixes, edits, rules, chat, history. Facts "
        "about the data — never the rows.", "db")]
for i, (nm, path, note, ic) in enumerate(sto):
    sx = M + 24 + i * (sw_ + 30)
    rrect(sx, STO_Y + 54, sw_, 150, 10, "#FFFFFF", STO, 1.6)
    e(icon(ic, sx + 34, STO_Y + 84, 25, STO))
    txt(sx + 58, STO_Y + 90, nm, 17.5, INK, 700)
    rrect(sx + 20, STO_Y + 104, sw_ - 40, 30, 6, STO_BG, "#E8C48A", 1.2)
    txt(sx + 32, STO_Y + 124, path, 14.5, STO, 600, fam="Consolas, monospace")
    para(sx + 20, STO_Y + 158, note, sw_ - 40, 14, INK2)

for cx_ in (C1 + COLW / 2 - 60, C2 + COLW / 2 - 60, C3 + COLW / 2 - 60):
    flow([(cx_, COL_Y + COL_H), (cx_, STO_Y)], None, STO)
txt(C1 + COLW / 2 - 50, COL_Y + COL_H + 40, "writes", 14, STO, 600)
# the working copy is read back by every later step
wcx = M + 24 + sw_ + 30 + sw_ / 2 + 60
flow([(wcx, STO_Y), (wcx, COL_Y + COL_H)], None, MUTE, 2.2, True)
txt(wcx + 12, COL_Y + COL_H + 40, "read back", 14, MUTE, 600)

# client -> ingest
flow([(M + 174, CLI_Y + CLI_H), (M + 174, COL_Y - 16), (C1 + COLW / 2, COL_Y - 16),
      (C1 + COLW / 2, COL_Y + 52)], "1")
# tabs read back
flow([(C3 + COLW / 2 + 200, COL_Y), (C3 + COLW / 2 + 200, CLI_Y + CLI_H)], "11", MUTE, 2.2, True)

# ---------------------------------------------------------------- dataflow ---
e(f'<path d="M{M} {DF_Y} H{W-M}" stroke="{RULE}" stroke-width="1.6"/>')
txt(M, DF_Y + 36, "Dataflow", 24, INK, 700)
txt(M + 140, DF_Y + 36, "the numbered path above, in order", 16, INK2)
steps = [
    ("1", "A user drops a file into the workspace. Anything not in the allowed formats, over "
          "50 MB or empty is refused before a row is read."),
    ("2", "The upload endpoint hands the bytes to the UploadAgent."),
    ("3", "DataLoader detects the encoding and, for CSVs, the real separator, then parses to a "
          "table. Column names are tidied so they can be stored."),
    ("4", "Three writes: the original file for provenance, the columnar working copy, and the "
          "facts about the file in SQLite."),
    ("5", "Analysis is triggered automatically. SimpleCoordinator runs the three agents in order "
          "over one shared context, isolating any failure."),
    ("6", "The profiling and quality agents call the deterministic engines — types, statistics, "
          "20+ checks and the weighted six-part score."),
    ("7", "Only the governance agent calls the LLM, and only to write descriptions and rationale. "
          "The classification itself is decided by rules."),
    ("8", "Your saved rules are applied, ignored issues removed, the score recalculated and "
          "everything persisted. Under 75 it waits for human approval."),
    ("9", "From the tabs, the user fixes an issue, drafts a rule, asks a question or requests a "
          "widget."),
    ("10", "Those paths use DuckDB read-only, the fixed repair strategies, or the chart "
           "recommender. A fix rewrites the working copy and re-triggers step 5."),
    ("11", "Every tab reads back what was already computed, so the pages open instantly and cost "
           "nothing."),
]
colw = (CWID - 2 * 40) / 3
per = 4
cy0 = DF_Y + 74
for i, (n, t) in enumerate(steps):
    cx = M + (i // per) * (colw + 40)
    ry_ = cy0 + (i % per) * 82
    e(f'<circle cx="{cx+17}" cy="{ry_+13}" r="14" fill="{BLUE}"/>')
    txt(cx + 17, ry_ + 18.5, n, 14, "#FFFFFF", 700, "middle")
    para(cx + 44, ry_ + 18, t, colw - 54, 14.5, INK2, 400, 19.5)

TOTAL = int(cy0 + per * 82 + 40)
svg = "\n".join(out).replace("__H__", str(TOTAL))
open("wf.svg", "w", encoding="utf-8").write(svg)
open("wf.html", "w", encoding="utf-8").write(
    '<!doctype html><meta charset="utf-8">'
    '<style>html,body{margin:0;padding:0;background:#fff}</style>' + svg)
print(f"OK  {W}x{TOTAL}")
