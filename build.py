#!/usr/bin/env python3
"""
Build a static website from the Obsidian Arabic review notes.

Source of truth stays in the vault. This script only reads it.
Output goes to ./docs/ (GitHub Pages: Settings -> Pages -> main branch /docs).

Usage:  python3 build.py [--vault PATH]
"""
import argparse, html, json, pathlib, re, shutil, sys, unicodedata

DEFAULT_VAULT = pathlib.Path.home() / "Desktop/The Coordinate/School/Language Review/Arabic"
OUT = pathlib.Path(__file__).parent / "docs"

# ---------------------------------------------------------------- link routing
def slug_for(name: str):
    """Map an Obsidian note name to a site page, or None if it isn't published."""
    base = name.split("#")[0].split("|")[0].strip()
    if base.endswith(".md"):
        base = base[:-3]
    base = base.split("/")[-1].strip()
    if base.startswith("00 "):
        return "review.html"
    if base == "Vocab Bank":
        return "vocab.html"
    if base == "Grammar Bank":
        return "grammar.html"
    m = re.match(r"L(\d{2})\b", base)
    if m:
        return f"l{int(m.group(1)):02d}.html"
    return None  # Error Log, Cumulative Drill, Fill-in-the-Blank: not published

AR = re.compile(r"[؀-ۿݐ-ݿ]")
def is_rtl(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    ar = sum(1 for c in letters if AR.match(c))
    return ar / len(letters) > 0.4


# ---------------------------------------------------------------- depersonalise
# The vault notes are written to me, by my drill skill. Classmates need the study
# material without the private plumbing (Error Log, arabic-drill, SR scheduling).
DEPERSONALIZE = [
    # self-check "tick if wrong" -> a real checkbox, always starting unticked
    (r"- \[[ xX]\] \u274c tick if wrong \u2014 \*([^*]+)\*",
     '<div class="miss"><label><input type="checkbox" class="missbox"> mark if you missed it</label>'
     '<span class="qtag">\\1</span></div>', 0),
    # dated/numbered drill chip -> static label
    (r"\U0001F3B2 FRESH SET[^<]*", "\u25c6 SELF-CHECK", 0),
    # instruction line referencing the drill skill + private error log
    (r"Reveal each, then <b>tick the checkbox under it only if you got it wrong</b>\..*?harder set\.",
     "Reveal each answer, then tick the box under it if you got it wrong. Your tick count is "
     "tallied in the corner \u2014 whatever you miss is what to go back and review.", re.S),
    (r"\U0001F501 Ticked your misses\?.*?weakest\.",
     "\U0001F501 <b>Count your ticks.</b> Whatever you missed here is the part of this lesson that "
     "hasn\u2019t stuck yet \u2014 go back up to that section and redo it.", re.S),
    # overview page
    (r"For practice, say <b>[^<]*arabic-drill[^<]*</b>\.?",
     "Every word and rule is collected in the "
     "<a href=\"vocab.html\">Vocab</a> and <a href=\"grammar.html\">Grammar</a> banks.", 0),
    (r"Run <b>arabic-drill</b>[^<]*<a href=\"Error Log\"[^>]*>Error Log</a>[^<]*\.",
     "Drill the <a href=\"flashcards.html\">flashcards</a> 3\u20134\u00d7/week and let the words "
     "you keep missing steer you.", 0),
    (r"\u2014 drillable flashcards\. Adaptive: say <b>[^<]*</b> \u2192 fresh weighted session, "
     r"graded, misses logged in <a href=\"Error Log\"[^>]*>Error Log</a>\.",
     "\u2014 every word and rule from Lessons 1\u201311, plus a "
     "<a href=\"flashcards.html\">flashcard deck</a> you can drill by lesson.", 0),
    # per-lesson weighting blurbs
    (r"re-weighted to your \d+ ticked misses?:\s*", "focus areas: ", 0),
    (r"\s*\u2014 your flagged weak spot", "", 0),
    (r"re-weighted to ", "focus: ", 0),
    # bank intros (line-anchored: NO DOTALL, or they swallow the file)
    (r"> \[!info\] How to use these\n(?:>.*\n)*",
     "> [!info] How to use these\n"
     "> Every word from Lessons 1\u201311, grouped by lesson, with its **root** in parentheses.\n"
     "> Verbs are listed as \u0627\u0644\u0645\u0627\u0636\u064a / \u0627\u0644\u0645\u0636\u0627\u0631\u0639 / \u0627\u0644\u0645\u0635\u062f\u0631.\n"
     "> Use the search box at the top to find a word fast, or open the\n"
     "> [flashcards](flashcards.html) to drill this list in either direction.\n"
     "> Most concrete nouns and verbs carry a picture for visual recall.\n", re.M),
    (r"> \[!info\] Grammar is drilled by \*\*arabic-drill\*\*[^\n]*\n(?:>.*\n)*",
     "> [!info] How to use these\n"
     "> Every grammar rule from Lessons 1\u201311 in one place \u2014 prompt on the left, answer on the right.\n"
     "> Cover the right-hand column and work your way down it.\n", re.M),
    # vault jargon in the bank titles
    (r"# Arabic \u2014 (Vocab|Grammar) Bank \(drillable\)", r"# \1 Bank", 0),
    # leftover deck tags
    (r"^\*\*Deck tag:\*\*.*$\n?", "", re.M),
    (r"^#flashcard\S*\s*$\n?", "", re.M),
    (r"\s*#flashcard\S*", "", 0),
]

def depersonalize(t: str) -> str:
    for pat, rep, flags in DEPERSONALIZE:
        t = re.sub(pat, rep, t, flags=flags)
    return t

# ---------------------------------------------------------------- md -> html
def strip_frontmatter(t: str):
    if t.startswith("---"):
        end = t.find("\n---", 3)
        if end != -1:
            return t[end + 4 :].lstrip("\n")
    return t

def inline(s: str) -> str:
    """Inline markdown. Raw HTML in the source is intentionally preserved."""
    # image embeds  ![[file.png|200]]
    def img(m):
        parts = m.group(1).split("|")
        fn = parts[0].strip().replace("\\", "")
        w = parts[1].strip() if len(parts) > 1 else "160"
        if not re.fullmatch(r"\d+", w):
            w = "160"
        return f'<img class="emoji-card" src="media/{html.escape(fn)}" alt="" loading="lazy" style="max-width:{w}px">'
    s = re.sub(r"!\[\[([^\]]+)\]\]", img, s)
    # wikilinks [[Note|alias]]
    def wiki(m):
        raw = m.group(1)
        target, _, alias = raw.partition("|")
        label = (alias or target.split("/")[-1]).strip()
        url = slug_for(target)
        if url:
            return f'<a href="{url}">{html.escape(label)}</a>'
        return html.escape(label)  # unpublished note -> plain text, no dead link
    s = re.sub(r"(?<!!)\[\[([^\]]+)\]\]", wiki, s)
    # markdown links
    def link(m):
        label, url = m.group(1), m.group(2)
        ext = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
        return f'<a href="{html.escape(url)}"{ext}>{label}</a>'
    s = re.sub(r"\[([^\]]+)\]\(((?:https?://|[\w./#-])[^)\s]*)\)", link, s)
    s = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"~~([^~]+)~~", r"<s>\1</s>", s)
    # bare hashtags -> chips
    s = re.sub(r"(?<![\w&#])#([A-Za-z][\w/-]*)", r'<span class="tag">#\1</span>', s)
    return s

