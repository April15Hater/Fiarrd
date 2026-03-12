"""
modules/docx_builder.py — Build .docx files for resume and cover letter export.

Two modes:
  1. Template mode: open a user-supplied .docx, find the placeholder line, replace it.
  2. Scratch mode: build a cleanly formatted document from scratch.

Placeholder strings:
  Resume:       [RESUME_CONTENT]
  Cover letter: [COVER_LETTER_CONTENT]

Target format (matched to user's reference resume):
  - Name:          18pt bold black Calibri, centered
  - Contact line:  9pt gray Calibri, centered
  - Tagline:       11pt bold black Calibri, centered (detected as ALL-CAPS or mixed-caps
                   line containing | between the contact and first section header)
  - Section hdrs:  11pt bold black Calibri, bottom border, 8pt space-before
  - Company line:  10.5pt bold black Calibri, 8pt space-before (detected: contains " | "
                   with location keywords OR is preceded/followed by a role line)
  - Role line:     10pt normal Calibri (title • dates or title | dates)
  - Bullets:       10pt Calibri List Bullet, 0pt space-after
                   Bold inline label when line starts with "Bold Label: rest"
  - Additional Exp single line: bold label + normal body on same paragraph
  - Horizontal rules / sub-section --- markers: suppressed
  - Body text:     10pt Calibri, 1pt space-after
"""
from __future__ import annotations
import io
import logging
import os
import re
from datetime import date

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# All-caps section headers (SUMMARY, EXPERIENCE, EDUCATION, CORE SKILLS, etc.)
_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9\s&/\-]{2,}$")

# Sub-section labels like  --- Portfolio Performance Analytics ---  (suppressed)
_SUBSECTION_RE = re.compile(r"^-{2,3}\s+.+\s+-{2,3}$")

# Horizontal rule lines (all dashes / underscores / box-drawing chars, 4+ chars)
_HRULE_RE = re.compile(r"^[-─_]{4,}$")

# Bullet lines:  "- text"  or  "• text"
_BULLET_RE = re.compile(r"^[-•]\s+(.+)$")

# Company line heuristic: contains " | " and has a city/state or "Remote" keyword,
# OR contains " | " followed by a 4-digit year (old format fallback)
_COMPANY_RE = re.compile(
    r".+\|.+(?:Remote|NC|NY|CA|TX|FL|IL|GA|WA|CO|MA|OH|PA|VA|AZ|OR|MN|MI|NJ|DC|"
    r"[A-Z]{2}\s*\(Remote\)|[A-Z]{2}\))|.+\|\s*\d{4}"
)

# Role / title line: contains a bullet-dot (•) followed by 4-digit year range,
# or "| Contractor" pattern, or "| Senior" etc.
_ROLE_LINE_RE = re.compile(r"[•|]\s*\d{4}|Contractor\s*[•|]|\|\s*(Senior|Principal|Lead|Manager|Analyst|Director|VP|Engineer|Developer)")

# Inline bold label at start of bullet: "Bold Label: rest of text"
# Matches "Word(s): " where label is 1-4 words ending with a colon
_INLINE_BOLD_RE = re.compile(r"^([A-Za-z][A-Za-z\s&/\-]{1,40}):\s+(.+)$")

# "Additional Experience: ..." single-line
_ADDITIONAL_EXP_RE = re.compile(r"^Additional Experience:\s*(.+)$", re.IGNORECASE)


