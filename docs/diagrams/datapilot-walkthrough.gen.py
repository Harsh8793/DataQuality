"""DataPilot AI walkthrough: upload -> analysis -> every tab, manual vs AI.

Each step carries an AI / RULE badge so it is obvious where the model is used
and where the answer is computed deterministically.
"""
from __future__ import annotations

import html

BLUE = "#0F6CBD"
BLUE_DK = "#0A4C86"
AI = "#7A4FBF"
AI_BG = "#FAF7FE"
MAN = "#3C6E71"
MAN_BG = "#F4F9F9"
RULEC = "#5B6670"
STORE = "#0F7B8A"
STORE_BG = "#F2FAFB"
GATE = "#B4690E"
GATE_BG = "#FFF9F0"
INK = "#1B1A19"
INK2 = "#4A4845"
MUTE = "#7A7875"
BD = "#DCDAD8"
BD_BLUE = "#BFDCF2"
BAND = "#F7FAFD"
RULE_LN = "#E6E4E2"

W = 2600
M = 60
CW = W - 2 * M

out: list[str] = []
def e(s): out.append(s)
def esc(s): return html.escape(str(s), quote=True)


def txt(x, y, s, fs=16, col=INK, wt=400, anchor="start", ls=0.0):
    e(f'<text x="{x}" y="{y}" font-family="Segoe UI, Arial, sans-serif" font-size="{fs}" '
      f'font-weight="{wt}" fill="{col}" text-anchor="{anchor}" letter-spacing="{ls}">{esc(s)}</text>')


def wrap(s, width, fs):
    limit = max(1, int(width / (fs * 0.515)))
    words, lines, cur = s.split(), [], ""
    for w_ in words:
        t = f"{cur} {w_}".strip()
        if len(t) <= limit:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = w_
    if cur: lines.append(cur)
    return lines


def para(x, y, s, width, fs=15, col=INK2, wt=400, lh=20.5):
    ls = wrap(s, width, fs)
    for i, ln in enumerate(ls):
        txt(x, y + i * lh, ln, fs, col, wt)
    return len(ls) * lh


def rrect(x, y, w, h, r=10, fill="#FFFFFF", stroke=BD, sw=1.4):
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
      f'stroke="{stroke}" stroke-width="{sw}"/>')


def numdot(cx, cy, n, col=BLUE, r=14):
    e(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}"/>')
    txt(cx, cy + 5.5, n, 14.5, "#FFFFFF", 700, "middle")


def tag(x, y, label, col, fs=12.5, h=24):
    tw = len(label) * (fs * 0.63) + 22
    e(f'<rect x="{x}" y="{y}" width="{tw}" height="{h}" rx="{h/2}" fill="{col}"/>')
    txt(x + tw / 2, y + h / 2 + 4.6, label, fs, "#FFFFFF", 700, "middle", 0.9)
    return tw


def otag(x, y, label, col, fs=11.5, h=21):
    tw = len(label) * (fs * 0.66) + 18
    e(f'<rect x="{x}" y="{y}" width="{tw}" height="{h}" rx="{h/2}" fill="#FFFFFF" '
      f'stroke="{col}" stroke-width="1.3"/>')
    txt(x + tw / 2, y + h / 2 + 4.2, label, fs, col, 700, "middle", 0.7)
    return tw


def arrow(pts, col=BLUE, sw=2.6, label=None):
    d = f'M{pts[0][0]} {pts[0][1]}' + "".join(f' L{a} {b}' for a, b in pts[1:])
    e(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linejoin="round" '
      f'stroke-linecap="round" marker-end="url(#a{col.lstrip("#")})"/>')
    if label:
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        tw = len(label) * 7.6 + 20
        rrect(mx + 16, my - 12, tw, 24, 12, "#FFFFFF", BD_BLUE, 1)
        txt(mx + 16 + tw / 2, my + 4.5, label, 13, BLUE_DK, 600, "middle")


# ------------------------------------------------------------ steps/panels ---
def step_h(detail, width, kind=None):
    return 27 + len(wrap(detail, width - 96, 15)) * 20.5 + 15


def draw_step(x, y, w, n, title, detail, col=BLUE, kind=None):
    numdot(x + 20, y + 13, n, col)
    tw = len(title) * 9.2
    txt(x + 48, y + 19, title, 17, INK, 600)
    if kind == "ai":
        otag(x + 54 + tw, y + 3, "AI", AI)
    elif kind == "rule":
        otag(x + 54 + tw, y + 3, "RULE", RULEC)
    h = 27
    if detail:
        h += para(x + 48, y + 44, detail, w - 96, 15, INK2)
    return h + 15