def dirwrap(cell: str) -> str:
    return ' dir="rtl"' if is_rtl(re.sub(r"<[^>]+>", "", cell)) else ""

CALLOUT = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")

def md_to_html(text: str) -> str:
    text = depersonalize(strip_frontmatter(text))
    text = re.sub(r"<!--SR:.*?-->\n?", "", text)      # spaced-repetition scheduling: private
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]

        # blank
        if not ln.strip():
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"\s*(---|\*\*\*|___)\s*", ln):
            out.append("<hr>")
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl, txt = len(m.group(1)), m.group(2).strip()
            aid = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", txt).lower()).strip("-")[:60]
            out.append(f'<h{lvl} id="{aid}"{dirwrap(txt)}>{inline(txt)}</h{lvl}>')
            i += 1
            continue

        # blockquote / callout
        if ln.lstrip().startswith(">"):
            block = []
            while i < len(lines) and (lines[i].lstrip().startswith(">") or
                                      (block and lines[i].strip() and not lines[i].startswith("#"))):
                if not lines[i].lstrip().startswith(">"):
                    break
                block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            kind, title = "note", ""
            cm = CALLOUT.match("> " + block[0]) if block else None
            if cm:
                kind, title = cm.group(1).lower(), cm.group(2).strip()
                block = block[1:]
            body = md_to_html("\n".join(block)) if block else ""
            head = f'<div class="callout-title">{inline(title or kind.title())}</div>'
            out.append(f'<div class="callout callout-{html.escape(kind)}">{head}{body}</div>')
            continue

        # table
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            def cells(row):
                return [c.strip() for c in row.strip().strip("|").split("|")]
            head = cells(ln)
            i += 2
            body = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                body.append(cells(lines[i]))
                i += 1
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += [f"<th{dirwrap(c)}>{inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for row in body:
                row += [""] * (len(head) - len(row))
                full = len([c for c in row if c]) == 1 and row[0]
                cls = ' class="row-group"' if full else ""
                t.append(f"<tr{cls}>")
                for c in row[: len(head)]:
                    t.append(f"<td{dirwrap(c)}>{inline(c)}</td>")
                t.append("</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue

        # list
        if re.match(r"^\s*([-*+]|\d+\.)\s+", ln):
            ordered = bool(re.match(r"^\s*\d+\.\s", ln))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(
                f"<li{dirwrap(x)}>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        # two-way flashcard line:  Arabic ::: English
        if ":::" in ln and is_rtl(ln.split(":::")[0]):
            front, _, back = ln.partition(":::")
            out.append(
                '<div class="card-row">'
                f'<div class="card-front" dir="rtl">{inline(front.strip())}</div>'
                f'<div class="card-back">{inline(back.strip())}</div>'
                "</div>")
            i += 1
            continue

        # one-way flashcard line:  prompt :: answer
        m2 = re.match(r"^(?!\s*[|>#])(.+?)\s+::\s+(.+)$", ln)
        if m2 and ":::" not in ln:
            q, a = m2.group(1).strip(), m2.group(2).strip()
            out.append(
                '<div class="card-row one-way">'
                f'<div class="card-q"{dirwrap(q)}>{inline(q)}</div>'
                f'<div class="card-a"{dirwrap(a)}>{inline(a)}</div>'
                "</div>")
            i += 1
            continue

        # raw html block -> pass through untouched
        if ln.lstrip().startswith("<"):
            out.append(ln)
            i += 1
            continue

        # paragraph
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*(#{1,6}\s|>|\||[-*+]\s|\d+\.\s|<|---)", lines[i]) and not (
                ":::" in lines[i] and is_rtl(lines[i].split(":::")[0])) and not re.match(
                r"^(?!\s*[|>#])(.+?)\s+::\s+(.+)$", lines[i]):
            para.append(lines[i])
            i += 1
        if para:
            p = " ".join(para)
            out.append(f"<p{dirwrap(p)}>{inline(p)}</p>")
        else:
            out.append(inline(ln))
            i += 1
    return "\n".join(out)

# ---------------------------------------------------------------- html-tiles
def clean_tiles(t: str) -> str:
    """The lesson notes are already HTML. Just fix Obsidian-only link/embed syntax."""
    t = depersonalize(strip_frontmatter(t))
    t = re.sub(r"<!--SR:.*?-->\n?", "", t)

    def fix_href(m):
        url = slug_for(m.group(1))
        return f'href="{url}"' if url else 'href="#" class="dead"'
    t = re.sub(r'href="((?!https?:|#|mailto:)[^"]+)"', fix_href, t)
    t = t.replace(' class="internal-link"', "")
    t = re.sub(r'<a href="#" class="dead">(.*?)</a>', r'<span class="unpublished">\1</span>', t, flags=re.S)

    def img(m):
        parts = m.group(1).split("|")
        fn = parts[0].strip().replace("\\", "")
        w = parts[1].strip() if len(parts) > 1 and parts[1].strip().isdigit() else "200"
        return f'<img class="emoji-card" src="media/{html.escape(fn)}" alt="" loading="lazy" style="max-width:{w}px">'
    t = re.sub(r"!\[\[([^\]]+)\]\]", img, t)

    def wiki(m):
        target, _, alias = m.group(1).partition("|")
        label = (alias or target.split("/")[-1]).strip()
        url = slug_for(target)
        return f'<a href="{url}">{html.escape(label)}</a>' if url else html.escape(label)
    t = re.sub(r"(?<!!)\[\[([^\]]+)\]\]", wiki, t)
    return t

# ---------------------------------------------------------------- flashcards
def parse_cards(vocab_md: str):
    cards, lesson = [], None
    for raw in strip_frontmatter(vocab_md).split("\n"):
        h = re.match(r"^##\s+Lesson\s+(\d+)\b", raw)
        if h:
            lesson = int(h.group(1))
            continue
        if raw.startswith("## "):        # Master Verb Table, Root families, ...
            lesson = None
            continue
        if ":::" not in raw or lesson is None:
            continue
        front, _, back = raw.partition(":::")
        front, back = front.strip(), back.strip()
        if not front or not back or front.startswith(("|", ">")):
            continue
        img = None
        mi = re.search(r"!\[\[([^\]|]+)", back)
        if mi:
            img = mi.group(1).strip().replace("\\", "")
        back_txt = re.sub(r"(<br\s*/?>)+\s*!\[\[[^\]]+\]\]", "", back).strip()
        back_txt = re.sub(r"<br\s*/?>", " ", back_txt).strip()
        root = None
        mr = re.search(r"\(([^)]*)\)\s*$", front)
        ar_front = front
        if mr:
            root = mr.group(1).strip()
            ar_front = front[: mr.start()].strip()
            if root in ("—", "-", ""):
                root = None
        cards.append({"l": lesson, "ar": ar_front, "root": root,
                      "en": re.sub(r"<[^>]+>", "", back_txt).strip(), "img": img})
    return cards

# ---------------------------------------------------------------- page shell
NAV = [("index.html", "Home"), ("review.html", "Overview"),
       ("vocab.html", "Vocab"), ("grammar.html", "Grammar"),
       ("flashcards.html", "Flashcards")]

def shell(title, body, active="", subtitle="", wide=False, extra_js=""):
    nav = "".join(
        f'<a href="{u}" class="{"on" if u == active else ""}">{n}</a>' for u, n in NAV)
    lessons = "".join(
        f'<a href="l{n:02d}.html" class="{"on" if f"l{n:02d}.html" == active else ""}">{n}</a>'
        for n in range(1, 12))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="Al-Kitaab Part One (3rd ed.) review notes, Lessons 1-11 - vocabulary, grammar, and flashcards.">
<meta name="robots" content="noindex, nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
  <div class="bar-inner">
    <a class="brand" href="index.html"><span class="brand-ar" dir="rtl">العربية</span><span class="brand-en">Al-Kitaab 1 &middot; Lessons 1&ndash;11</span></a>
    <nav class="mainnav">{nav}</nav>
    <button id="theme" class="theme" type="button" aria-label="Toggle dark mode">&#9789;</button>
  </div>
  <nav class="lessonnav" aria-label="Lessons"><span class="lbl">Lessons</span>{lessons}</nav>
</header>
<main id="main" class="{'wide' if wide else ''}">
{f'<p class="crumb">{html.escape(subtitle)}</p>' if subtitle else ''}
{body}
</main>
<footer>
  <p>Study notes on <b>Al-Kitaab fii Ta&#703;allum al-&#703;Arabiyya, Part One (3rd ed.)</b>, Lessons 1&ndash;11.
  Built from Obsidian notes. Picture cards are <a href="https://openmoji.org" target="_blank" rel="noopener">OpenMoji</a> (CC BY-SA 4.0).</p>
  <p class="fine">Unofficial student-made review material. Not affiliated with the textbook's authors or publisher.</p>
</footer>
<script src="assets/site.js"></script>
{extra_js}
</body>
</html>"""

# ---------------------------------------------------------------- assets
CSS = r"""
:root{
  --bg:#ffffff; --background-primary:#ffffff; --background-primary-alt:#f7f8fa;
  --background-secondary:#f4f6f9; --background-modifier-border:#e2e6ec;
  --text-normal:#15181d; --text-muted:#616a77; --accent:#3b82d6;
  --font-interface:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  --font-ar:'Amiri','Geeza Pro','Noto Naskh Arabic',serif;
  --shadow:0 1px 2px rgba(16,24,40,.05),0 6px 20px rgba(16,24,40,.05);
}
html[data-theme="dark"]{
  --bg:#14171c; --background-primary:#14171c; --background-primary-alt:#1b1f26;
  --background-secondary:#1b1f26; --background-modifier-border:#2c323c;
  --text-normal:#e6e9ee; --text-muted:#98a2b2; --accent:#6aa5e8;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 8px 24px rgba(0,0,0,.28);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:104px}
body{margin:0;background:var(--bg);color:var(--text-normal);
  font-family:var(--font-interface);line-height:1.6;-webkit-text-size-adjust:100%}
[dir="rtl"]{font-family:var(--font-ar);line-height:1.9}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.skip{position:absolute;left:-9999px}
.skip:focus{left:8px;top:8px;background:var(--accent);color:#fff;padding:8px 14px;border-radius:8px;z-index:99}

/* ---- header ---- */
.topbar{position:sticky;top:0;z-index:50;background:var(--background-primary);
  border-bottom:1px solid var(--background-modifier-border);backdrop-filter:saturate(180%) blur(8px)}
.bar-inner{max-width:1180px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:16px}
.brand{display:flex;flex-direction:column;line-height:1.15;color:var(--text-normal);flex:0 0 auto}
.brand:hover{text-decoration:none}
.brand-ar{font-family:var(--font-ar);font-size:1.3em;font-weight:700}
.brand-en{font-size:.68em;color:var(--text-muted);font-weight:600;letter-spacing:.04em}
.mainnav{display:flex;gap:2px;margin-left:auto;flex-wrap:wrap}
.mainnav a{padding:7px 13px;border-radius:9px;font-size:.87em;font-weight:600;color:var(--text-muted)}
.mainnav a:hover{background:var(--background-secondary);text-decoration:none;color:var(--text-normal)}
.mainnav a.on{background:var(--accent);color:#fff}
.theme{background:var(--background-secondary);border:1px solid var(--background-modifier-border);
  color:var(--text-normal);border-radius:9px;width:36px;height:34px;cursor:pointer;font-size:1em;flex:0 0 auto}
.lessonnav{max-width:1180px;margin:0 auto;padding:0 20px 9px;display:flex;gap:5px;align-items:center;flex-wrap:wrap}
.lessonnav .lbl{font-size:.66em;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin-right:4px}
.lessonnav a{width:29px;height:29px;display:grid;place-items:center;border-radius:8px;font-size:.8em;font-weight:700;
  color:var(--text-muted);border:1px solid var(--background-modifier-border)}
.lessonnav a:hover{background:var(--background-secondary);color:var(--text-normal);text-decoration:none}
.lessonnav a.on{background:var(--accent);color:#fff;border-color:var(--accent)}

main{max-width:900px;margin:0 auto;padding:30px 20px 70px}
main.wide{max-width:1180px}
.crumb{font-size:.76em;color:var(--text-muted);margin:0 0 14px;letter-spacing:.03em}

h1,h2,h3,h4{line-height:1.25;color:var(--text-normal);scroll-margin-top:110px}
h1{font-size:2em;font-weight:800;letter-spacing:-.02em;margin:.2em 0 .5em}
h2{font-size:1.4em;font-weight:800;margin:1.9em 0 .5em;padding-bottom:.3em;
  border-bottom:1px solid var(--background-modifier-border)}
h3{font-size:1.08em;font-weight:700;margin:1.5em 0 .4em;color:var(--text-normal)}
h2[dir="rtl"],h3[dir="rtl"]{font-size:1.5em}
hr{border:0;border-top:1px solid var(--background-modifier-border);margin:2.2em 0}
code{background:var(--background-secondary);border:1px solid var(--background-modifier-border);
  border-radius:5px;padding:1px 5px;font-size:.88em}
.tag{display:inline-block;font-size:.72em;font-weight:700;color:var(--text-muted);
  background:var(--background-secondary);border-radius:999px;padding:1px 9px}
.unpublished{color:var(--text-muted)}

/* ---- tables ---- */
.table-wrap{overflow-x:auto;margin:14px 0;border:1px solid var(--background-modifier-border);
  border-radius:12px;background:var(--background-primary);box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:.9em}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--background-modifier-border);vertical-align:top}
th{background:var(--background-secondary);font-weight:700;font-size:.85em;
  letter-spacing:.03em;position:sticky;top:0}
td[dir="rtl"],th[dir="rtl"]{text-align:right;font-size:1.12em}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--background-primary-alt)}
tr.row-group td{background:var(--background-secondary);font-weight:800}

/* ---- callouts ---- */
.callout{background:var(--background-secondary);border:1px solid var(--background-modifier-border);
  border-left:4px solid var(--accent);border-radius:12px;padding:13px 18px;margin:16px 0}
.callout-title{font-size:.72em;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
  color:var(--accent);margin-bottom:6px}
.callout p:first-of-type{margin-top:0}
.callout p:last-child{margin-bottom:0}
.callout-warning,.callout-caution{border-left-color:#e0913a}
.callout-warning .callout-title,.callout-caution .callout-title{color:#e0913a}
.callout-tip,.callout-success{border-left-color:#3aa76d}
.callout-tip .callout-title,.callout-success .callout-title{color:#3aa76d}

/* ---- vocab card rows ---- */
.card-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:center;
  padding:11px 16px;border:1px solid var(--background-modifier-border);border-radius:12px;
  background:var(--background-primary);margin:7px 0}
.card-front{font-family:var(--font-ar);font-size:1.45em;font-weight:700;text-align:right}
.card-back{font-size:.94em;color:var(--text-muted)}
.emoji-card{max-width:110px;height:auto;display:block;margin:8px 0}
@media(max-width:620px){.card-row{grid-template-columns:1fr;gap:4px}.card-front{text-align:right}}

/* ---- home ---- */
.hero{background:var(--background-secondary);border:1px solid var(--background-modifier-border);
  border-radius:18px;padding:34px 30px;margin-bottom:26px;box-shadow:var(--shadow)}
.hero h1{margin-top:0}
.hero .ar{font-family:var(--font-ar);font-size:2.6em;font-weight:700;margin:0 0 6px}
.hero p{color:var(--text-muted);max-width:60ch;margin:.6em 0 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(258px,1fr));gap:14px;margin:18px 0}
.tile{display:block;background:var(--background-primary);border:1px solid var(--background-modifier-border);
  border-radius:14px;padding:17px 19px;color:var(--text-normal);transition:transform .14s,box-shadow .14s,border-color .14s}
.tile:hover{text-decoration:none;transform:translateY(-2px);box-shadow:var(--shadow);border-color:var(--accent)}
.tile .n{display:inline-block;font-size:.66em;font-weight:800;letter-spacing:.09em;color:#fff;
  background:var(--accent);border-radius:999px;padding:3px 10px;margin-bottom:9px}
.tile .ar{font-family:var(--font-ar);font-size:1.5em;font-weight:700;direction:rtl;text-align:right;line-height:1.5}
.tile .en{font-size:.86em;color:var(--text-muted);margin-top:3px}
.tile .meta{font-size:.72em;color:var(--text-muted);margin-top:9px;
  border-top:1px solid var(--background-modifier-border);padding-top:8px}

/* ---- toolbar (vocab search) ---- */
.toolbar{position:sticky;top:96px;z-index:20;display:flex;gap:9px;flex-wrap:wrap;align-items:center;
  background:var(--background-primary);border:1px solid var(--background-modifier-border);
  border-radius:12px;padding:10px 12px;margin-bottom:18px;box-shadow:var(--shadow)}
.toolbar input,.toolbar select{font:inherit;font-size:.9em;padding:7px 11px;border-radius:9px;
  border:1px solid var(--background-modifier-border);background:var(--background-primary-alt);color:var(--text-normal)}
.toolbar input{flex:1 1 220px}
.toolbar .count{font-size:.78em;color:var(--text-muted);margin-left:auto}
.hidden{display:none !important}
mark{background:#ffe9a8;color:#15181d;border-radius:3px;padding:0 2px}
html[data-theme="dark"] mark{background:#6b5a1e;color:#fff}

/* ---- flashcards ---- */
.fc-setup{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-bottom:18px}
.fc-setup select,.fc-setup button{font:inherit;font-size:.9em;padding:8px 14px;border-radius:9px;
  border:1px solid var(--background-modifier-border);background:var(--background-primary-alt);
  color:var(--text-normal);cursor:pointer}
.fc-setup button.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:700}
.flashcard{position:relative;min-height:340px;display:grid;place-items:center;text-align:center;
  background:var(--background-secondary);border:1px solid var(--background-modifier-border);
  border-radius:20px;padding:36px 28px;cursor:pointer;user-select:none;box-shadow:var(--shadow)}
.flashcard:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.fc-prompt-ar{font-family:var(--font-ar);font-size:3em;font-weight:700;direction:rtl;line-height:1.55}
.fc-prompt-en{font-size:1.9em;font-weight:700}
.fc-root{font-family:var(--font-ar);direction:rtl;font-size:1em;color:var(--text-muted);
  background:var(--background-modifier-border);border-radius:7px;padding:2px 11px;display:inline-block;margin-top:12px}
.fc-answer{margin-top:20px;padding-top:18px;border-top:1px dashed var(--background-modifier-border);width:100%}
.fc-answer img{max-width:140px;margin:12px auto 0;display:block}
.fc-hint{position:absolute;bottom:12px;left:0;right:0;font-size:.74em;color:var(--text-muted)}
.fc-actions{display:flex;gap:10px;justify-content:center;margin-top:16px}
.fc-actions button{font:inherit;font-weight:700;font-size:.92em;padding:11px 26px;border-radius:11px;cursor:pointer;
  border:1px solid var(--background-modifier-border);background:var(--background-primary-alt);color:var(--text-normal)}
.fc-actions .good{background:#3aa76d;border-color:#3aa76d;color:#fff}
.fc-actions .bad{background:#d9534f;border-color:#d9534f;color:#fff}
.fc-bar{height:7px;border-radius:999px;background:var(--background-modifier-border);overflow:hidden;margin:16px 0 9px}
.fc-bar i{display:block;height:100%;background:var(--accent);width:0;transition:width .25s}
.fc-stats{display:flex;gap:18px;font-size:.82em;color:var(--text-muted);justify-content:center;margin-bottom:14px}
.fc-stats b{color:var(--text-normal)}

/* ---- one-way (prompt / answer) cards ---- */
.card-row.one-way{grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);align-items:start;gap:20px;padding:12px 18px}
.card-q{font-size:.95em;color:var(--text-normal)}
.card-q[dir="rtl"],.card-a[dir="rtl"]{font-family:var(--font-ar);font-size:1.25em;text-align:right}
.card-a{font-size:.95em;color:var(--text-muted);border-left:2px solid var(--background-modifier-border);padding-left:16px}
.card-a[dir="rtl"]{color:var(--text-normal);font-weight:600}
@media(max-width:620px){.card-row.one-way{grid-template-columns:1fr;gap:6px}
  .card-a{border-left:0;border-top:1px solid var(--background-modifier-border);padding:6px 0 0}}

/* ---- self-check misses ---- */
.miss{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:8px 0 2px;font-size:.8em}
.miss label{display:inline-flex;align-items:center;gap:7px;cursor:pointer;color:var(--text-muted);
  border:1px solid var(--background-modifier-border);border-radius:999px;padding:3px 12px;user-select:none}
.miss label:hover{border-color:#d9534f;color:var(--text-normal)}
.miss input{accent-color:#d9534f;cursor:pointer;margin:0}
.miss input:checked + span,.miss label:has(input:checked){color:#d9534f;border-color:#d9534f;font-weight:700}
.qtag{font-size:.9em;color:var(--text-muted);font-style:italic}
.tally{position:fixed;right:18px;bottom:18px;z-index:60;background:var(--background-primary);
  border:1px solid var(--background-modifier-border);border-radius:999px;padding:9px 18px;
  box-shadow:var(--shadow);font-size:.82em;font-weight:700;color:var(--text-normal);display:none;gap:9px;align-items:center}
.tally.on{display:flex}
.tally b{color:#d9534f;font-size:1.25em}
.tally button{font:inherit;font-size:.86em;font-weight:600;background:none;border:0;color:var(--text-muted);
  cursor:pointer;border-left:1px solid var(--background-modifier-border);padding-left:10px}
@media(max-width:620px){.tally{right:10px;bottom:10px}}

footer{border-top:1px solid var(--background-modifier-border);padding:24px 20px 46px;
  max-width:1180px;margin:0 auto;color:var(--text-muted);font-size:.8em}
footer .fine{opacity:.75;font-size:.92em}
@media(max-width:620px){
  .bar-inner{flex-wrap:wrap;gap:10px}
  .mainnav{width:100%;margin-left:0;order:3}
  main{padding:20px 15px 50px}
  h1{font-size:1.55em}
  .toolbar{position:static}
  .fc-prompt-ar{font-size:2.2em}
}
@media print{.topbar,.toolbar,footer,.theme{display:none}main{max-width:none}}
"""

JS = r"""
(function(){
  var K='arabic-site-theme';
  var saved=null; try{saved=localStorage.getItem(K);}catch(e){}
  var t=saved||(window.matchMedia&&matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.setAttribute('data-theme',t);
  document.addEventListener('DOMContentLoaded',function(){
    var b=document.getElementById('theme'); if(!b)return;
    var set=function(v){document.documentElement.setAttribute('data-theme',v);
      b.innerHTML=v==='dark'?'&#9728;':'&#9789;'; try{localStorage.setItem(K,v);}catch(e){}};
    set(document.documentElement.getAttribute('data-theme'));
    b.addEventListener('click',function(){
      set(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark');});
  });
  /* self-check miss tally */
  document.addEventListener('DOMContentLoaded',function(){
    var boxes=document.querySelectorAll('.missbox');
    if(!boxes.length)return;
    var t=document.createElement('div'); t.className='tally';
    t.innerHTML='<span>Missed <b>0</b> / '+boxes.length+'</span><button type="button">reset</button>';
    document.body.appendChild(t);
    var num=t.querySelector('b');
    function upd(){
      var n=0; boxes.forEach(function(b){if(b.checked)n++;});
      num.textContent=n; t.classList.toggle('on',n>0);
    }
    boxes.forEach(function(b){b.addEventListener('change',upd);});
    upd();
    t.querySelector('button').addEventListener('click',function(){
      boxes.forEach(function(b){b.checked=false;}); upd();});
  });
})();
"""

SEARCH_JS = r"""
<script>
(function(){
  var q=document.getElementById('q'), sel=document.getElementById('sec'), cnt=document.getElementById('cnt');
  if(!q) return;
  var rows=[], sections=[];
  document.querySelectorAll('#main tbody tr, #main .card-row').forEach(function(el){
    rows.push({el:el, txt:el.textContent.toLowerCase()});
  });
  document.querySelectorAll('#main h2, #main h3').forEach(function(h){sections.push(h);});

  function sectionOf(el){
    var n=el.closest('.table-wrap')||el, h=null;
    while(n){ if(n.previousElementSibling){n=n.previousElementSibling;
        if(/^H[23]$/.test(n.tagName)){h=n;break;} } else {n=n.parentElement;} }
    return h?h.id:'';
  }
  rows.forEach(function(r){ r.sec=sectionOf(r.el); });

  function apply(){
    var s=q.value.trim().toLowerCase(), want=sel?sel.value:'';
    var shown=0;
    rows.forEach(function(r){
      var ok=(!s||r.txt.indexOf(s)>-1)&&(!want||r.sec===want);
      r.el.classList.toggle('hidden',!ok); if(ok)shown++;
    });
    // hide section blocks that ended up empty
    document.querySelectorAll('#main .table-wrap').forEach(function(w){
      var any=w.querySelectorAll('tbody tr:not(.hidden)').length;
      w.classList.toggle('hidden',!any);
    });
    sections.forEach(function(h){
      var vis=false,n=h.nextElementSibling;
      while(n&&!/^H[23]$/.test(n.tagName)){
        if(!n.classList.contains('hidden')&&n.offsetParent!==null){vis=true;break;} n=n.nextElementSibling;}
      h.classList.toggle('hidden', (s||want)&&!vis);
    });
    if(cnt) cnt.textContent = shown + ' / ' + rows.length + ' entries';
  }
  q.addEventListener('input',apply);
  if(sel) sel.addEventListener('change',apply);
  apply();
})();
</script>
"""

FLASHCARD_JS = r"""
<script>
(function(){
  var DECK=[], pool=[], idx=0, flipped=false, right=0, wrong=0, missed=[];
  var elCard=document.getElementById('card'), elBar=document.getElementById('bar'),
      elStats=document.getElementById('stats'), elActions=document.getElementById('actions'),
      selL=document.getElementById('lesson'), selD=document.getElementById('dir'),
      btnStart=document.getElementById('start'), btnShuffle=document.getElementById('reshuffle');

  fetch('data/cards.json').then(function(r){return r.json();}).then(function(d){
    DECK=d; build();
  }).catch(function(){ elCard.innerHTML='<p>Could not load the deck. Serve this folder over http (see README).</p>'; });

  function shuffle(a){for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1));var t=a[i];a[i]=a[j];a[j]=t;}return a;}

  function build(){
    var L=selL.value;
    pool=shuffle(DECK.filter(function(c){return !L||String(c.l)===L;}).slice());
    idx=0;right=0;wrong=0;missed=[];flipped=false;render();
  }
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}

  function render(){
    if(!pool.length){elCard.innerHTML='<p>No cards in this selection.</p>';elActions.classList.add('hidden');return;}
    if(idx>=pool.length){
      var pct=Math.round(right/(right+wrong||1)*100);
      var list=missed.length?'<div style="margin-top:18px;text-align:left;max-width:460px">'+
        '<div style="font-size:.74em;font-weight:800;letter-spacing:.08em;color:var(--text-muted);margin-bottom:8px">REVIEW THESE</div>'+
        missed.map(function(c){return '<div class="card-row"><div class="card-front" dir="rtl">'+esc(c.ar)+
          '</div><div class="card-back">'+esc(c.en)+'</div></div>';}).join('')+'</div>':'';
      elCard.innerHTML='<div><div style="font-size:2.6em;font-weight:800">'+pct+'%</div>'+
        '<p style="color:var(--text-muted)">'+right+' right &middot; '+wrong+' missed &middot; '+pool.length+' cards</p>'+list+'</div>';
      elActions.classList.add('hidden');
      elBar.style.width='100%';
      elStats.innerHTML='Round complete &mdash; press <b>R</b> or hit Reshuffle to go again.';
      return;
    }
    var c=pool[idx], arFirst=selD.value!=='en';
    var front = arFirst
      ? '<div class="fc-prompt-ar">'+esc(c.ar)+'</div>'+(c.root?'<div class="fc-root">'+esc(c.root)+'</div>':'')
      : '<div class="fc-prompt-en">'+esc(c.en)+'</div>';
    var back = arFirst
      ? '<div style="font-size:1.35em;font-weight:700">'+esc(c.en)+'</div>'
      : '<div class="fc-prompt-ar">'+esc(c.ar)+'</div>'+(c.root?'<div class="fc-root">'+esc(c.root)+'</div>':'');
    if(c.img) back += '<img src="media/'+esc(c.img)+'" alt="">';
    elCard.innerHTML='<div style="width:100%">'+front+
      (flipped?'<div class="fc-answer">'+back+'</div>':'')+
      '<div class="fc-hint">'+(flipped?'1 = missed &middot; 2 = got it':'click or press Space to flip')+'</div></div>';
    elActions.classList.toggle('hidden',!flipped);
    elBar.style.width=(idx/pool.length*100)+'%';
    elStats.innerHTML='<span>Card <b>'+(idx+1)+'</b> / '+pool.length+'</span>'+
      '<span>Lesson <b>'+c.l+'</b></span><span>Right <b>'+right+'</b></span><span>Missed <b>'+wrong+'</b></span>';
  }
  function flip(){ if(idx<pool.length){flipped=!flipped;render();} }
  function grade(ok){ if(idx>=pool.length)return;
    if(ok){right++;}else{wrong++;missed.push(pool[idx]);}
    idx++;flipped=false;render(); }

  elCard.addEventListener('click',flip);
  document.getElementById('good').addEventListener('click',function(e){e.stopPropagation();grade(true);});
  document.getElementById('bad').addEventListener('click',function(e){e.stopPropagation();grade(false);});
  btnStart.addEventListener('click',build);
  btnShuffle.addEventListener('click',build);
  selL.addEventListener('change',build);
  selD.addEventListener('change',build);
  document.addEventListener('keydown',function(e){
    if(/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName))return;
    if(e.code==='Space'||e.key==='Enter'){e.preventDefault();flip();}
    else if(e.key==='2'||e.key==='ArrowRight'){if(flipped)grade(true);}
    else if(e.key==='1'||e.key==='ArrowLeft'){if(flipped)grade(false);}
    else if(e.key==='r'||e.key==='R'){build();}
  });
})();
</script>
"""

# ---------------------------------------------------------------- main build
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(DEFAULT_VAULT))
    args = ap.parse_args()
    src = pathlib.Path(args.vault).expanduser()
    if not src.is_dir():
        sys.exit(f"Source folder not found: {src}")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    (OUT / "media").mkdir()
    (OUT / "data").mkdir()
    (OUT / "assets/site.css").write_text(CSS)
    (OUT / "assets/site.js").write_text(JS)
    (OUT / ".nojekyll").write_text("")
    # keep the site out of search results: shared by link, not indexed
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n")

    # --- media
    n_media = 0
    for p in sorted((src / "_media").glob("*")):
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"):
            shutil.copy2(p, OUT / "media" / p.name)
            n_media += 1

    # --- lessons
    lesson_meta = []
    for p in sorted((src / "Lessons").glob("L*.md")):
        raw = p.read_text()
        fm = raw.split("---")[1] if raw.startswith("---") else ""
        def fv(key, default=""):
            m = re.search(rf"^{key}:\s*(.*)$", fm, re.M)
            return m.group(1).strip().strip('"\'') if m else default
        num = int(fv("lesson", re.match(r"L(\d+)", p.name).group(1)))
        meta = {"n": num, "ar": fv("lesson_title_ar"), "en": fv("lesson_title_en"),
                "pages": fv("pages"), "file": f"l{num:02d}.html"}
        lesson_meta.append(meta)
        (OUT / meta["file"]).write_text(shell(
            f"Lesson {num} — {meta['en']}",
            clean_tiles(raw),
            active=meta["file"],
            subtitle=f"Lesson {num} · pp. {meta['pages']}"))
    lesson_meta.sort(key=lambda m: m["n"])

    # --- general review
    (OUT / "review.html").write_text(shell(
        "Overview — Lessons 1–11",
        clean_tiles((src / "00 — General Review.md").read_text()),
        active="review.html", subtitle="Cross-lesson overview"))

    # --- grammar bank
    (OUT / "grammar.html").write_text(shell(
        "Grammar Bank",
        md_to_html((src / "Practice/Grammar Bank.md").read_text()),
        active="grammar.html", subtitle="Grammar reference · Lessons 1–11"))

    # --- vocab bank (+ search toolbar)
    vocab_md = (src / "Practice/Vocab Bank.md").read_text()
    vocab_html = md_to_html(vocab_md)
    opts = "".join(f'<option value="lesson-{n}">Lesson {n}</option>' for n in range(1, 12))
    toolbar = (
        '<div class="toolbar">'
        '<input id="q" type="search" placeholder="Search Arabic, English, or root…" aria-label="Search vocabulary">'
        f'<select id="sec" aria-label="Filter by lesson"><option value="">All sections</option>{opts}</select>'
        '<span class="count" id="cnt"></span></div>')
    (OUT / "vocab.html").write_text(shell(
        "Vocab Bank", toolbar + vocab_html, active="vocab.html",
        subtitle="Every word, Lessons 1–11", wide=True, extra_js=SEARCH_JS))

    # --- flashcards
    cards = parse_cards(vocab_md)
    (OUT / "data/cards.json").write_text(json.dumps(cards, ensure_ascii=False, separators=(",", ":")))
    by_lesson = {}
    for c in cards:
        by_lesson[c["l"]] = by_lesson.get(c["l"], 0) + 1
    lopts = "".join(
        f'<option value="{n}">Lesson {n} ({by_lesson.get(n,0)})</option>' for n in sorted(by_lesson))
    fc_body = f"""
<h1>Flashcards</h1>
<div class="fc-setup">
  <select id="lesson" aria-label="Deck"><option value="">All lessons ({len(cards)} cards)</option>{lopts}</select>
  <select id="dir" aria-label="Direction">
    <option value="ar">Arabic &rarr; English</option>
    <option value="en">English &rarr; Arabic</option>
  </select>
  <button id="start" class="primary" type="button">Start</button>
  <button id="reshuffle" type="button">Reshuffle</button>
</div>
<div class="fc-bar"><i id="bar"></i></div>
<div class="fc-stats" id="stats"></div>
<div class="flashcard" id="card" tabindex="0" role="button" aria-label="Flashcard, click to flip">Loading deck&hellip;</div>
<div class="fc-actions hidden" id="actions">
  <button class="bad" id="bad" type="button">Missed &nbsp;<kbd>1</kbd></button>
  <button class="good" id="good" type="button">Got it &nbsp;<kbd>2</kbd></button>
</div>
<p style="font-size:.8em;color:var(--text-muted);margin-top:18px">
  <b>Keys:</b> Space/Enter flip &middot; 1 missed &middot; 2 got it &middot; R reshuffle.
  Missed cards are listed at the end of the round.</p>
"""
    (OUT / "flashcards.html").write_text(shell(
        "Flashcards", fc_body, active="flashcards.html",
        subtitle=f"{len(cards)} cards · Lessons 1–11", extra_js=FLASHCARD_JS))

    # --- home
    tiles = "".join(
        f'<a class="tile" href="{m["file"]}"><span class="n">LESSON {m["n"]}</span>'
        f'<div class="ar">{html.escape(m["ar"])}</div>'
        f'<div class="en">{html.escape(m["en"])}</div>'
        f'<div class="meta">pp. {html.escape(m["pages"])}</div></a>'
        for m in lesson_meta)
    home = f"""
<div class="hero">
  <div class="ar" dir="rtl">مُراجَعة العَرَبيّة</div>
  <h1>Al-Kitaab Part One &mdash; Lessons 1&ndash;11</h1>
  <p>Full review notes for every lesson: vocabulary, grammar, and the structures each chapter
  actually tests. Plus a searchable vocab bank of <b>{len(cards)} words</b> and a flashcard deck
  you can drill by lesson.</p>
</div>
<div class="grid">
  <a class="tile" href="review.html"><span class="n">START HERE</span>
    <div class="en" style="font-size:1.05em;font-weight:700;color:var(--text-normal)">Cross-Lesson Overview</div>
    <div class="en">Every grammar topic from Lessons 1&ndash;11 in one place.</div></a>
  <a class="tile" href="vocab.html"><span class="n">VOCAB</span>
    <div class="en" style="font-size:1.05em;font-weight:700;color:var(--text-normal)">Vocab Bank</div>
    <div class="en">All {len(cards)} words with roots and picture cards. Searchable.</div></a>
  <a class="tile" href="grammar.html"><span class="n">GRAMMAR</span>
    <div class="en" style="font-size:1.05em;font-weight:700;color:var(--text-normal)">Grammar Bank</div>
    <div class="en">Rules, patterns, and the verb forms I&ndash;X.</div></a>
  <a class="tile" href="flashcards.html"><span class="n">DRILL</span>
    <div class="en" style="font-size:1.05em;font-weight:700;color:var(--text-normal)">Flashcards</div>
    <div class="en">Click-to-flip, both directions, by lesson.</div></a>
</div>
<h2>Lessons</h2>
<div class="grid">{tiles}</div>
"""
    (OUT / "index.html").write_text(shell(
        "Arabic — Al-Kitaab 1 Review", home, active="index.html"))

    print(f"Built {len(lesson_meta)} lessons + 5 pages")
    print(f"  {len(cards)} flashcards  |  {n_media} images  |  -> {OUT}")

if __name__ == "__main__":
    main()