def _sanitize(text: str) -> str:
    """Strip XML-illegal control characters (keeps tab, newline, CR)."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def build_resume_docx(resume_text: str, template_path: str = None) -> bytes:
    """
    Build a resume .docx from resume_text.
    If template_path points to a valid .docx, inject content there.
    Otherwise build from scratch.
    Returns raw bytes suitable for a Flask response.
    """
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    resume_text = _sanitize(resume_text)

    if template_path and os.path.isfile(template_path):
        return _inject_into_template(resume_text, template_path, "[RESUME_CONTENT]")

    doc = Document()

    # ── Default style ────────────────────────────────────────────────────────
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    # ── Margins ──────────────────────────────────────────────────────────────
    for sec in doc.sections:
        sec.top_margin    = Inches(0.75)
        sec.bottom_margin = Inches(0.75)
        sec.left_margin   = Inches(0.75)
        sec.right_margin  = Inches(0.75)

    BLACK = RGBColor(0x00, 0x00, 0x00)
    GRAY  = RGBColor(0x47, 0x55, 0x69)

    lines = resume_text.splitlines()

    # ── Pass 1: locate structural anchor lines ───────────────────────────────
    name_idx    = next((i for i, l in enumerate(lines) if l.strip()), None)
    contact_idx = None
    tagline_idx = None
    first_section_idx = None

    if name_idx is not None:
        # Contact line: within 3 lines of name, contains @ or phone pattern or |
        for i in range(name_idx + 1, min(name_idx + 4, len(lines))):
            l = lines[i].strip()
            if l and ("|" in l or "•" in l or "@" in l or re.search(r"\d{3}[-.\s]\d{3}", l)):
                contact_idx = i
                break

        # First section header
        for i in range(name_idx + 1, len(lines)):
            if _SECTION_HEADER_RE.match(lines[i].strip()) and not _HRULE_RE.match(lines[i].strip()):
                first_section_idx = i
                break

        # Tagline: between contact and first section — non-empty, non-hrule, non-section-header
        if contact_idx is not None and first_section_idx is not None:
            for i in range(contact_idx + 1, first_section_idx):
                l = lines[i].strip()
                if l and not _HRULE_RE.match(l) and not _SECTION_HEADER_RE.match(l):
                    tagline_idx = i
                    break

    # ── Pass 2: render each line ─────────────────────────────────────────────
    i = 0
    while i < len(lines):
        raw      = lines[i]
        line     = raw.rstrip()
        stripped = line.strip()
        idx      = i
        i += 1

        # ── Name ────────────────────────────────────────────────────────────
        if idx == name_idx:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(2)
            run = p.add_run(stripped)
            run.bold = True
            run.font.name = "Calibri"
            run.font.size = Pt(18)
            run.font.color.rgb = BLACK
            continue

        # ── Contact line ─────────────────────────────────────────────────────
        if idx == contact_idx:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(3)
            run = p.add_run(stripped)
            run.font.name = "Calibri"
            run.font.size = Pt(9)
            run.font.color.rgb = GRAY
            continue

        # ── Tagline (headline / target role) ─────────────────────────────────
        if idx == tagline_idx:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after  = Pt(6)
            run = p.add_run(stripped)
            run.bold = True
            run.font.name = "Calibri"
            run.font.size = Pt(11)
            run.font.color.rgb = BLACK
            continue

        # ── Suppress horizontal rules and sub-section markers ────────────────
        if _HRULE_RE.match(stripped) or _SUBSECTION_RE.match(stripped):
            continue

        # ── Empty line ───────────────────────────────────────────────────────
        if not stripped:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(2)
            continue

        # ── All-caps section header ──────────────────────────────────────────
        if _SECTION_HEADER_RE.match(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after  = Pt(2)
            run = p.add_run(stripped)
            run.bold = True
            run.font.name = "Calibri"
            run.font.size = Pt(11)
            run.font.color.rgb = BLACK
            _add_bottom_border(p, color="000000")
            continue

        # ── Additional Experience single-line ────────────────────────────────
        m = _ADDITIONAL_EXP_RE.match(stripped)
        if m:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after  = Pt(2)
            bold_run = p.add_run("Additional Experience: ")
            bold_run.bold = True
            bold_run.font.name = "Calibri"
            bold_run.font.size = Pt(10)
            body_run = p.add_run(m.group(1))
            body_run.font.name = "Calibri"
            body_run.font.size = Pt(10)
            continue

        # ── Company line ─────────────────────────────────────────────────────
        if _COMPANY_RE.search(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after  = Pt(0)
            run = p.add_run(stripped)
            run.bold = True
            run.font.name = "Calibri"
            run.font.size = Pt(10.5)
            run.font.color.rgb = BLACK
            continue

        # ── Role / title line (title • dates or title | dates) ───────────────
        if _ROLE_LINE_RE.search(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(3)
            run = p.add_run(stripped)
            run.font.name = "Calibri"
            run.font.size = Pt(10)
            run.font.color.rgb = BLACK
            continue

        # ── Bullet point ─────────────────────────────────────────────────────
        bm = _BULLET_RE.match(stripped)
        if bm:
            text = bm.group(1)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(1)
            p.paragraph_format.left_indent  = Inches(0.25)
            # Check for inline bold label "Label: rest"
            lm = _INLINE_BOLD_RE.match(text)
            if lm:
                bold_run = p.add_run(lm.group(1) + ": ")
                bold_run.bold = True
                bold_run.font.name = "Calibri"
                bold_run.font.size = Pt(10)
                body_run = p.add_run(lm.group(2))
                body_run.font.name = "Calibri"
                body_run.font.size = Pt(10)
            else:
                run = p.add_run(text)
                run.font.name = "Calibri"
                run.font.size = Pt(10)
            continue

        # ── Default body text ────────────────────────────────────────────────
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(1)
        run = p.add_run(line)
        run.font.name = "Calibri"
        run.font.size = Pt(10)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _add_bottom_border(paragraph, color: str = "000000", sz: str = "4"):
    """Add a bottom paragraph border to visually underline a section header."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    pPr  = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"),   "single")
    bottom.set(qn("w:sz"),    sz)
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)