def panel_h(w, steps, writes=None, cols=1, head=92):
    inner = (w - 34) / cols if cols > 1 else w
    per = -(-len(steps) // cols)
    groups = [steps[i * per:(i + 1) * per] for i in range(cols)]
    body = max(sum(step_h(s[1], inner) for s in g) for g in groups if g)
    return head + body + (46 if writes else 14)


def panel(x, y, w, name, sub, steps, writes=None, col=AI, bg=AI_BG, badge="AI AGENT",
          cols=1, min_h=0):
    head = 92
    inner = (w - 34) / cols if cols > 1 else w
    per = -(-len(steps) // cols)
    groups = [steps[i * per:(i + 1) * per] for i in range(cols)]
    body = max(sum(step_h(s[1], inner) for s in g) for g in groups if g)
    foot = 46 if writes else 14
    h = max(head + body + foot, min_h)
    body = h - head - foot

    rrect(x, y, w, h, 12, bg, col, 2.0)
    tw = tag(x + 20, y + 18, badge, col)
    txt(x + 20 + tw + 14, y + 37, name, 21, INK, 700)
    txt(x + 20, y + 76, sub, 14.5, col, 600)
    e(f'<path d="M{x+20} {y+head-8} H{x+w-20}" stroke="{col}" stroke-width="1" opacity="0.35"/>')
    for ci in range(cols):
        cy = y + head
        cx = x + ci * (inner + 34)
        for si, s in enumerate(groups[ci]):
            t, d = s[0], s[1]
            k = s[2] if len(s) > 2 else None
            cy += draw_step(cx, cy, inner, ci * per + si + 1, t, d, col, k)
        if ci < cols - 1:
            e(f'<path d="M{cx+inner+17} {y+head} V{y+head+body}" stroke="{col}" '
              f'stroke-width="1" opacity="0.28"/>')
    if writes:
        wy = y + h - 34
        e(f'<path d="M{x+20} {wy-14} H{x+w-20}" stroke="{col}" stroke-width="1" opacity="0.35"/>')
        txt(x + 20, wy + 8, writes, 15, col, 700)
    return h


def manual_h(w, bullets, note=None):
    h = 84
    for b in bullets:
        h += len(wrap(b, w - 72, 16)) * 22 + 14
    if note:
        h += len(wrap(note, w - 56, 14.5)) * 19.5 + 18
    return h + 14


def manual(x, y, w, bullets, note=None, min_h=0):
    h = max(manual_h(w, bullets, note), min_h)
    rrect(x, y, w, h, 12, MAN_BG, MAN, 2.0)
    tw = tag(x + 20, y + 18, "MANUAL", MAN)
    txt(x + 20 + tw + 14, y + 37, "What you do by hand", 19, INK, 700)
    e(f'<path d="M{x+20} {y+62} H{x+w-20}" stroke="{MAN}" stroke-width="1" opacity="0.35"/>')
    cy = y + 84
    for b in bullets:
        e(f'<circle cx="{x+30}" cy="{cy-5}" r="3.6" fill="{MAN}"/>')
        cy += para(x + 46, cy, b, w - 72, 16, INK, 400, 22) + 14
    if note:
        cy += 4
        para(x + 28, cy, note, w - 56, 14.5, MUTE, 400, 19.5)
    return h


def store(x, y, w, name, path, note):
    h = 132
    rrect(x, y, w, h, 11, STORE_BG, STORE, 1.8)
    txt(x + 20, y + 32, name, 17.5, INK, 700)
    rrect(x + 20, y + 46, w - 40, 30, 6, "#FFFFFF", "#CFE7EA", 1.2)
    txt(x + 32, y + 66, path, 14.5, STORE, 600)
    para(x + 20, y + 100, note, w - 40, 14, INK2)
    return h


def gate(x, y, w, title, body, min_h=0):
    lines = wrap(body, w - 70, 15.5)
    h = max(58 + len(lines) * 21 + 22, min_h)
    rrect(x, y, w, h, 11, GATE_BG, GATE, 2.0)
    e(f'<path d="M{x} {y} h12 v{h} h-12 z" fill="{GATE}" opacity="0.9"/>')
    tw = tag(x + 32, y + 18, "YOUR DECISION", GATE)
    txt(x + 32 + tw + 16, y + 37, title, 18.5, INK, 700)
    for i, ln in enumerate(lines):
        txt(x + 32, y + 76 + i * 21, ln, 15.5, INK2)
    return h


def chips(x, y, w, items, per_row, col=BLUE, ch=64, fs=15.5):
    gap = 20
    cwid = (w - (per_row - 1) * gap) / per_row
    rows = -(-len(items) // per_row)
    for i, it in enumerate(items):
        cx = x + (i % per_row) * (cwid + gap)
        cy = y + (i // per_row) * (ch + gap)
        rrect(cx, cy, cwid, ch, 8)
        e(f'<rect x="{cx}" y="{cy}" width="4" height="{ch}" rx="2" fill="{col}"/>')
        ls = wrap(it, cwid - 34, fs)
        ty = cy + ch / 2 - (len(ls) - 1) * 9 + 5.5
        for j, ln in enumerate(ls):
            txt(cx + 18, ty + j * 19, ln, fs, INK, 600)
    return rows * ch + (rows - 1) * gap


# ------------------------------------------------------------------- bands ---
def band_open(): return len(out)


def band_close(mark, y, h, num, title, sub, api, kind="STAGE"):
    col = BLUE if kind == "STAGE" else "#2B579A"
    s = (f'<rect x="{M}" y="{y}" width="{CW}" height="{h}" rx="16" fill="{BAND}" '
         f'stroke="{BD_BLUE}" stroke-width="1.6"/>'
         f'<rect x="{M}" y="{y}" width="9" height="{h}" rx="4.5" fill="{col}"/>')
    if kind == "STAGE":
        s += (f'<circle cx="{M+66}" cy="{y+56}" r="30" fill="{col}"/>'
              f'<text x="{M+66}" y="{y+67}" font-family="Segoe UI, Arial, sans-serif" '
              f'font-size="30" font-weight="700" fill="#FFFFFF" text-anchor="middle">{num}</text>')
        tx = M + 114
    else:
        s += (f'<rect x="{M+34}" y="{y+34}" width="128" height="42" rx="10" fill="{col}"/>'
              f'<text x="{M+98}" y="{y+62}" font-family="Segoe UI, Arial, sans-serif" '
              f'font-size="16" font-weight="700" fill="#FFFFFF" text-anchor="middle" '
              f'letter-spacing="1.2">TAB {num}</text>')
        tx = M + 186
    s += (f'<text x="{tx}" y="{y+50}" font-family="Segoe UI, Arial, sans-serif" font-size="26" '
          f'font-weight="700" fill="{INK}">{esc(title)}</text>'
          f'<text x="{tx}" y="{y+78}" font-family="Segoe UI, Arial, sans-serif" font-size="16" '
          f'fill="{INK2}">{esc(sub)}</text>')
    if api:
        tw = len(api) * 9.2 + 30
        s += (f'<rect x="{W-M-20-tw}" y="{y+34}" width="{tw}" height="34" rx="8" fill="#FFFFFF" '
              f'stroke="{BD_BLUE}" stroke-width="1.3"/>'
              f'<text x="{W-M-20-tw/2}" y="{y+56}" font-family="Consolas, monospace" '
              f'font-size="15" font-weight="600" fill="{BLUE_DK}" text-anchor="middle">'
              f'{esc(api)}</text>')
    out.insert(mark, s)


# =============================================================== document ====
e(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="__H__" '
  f'viewBox="0 0 {W} __H__" font-family="Segoe UI, Arial, sans-serif">')
e('<defs>')
for c in (BLUE, AI, STORE, GATE, MAN, MUTE):
    e(f'<marker id="a{c.lstrip("#")}" viewBox="0 0 12 12" refX="9.5" refY="6" markerWidth="8" '
      f'markerHeight="8" orient="auto-start-reverse">'
      f'<path d="M1 1.6 L10.5 6 L1 10.4 z" fill="{c}"/></marker>')
e('</defs>')
e('<rect width="100%" height="100%" fill="#FFFFFF"/>')

e(f'<rect x="{M}" y="46" width="7" height="62" rx="3.5" fill="{BLUE}"/>')
txt(M + 26, 80, "DataPilot AI — how it works, tab by tab", 40, INK, 700)
txt(M + 26, 112, "Upload, automatic analysis, then what you do by hand versus what the AI does "
                 "— for every tab up to Governance.", 19, INK2)
txt(W - M, 80, "Walkthrough diagram", 17, INK2, 600, "end")
txt(W - M, 106, "Read from the backend source", 15, MUTE, 400, "end")

# legend
lx = M
ly = 132
rrect(lx, ly, CW, 62, 10, "#FFFFFF", BD_BLUE, 1.5)
txt(lx + 24, ly + 38, "How to read this", 16, BLUE, 700)
px = lx + 190
tw = otag(px, ly + 20, "AI", AI); px += tw + 10
txt(px, ly + 38, "the AI model is called for this step", 15.5, INK2); px += 300
tw = otag(px, ly + 20, "RULE", RULEC); px += tw + 10
txt(px, ly + 38, "fixed code decides — same answer every time, no tokens", 15.5, INK2); px += 440
tw = tag(px, ly + 19, "MANUAL", MAN); px += tw + 10
txt(px, ly + 38, "you do it", 15.5, INK2); px += 130
tw = tag(px, ly + 19, "YOUR DECISION", GATE); px += tw + 10
txt(px, ly + 38, "nothing proceeds until you approve", 15.5, INK2)

y = 232
CX = W / 2

# ============================================================== STAGE 1 =====
mk = band_open()
cy = y + 110
rrect(M + 20, cy, CW - 40, 88, 11, "#FFFFFF", BD_BLUE, 1.6)
txt(M + 44, cy + 34, "Accepted input", 16, BLUE, 700)
fx = M + 210
for f_ in [".csv", ".xlsx", ".xls", ".json", ".parquet"]:
    tw = len(f_) * 11 + 30
    rrect(fx, cy + 18, tw, 34, 8, "#F2F8FD", BD_BLUE, 1.2)
    txt(fx + tw / 2, cy + 41, f_, 16, BLUE_DK, 700, "middle")
    fx += tw + 14
txt(fx + 16, cy + 41, "· max 50 MB · rejected if empty or the extension isn't allowed", 15, INK2)
cy += 88 + 34

s1 = [
    ("Check the file", "The extension must be allowed, the size must be under 50 MB and the file "
                       "must not be empty. Anything else is refused before a single row is read.",
     "rule"),
    ("Work out the format, then read it", "The encoding is detected from the first 100 KB. For a "
     "CSV the real separator is found by testing comma, semicolon, pipe, tab and tilde. Excel, "
     "JSON and Parquet use their own reader.", "rule"),
    ("Tidy the column names", "Spaces are trimmed and repeated names are made unique, so the "
     "table can be stored safely.", "rule"),
]
h = panel(M + 20, cy, CW - 40, "Reading the upload", "No AI here — this is all fixed code",
          s1, col=BLUE, bg="#F9FCFE", badge="BACKEND")
cy += h + 38
txt(M + 20, cy + 6, "The same upload is then written to three places, each with a different job:",
    17, INK, 600)
cy += 30
c3 = (CW - 40 - 2 * 24) / 3
store(M + 20, cy, c3, "1 · Your original file", "data/uploads/…",
      "An exact copy, kept only as proof of what you sent. Never changed, never read again.")
store(M + 20 + c3 + 24, cy, c3, "2 · The working copy", "data/parquet/<id>.parquet",
      "A fast columnar version. Everything from here on reads and rewrites this file.")
h = store(M + 20 + 2 * (c3 + 24), cy, c3, "3 · The record of it", "SQLite database",
          "Format, encoding, separator, row and column counts. Facts about the file — never the "
          "rows themselves.")
cy += h + 26
txt(M + 20, cy + 12, "Analysis then starts on its own — you don't have to press anything.",
    16.5, BLUE_DK, 700)
cy += 34
H = cy - y
band_close(mk, y, H, 1, "You upload a file", "Drag and drop, any of the formats below",
           "POST /api/v1/datasets")
y += H
arrow([(CX, y + 8), (CX, y + 62)], label="the working copy is the input from here on")
y += 70

# ============================================================== STAGE 2 =====
mk = band_open()
cy = y + 110
rrect(M + 20, cy, CW - 40, 118, 11, "#FFFFFF", BD_BLUE, 1.6)
txt(M + 44, cy + 36, "Three AI agents run in order, one after another", 18.5, INK, 700)
para(M + 44, cy + 62, "They share a single working memory: each agent reads what the one before "
                      "it worked out and adds its own findings. If an agent fails, only that "
                      "agent's part is missing — the rest still completes. This is where the "
                      "score, the issue list and the sensitivity classification come from.",
     CW - 100, 15.5, INK2)
cy += 118 + 32

pw = (CW - 40 - 2 * 30) / 3
a1 = [
    ("Open the working copy", "Load the stored table into memory.", "rule"),
    ("Work out each column's basic type", "Number, text, date, true/false.", "rule"),
    ("Work out what each column means", "14 business types are recognised — email, phone, "
     "postcode, web address, latitude/longitude, money, date, ID, category — from the shape of "
     "the values plus the column's name.", "rule"),
    ("Measure every column", "How much is missing, how many different values, smallest, largest, "
     "average, and a few real examples.", "rule"),
]
a2 = [
    ("Run every check", "Over 20 independent checks look for missing values, blanks, duplicate "
     "rows and columns, columns that never change, too many or too few distinct values, badly "
     "formed emails, phones, web addresses and dates, unexpected negatives, stray spaces, "
     "inconsistent capitalisation and outliers.", "rule"),
    ("Record what each check found", "Which column, how serious, how many rows, and which of the "
     "six quality areas it damages.", "rule"),
    ("Score each of the six areas", "Every area starts at 100 and loses points based on how "
     "serious the problem is and how much of the table it affects.", "rule"),
    ("Combine into one score", "Completeness 25% · Validity 20% · Uniqueness 15% · Consistency "
     "15% · Accuracy 15% · Integrity 10% — giving the headline number out of 100.", "rule"),
]
a3 = [
    ("Look for sensitive columns", "Column names and detected meanings are matched against "
     "personal, financial and health patterns.", "rule"),
    ("Decide the classification and tier", "Fixed rules make this call, so it is identical on "
     "every run and can be defended in an audit. The AI is not allowed to change it.", "rule"),
    ("Ask the AI to write the human layer", "The AI supplies business-friendly column names, "
     "one-line descriptions and the wording that explains the classification. Columns go in "
     "batches of 20 to keep the cost down.", "ai"),
    ("Carry on without it if needed", "If the AI is unavailable or returns something unusable, "
     "the rule-based result is kept exactly as it is.", "rule"),
]
hmax = max(panel_h(pw, a1, 1), panel_h(pw, a2, 1), panel_h(pw, a3, 1))
panel(M + 20, cy, pw, "Agent 1 · Profiling", "Understands the shape of your data", a1,
      "result → what every column is and contains", min_h=hmax)
panel(M + 20 + pw + 30, cy, pw, "Agent 2 · Quality", "Finds the problems and scores them", a2,
      "result → the issue list and the 0-100 score", min_h=hmax)
panel(M + 20 + 2 * (pw + 30), cy, pw, "Agent 3 · Governance",
      "Judges sensitivity — the only AI call here", a3,
      "result → classification, personal-data list, tier", min_h=hmax)
for i in range(2):
    ax = M + 20 + (i + 1) * pw + i * 30 + 6
    arrow([(ax, cy + hmax / 2), (ax + 18, cy + hmax / 2)], AI, 2.4)
cy += hmax + 34

rrect(M + 20, cy, CW - 40, 96, 11, "#FFFFFF", AI, 1.8)
tw = tag(M + 44, cy + 20, "WHERE THE AI IS USED", AI)
txt(M + 44 + tw + 16, cy + 38, "Only one step in this whole stage calls the model", 18, INK, 700)
para(M + 44, cy + 62, "Agent 3 asks the AI to write the descriptions and the explanation text. "
                      "Everything else — the types, the checks and the score — is fixed code, on "
                      "purpose: the same file must always produce the same score, it has to stand "
                      "up to an audit, and re-analysis runs after every fix and edit so it needs "
                      "to be free and instant.", CW - 100, 15.5, INK2)
cy += 96 + 30

h = chips(M + 20, cy, CW - 40,
          ["Your own saved rules are run and added to the issue list",
           "Issues you chose to ignore are removed", "The score is recalculated",
           "Everything is saved so the tabs can just read it"], 4, BLUE, 74)
cy += h + 30
h = gate(M + 20, cy, CW - 40, "Approve the dataset",
         "Score 75 or above and it is cleared automatically. Below 75 and it is marked as needing "
         "review — the app shows a banner with Approve and Reject, and until someone chooses, the "
         "dataset is not treated as fit to use.")
cy += h + 30
H = cy - y
band_close(mk, y, H, 2, "The app analyses it automatically",
           "No clicks needed. This also re-runs after every fix, edit or new rule",
           "POST /datasets/{id}/analyze")
y += H
arrow([(CX, y + 8), (CX, y + 62)], label="now you open the dataset and work through the tabs")
y += 76

# ================================================================== TABS =====
MANW = 660
AIW = CW - 40 - MANW - 30
AIX = M + 20 + MANW + 30


def tab(num, name, sub, api, bullets, note, ai_panels, last=False):
    """One tab band: narrow manual column, wide AI column with stacked panels."""
    global y
    mk = band_open()
    cy = y + 110
    ai_total = sum(panel_h(AIW, s, wr, c) for _, _, s, wr, c in ai_panels) \
        + 26 * (len(ai_panels) - 1)
    mh = max(manual_h(MANW, bullets, note), ai_total)
    manual(M + 20, cy, MANW, bullets, note, min_h=mh)
    ay = cy
    for pname, psub, psteps, pwrites, pcols in ai_panels:
        ph = panel(AIX, ay, AIW, pname, psub, psteps, pwrites, cols=pcols)
        ay += ph + 26
    cy += mh + 30
    H = cy - y
    band_close(mk, y, H, num, name, sub, api, kind="TAB")
    y += H
    if not last:
        arrow([(CX, y + 8), (CX, y + 58)])
        y += 66


# ---- TAB 1 · Overview
tab(1, "Overview", "You read what the dataset actually contains before touching anything",
    "GET /datasets/{id} · /profile · /preview · /story",
    ["Read the row and column counts, the format, encoding and separator that were detected.",
     "Scan the column list with each column's detected meaning and how much of it is missing.",
     "Page through the real rows, 50 at a time.",
     "Decide whether this is even the right file before doing any work on it."],
    "None of this recalculates anything — it is all read back from Stage 2, so the page opens "
    "instantly.",
    [("Data story", "Writes a plain-English summary of the dataset", [
        ("You open the tab", "The story is requested once, in the background.", "rule"),
        ("The AI is given a summary, not your rows", "It receives the column names, their "
         "detected meanings, the row count and the quality score. The actual data values are "
         "not sent, so nothing sensitive leaves the app.", "rule"),
        ("The AI writes the description", "A few sentences on what this dataset appears to be "
         "about, what the important columns mean, and what stands out as unusual.", "ai"),
        ("It is saved for next time", "The story is stored on the dataset, so it is written "
         "once. Every later visit is instant and costs nothing. You can force a rewrite if the "
         "data has changed a lot.", "rule"),
        ("If the AI is unavailable", "You still get a summary — assembled from the numbers "
         "instead of written as prose.", "rule"),
    ], "you get → a short readable description of the dataset", 1)])

# ---- TAB 2 · Quality
tab(2, "Quality", "You see the score and the problems, then either write your own rule or let "
                  "the AI fix an issue", "GET /datasets/{id}/quality",
    ["Read the overall score and the six area bars.",
     "Filter the issue list by status or severity.",
     "Open an issue to see the affected rows.",
     "Mark an issue as ignored if it is acceptable for your use — it stops counting against the "
     "score and can be brought back at any time.",
     "Approve or reject the dataset."],
    "Every issue already comes with a written explanation produced by fixed code, which is why "
    "this page never waits for the AI.",
    [("Explaining an issue", "Turns a finding into something you can act on", [
        ("You ask for more detail on an issue", "The built-in explanation is shown immediately; "
         "the AI version is only fetched if you want it.", "rule"),
        ("The AI is given the finding, not the data", "It sees the check name, the column, the "
         "severity and how many rows are affected — never the row values.", "rule"),
        ("The AI writes four things", "What is wrong, why it usually happens, what it costs you "
         "in practice, and what to do about it.", "ai"),
        ("Anything it cannot explain", "Falls back to the standard wording for that check, so "
         "there is never a blank explanation.", "rule"),
    ], None, 1),
     ("Your own rule, written in English", "You describe the rule — the AI only translates it", [
         ("You type the rule normally", 'For example "salary should never be negative" or '
          '"order date cannot be in the future".', "rule"),
         ("The AI turns it into a real condition", "It converts your sentence into something the "
          "app can actually run against the data. Nothing has run yet.", "ai"),
         ("It is tested, read-only", "The condition is run against the working copy and reports "
          "how many rows break the rule, with up to 10 real examples.", "rule"),
         ("If it doesn't work, it is repaired", "Type mismatches are corrected automatically and "
          "retried. If it still fails, the AI gets exactly one attempt to fix it.", "ai"),
         ("You see the result before anything is saved", 'It shows "this flags N of M rows" with '
          "the examples, so you can judge whether the rule is right.", "rule"),
         ("You approve it — or it is discarded", "Only on approval is the rule stored, and from "
          "then on it runs inside every future analysis. Reject and nothing is kept.", "rule"),
     ], "you get → a permanent check of your own, in your words", 1),
     ("One-click fix", "The AI decides nothing here — the change is a fixed rule", [
         ("You click Fix on an issue", "Or Fix all, which does every fixable issue as one batch.",
          "rule"),
         ("Only known-safe fixes are allowed", "If the issue has no proven fix, the request is "
          "refused and you are pointed at cleaning instead. Nothing is improvised.", "rule"),
         ("An undo point is created first", "Before anything changes, so it can always be put "
          "back.", "rule"),
         ("The change follows a fixed rule", "Missing numbers become the middle value, missing "
          "text becomes the most common value, stray spaces are trimmed, duplicate rows are "
          "dropped. The AI is not asked what to change.", "rule"),
         ("Every changed cell is recorded", "The before and after value of each one, so the edit "
          "is fully traceable.", "rule"),
         ("The dataset is re-analysed", "The whole of Stage 2 runs again, so you immediately see "
          "the new score and what is left.", "rule"),
         ("You can undo any of it", "One fix, a whole batch, or everything.", "rule"),
     ], "you get → a corrected dataset, a new score, and a full audit trail", 2)])

# ---- TAB 3 · Edit data
tab(3, "Edit data", "You correct individual values yourself", "POST /datasets/{id}/edits",
    ["Filter down to the rows you care about.",
     "Click a cell and type the correct value.",
     "Save the changes.",
     "Undo the last edit if you got it wrong."],
    "Edits are treated exactly like a fix: snapshotted first, recorded cell by cell, and followed "
    "by a re-analysis.",
    [("No AI on this tab", "Deliberately — your corrections are yours", [
        ("Nothing is suggested or auto-filled", "The app does not guess what you meant or "
         "propose replacement values. What you type is what is stored.", "rule"),
        ("But it is still protected", "An undo point is taken before the edit, every changed cell "
         "is recorded with its old and new value, and the score is recalculated afterwards — the "
         "same safety net the fix agent gets.", "rule"),
        ("Why it works this way", "A manual edit is a statement of fact about your business that "
         "only you can make. Letting a model influence it would quietly put guesses into data you "
         "believe you verified by hand.", "rule"),
    ], None, 1)])

# ---- TAB 4 · Dashboard
tab(4, "Dashboard", "You get a dashboard without building one, then ask for extra widgets in "
                    "words", "GET /datasets/{id}/dashboard · POST /dashboard/command",
    ["Read the KPIs and charts that were chosen for you.",
     "Tick which ones you want to keep — your selection is saved.",
     "Accept or reject any widget the AI proposes.",
     "Ask a widget to explain itself."],
    "The starting dashboard involves no AI at all — it is built from what Stage 2 already worked "
    "out about your columns.",
    [("Building the default dashboard", "Chosen by rules, from the column types", [
        ("Candidate widgets are worked out", "Using each column's detected meaning, the app lists "
         "every KPI and chart the data could genuinely support.", "rule"),
        ("A sensible default set is picked", "So the tab is useful the moment you open it, with "
         "no prompting and no waiting.", "rule"),
        ("Charts only get valid columns", "A total needs a number, a trend needs a date, a "
         "breakdown needs a category. Impossible combinations are never offered.", "rule"),
    ], None, 1),
     ("Asking for a widget in words", "You describe it — the AI plans it, you confirm it", [
         ("You type what you want", 'For example "average revenue by state" or "spend vs units".',
          "rule"),
         ("Your column names are checked first", "If nothing in your request matches a real "
          "column, it stops and says so rather than charting something unrelated. This is the "
          "guard that stops confident nonsense.", "rule"),
         ("If you named the chart type, you win", 'Saying "spend vs units" means a scatter plot, '
          "and your wording overrides the AI's guess.", "rule"),
         ("Otherwise the AI plans it", "It chooses which columns to use, which chart type and "
          "whether to total or average.", "ai"),
         ("The plan is checked against reality", "A chart the columns cannot support is thrown "
          "away and a simpler keyword method tries instead. If that also fails you get a clear "
          "refusal, not a broken chart.", "rule"),
         ("Near-misses are surfaced, not hidden", "If it matched a misspelt column to a real one, "
          "it tells you which substitution it made.", "rule"),
         ("It is proposed, never silently added", "You see the finished widget and choose whether "
          "to keep it.", "rule"),
     ], "you get → a widget you asked for in plain words, with the reasoning shown", 2)])

# ---- TAB 5 · Chat
tab(5, "Chat", "You ask questions about the data in plain English", "POST /datasets/{id}/chat",
    ["Type a question the way you would ask a colleague.",
     "Read the answer, the table behind it and the chart.",
     "Ask follow-ups — the conversation is remembered.",
     "Clear the history when you want a clean start."],
    "History is saved per dataset and restored when you come back, so follow-ups still make "
    "sense tomorrow.",
    [("Answering a question", "Understand, query, then explain — with a fallback at every step", [
        ("Obvious questions skip the AI", '"How many rows" is answered by counting them. "Give '
         "me insights\" goes straight to the summary generator. No model needed, no chance of a "
         "vague reply.", "rule"),
        ("The AI plans the answer", "It reads your question plus the last few turns of the "
         "conversation and decides whether this needs a query over the data or just a reply — "
          'so "now show that as a pie chart" still makes sense.', "ai"),
        ("The plan is sanity-checked", "If it came back with neither a query nor a real answer, "
         "or with a brush-off like \"please run a query yourself\", it is thrown away here. You "
         "never see those.", "rule"),
        ("A backup method takes over if needed", "The app assembles a query itself from the "
         "columns your question mentions and any filter it implies. This is what keeps Chat "
         "working when the AI is completely offline.", "rule"),
        ("The query runs read-only", "It can only read. Anything that would change or delete "
         "data is blocked, and a row limit is always applied — even if the model asked for it.",
         "rule"),
        ("One retry on failure", "If the planned query errors, the backup query runs instead so "
         "you still get an answer.", "rule"),
        ("A chart is chosen for the result", "Based on the shape of what came back, unless you "
         "asked for a specific type.", "rule"),
        ("The AI writes the explanation", "One or two sentences saying what the table actually "
         "shows, and the exchange is saved for your next question.", "ai"),
    ], "you get → a sentence, the table it came from, and a chart", 2)])

# ---- TAB 6 · Governance
tab(6, "Governance", "You see how sensitive this dataset is and how it should be handled",
    "GET /datasets/{id}/governance",
    ["Read the sensitivity classification and why it was given.",
     "Review the list of columns holding personal data.",
     "Read the recommended handling tier and the reasoning.",
     "Check the business description of each column.",
     "As a steward, approve or reject the dataset on this basis."],
    "This is the tab an auditor would ask to see, which is why the AI has the smallest possible "
    "role in it.",
    [("Classifying the dataset", "Rules make the decision — the AI only writes it up", [
        ("Sensitive columns are identified", "Column names and detected meanings are matched "
         "against known personal, financial and health patterns — names, contact details, "
         "identifiers, dates of birth, salary, account and card fields, medical terms.", "rule"),
        ("The classification is computed", "From what was found. Fixed rules, so the same "
         "dataset always produces the same answer and it can be explained line by line.", "rule"),
        ("The handling tier is recommended", "Based on the sensitivity and the size of the "
         "dataset. Also fixed rules.", "rule"),
        ("Only now is the AI involved", "It is asked to write the business-friendly column names, "
         "the one-line descriptions and the readable rationale. It cannot change the "
         "classification, the personal-data list or the tier — those are already decided.", "ai"),
        ("Columns are sent in batches of 20", "To stay inside the model's limits on wide tables, "
         "and to keep the cost predictable.", "rule"),
        ("If the AI fails, nothing is lost", "Unavailable, erroring or malformed output all lead "
         "to the same place: the rule-based result is kept exactly as computed. The compliance "
         "answer never depends on the model being up.", "rule"),
    ], "you get → a defensible classification, plus readable descriptions on top", 2)],
    last=True)

# ------------------------------------------------------------------ footer ---
y += 34
e(f'<path d="M{M} {y} H{W-M}" stroke="{RULE_LN}" stroke-width="1.6"/>')
y += 36
rules = [
    ("The AI never decides a number", "Scores, classifications and fixes are computed by rules, "
     "so they are repeatable."),
    ("The AI writes the words", "Descriptions, explanations, stories and narration — the parts "
     "where language is the point."),
    ("Your rows are rarely sent", "Most AI calls see only column names, types and counts — not "
     "the values."),
    ("It all works with the AI off", "Every AI step has a fixed-code fallback, so nothing becomes "
     "unusable."),
]
fw = (CW - 3 * 26) / 4
for i, (t, d) in enumerate(rules):
    fx = M + i * (fw + 26)
    e(f'<rect x="{fx}" y="{y}" width="4" height="72" rx="2" fill="{AI if i < 2 else BLUE}"/>')
    txt(fx + 18, y + 22, t, 16.5, INK, 700)
    para(fx + 18, y + 46, d, fw - 30, 14.5, INK2, 400, 19)
y += 72 + 40

TOTAL = int(y)
svg = "\n".join(out).replace("__H__", str(TOTAL))
open("flow2.svg", "w", encoding="utf-8").write(svg)
open("flow2.html", "w", encoding="utf-8").write(
    '<!doctype html><meta charset="utf-8">'
    '<style>html,body{margin:0;padding:0;background:#fff}</style>' + svg)
print(f"OK  {W}x{TOTAL}")