# ---------------------------------------------------------------------------
# Cover letter
# ---------------------------------------------------------------------------

def build_cover_letter_docx(cover_letter_text: str, template_path: str = None) -> bytes:
    """
    Build a cover letter .docx from cover_letter_text.
    If template_path points to a valid .docx, inject content there.
    Otherwise build from scratch.
    Returns raw bytes suitable for a Flask response.
    """
    from docx import Document
    from docx.shared import Pt, Inches

    cover_letter_text = _sanitize(cover_letter_text)

    if template_path and os.path.isfile(template_path):
        return _inject_into_template(cover_letter_text, template_path, "[COVER_LETTER_CONTENT]")

    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    for section in doc.sections:
        section.top_margin    = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin   = Inches(1.0)
        section.right_margin  = Inches(1.0)

    # Date header
    p = doc.add_paragraph(date.today().strftime("%B %d, %Y"))
    p.paragraph_format.space_after = Pt(12)
    for run in p.runs:
        run.font.name = "Calibri"
        run.font.size = Pt(11)

    # Body paragraphs
    for para in cover_letter_text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        p = doc.add_paragraph(para)
        p.paragraph_format.space_after = Pt(10)
        for run in p.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(11)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Template injection
# ---------------------------------------------------------------------------

def _inject_into_template(content: str, template_path: str, placeholder: str) -> bytes:
    """
    Open a .docx template, find the paragraph containing placeholder,
    replace it with the content lines, and return bytes.
    """
    from docx import Document
    from docx.shared import Pt
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document(template_path)

    target_para = None
    for para in doc.paragraphs:
        if placeholder in para.text:
            target_para = para
            break

    if target_para is None:
        logger.warning(
            "Placeholder '%s' not found in template %s — falling back to appending content.",
            placeholder, template_path
        )
        for line in content.splitlines():
            p = doc.add_paragraph(line.rstrip())
            for run in p.runs:
                run.font.size = Pt(10)
    else:
        parent = target_para._element.getparent()
        idx = list(parent).index(target_para._element)
        parent.remove(target_para._element)

        for j, line in enumerate(content.splitlines()):
            new_p = OxmlElement("w:p")
            new_r = OxmlElement("w:r")
            new_t = OxmlElement("w:t")
            new_t.text = line.rstrip()
            new_r.append(new_t)
            new_p.append(new_r)
            parent.insert(idx + j, new_p)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()
