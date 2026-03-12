"""
modules/docx_builder.py — Build .docx files for resume and cover letter export.

Two modes:
  1. Template mode: open a user-supplied .docx, find the placeholder line, replace it.
  2. Scratch mode: build a cleanly formatted document from scratch.

Placeholder strings:
  Resume:       [RESUME_CONTENT]
  Cover letter: [COVER_LETTER_CONTENT]

Expected resume plain-text format (enforced in AI prompt):

  FIRST LAST
  City, ST • phone • email • website
  HEADLINE | SUBHEADLINE

  SECTION HEADER
  • Label: description
  • Label: description

  SECTION HEADER
  Company Name | City, ST (Remote)
  Title • YYYY–YYYY
  • Bullet one
  • Bullet two

  Additional Experience: Co — Title (YYYY) • Co — Title (YYYY)

  SECTION HEADER
  Degree — Institution

Line classification (in order of precedence):
  1. name_idx      — first non-empty line
  2. contact_idx   — contains • or @ or phone pattern, within 3 lines of name
  3. tagline_idx   — next non-empty, non-section-header line after contact
  4. section hdr   — ALL CAPS, 3+ chars
  5. company line  — contains " | " AND NOT a year-range after •
  6. role line     — contains • followed by 4-digit year
  7. bullet        — starts with •
  8. additional exp — starts with "Additional Experience:"
  9. body text     — everything else
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

_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9\s&/\-]{2,}$")
_BULLET_RE         = re.compile(r"^[•\-]\s+(.+)$")
_COMPANY_RE        = re.compile(r"^.+\s+\|\s+.+$")          # "Name | Location"
_ROLE_RE           = re.compile(r".+•\s*\d{4}")              # "Title • YYYY"
_INLINE_BOLD_RE    = re.compile(r"^([A-Za-z][A-Za-z\s&/\-]{1,40}):\s+(.+)$")
_ADDITIONAL_EXP_RE = re.compile(r"^Additional Experience:\s*(.+)$", re.IGNORECASE)


def _sanitize(text: str) -> str:
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

    # Default style
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    # Margins
    for sec in doc.sections:
        sec.top_margin    = Inches(0.75)
        sec.bottom_margin = Inches(0.75)
        sec.left_margin   = Inches(0.75)
        sec.right_margin  = Inches(0.75)

    BLACK = RGBColor(0x00, 0x00, 0x00)
    GRAY  = RGBColor(0x47, 0x55, 0x69)

    lines = [l.rstrip() for l in resume_text.splitlines()]

    # ── Locate structural anchor lines ──────────────────────────────────────
    name_idx = next((i for i, l in enumerate(lines) if l.strip()), None)
    contact_idx = None
    tagline_idx = None

    if name_idx is not None:
        for i in range(name_idx + 1, min(name_idx + 4, len(lines))):
            l = lines[i].strip()
            if l and ("•" in l or "@" in l or re.search(r"\d{3}[-.\s]\d{3}", l)):
                contact_idx = i
                break

        # Tagline: first non-empty non-section-header line after contact
        start = (contact_idx + 1) if contact_idx is not None else (name_idx + 1)
        for i in range(start, min(start + 5, len(lines))):
            l = lines[i].strip()
            if l and not _SECTION_HEADER_RE.match(l):
                tagline_idx = i
                break

    # ── Render ───────────────────────────────────────────────────────────────
    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Name
        if idx == name_idx:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(2)
            r = p.add_run(stripped)
            r.bold = True
            r.font.name = "Calibri"
            r.font.size = Pt(18)
            r.font.color.rgb = BLACK
            continue

        # Contact
        if idx == contact_idx:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(2)
            r = p.add_run(stripped)
            r.font.name = "Calibri"
            r.font.size = Pt(9)
            r.font.color.rgb = GRAY
            continue

        # Tagline
        if idx == tagline_idx:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after  = Pt(6)
            r = p.add_run(stripped)
            r.bold = True
            r.font.name = "Calibri"
            r.font.size = Pt(11)
            r.font.color.rgb = BLACK
            continue

        # Empty line → small spacer
        if not stripped:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(2)
            continue

        # Section header
        if _SECTION_HEADER_RE.match(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after  = Pt(2)
            r = p.add_run(stripped)
            r.bold = True
            r.font.name = "Calibri"
            r.font.size = Pt(11)
            r.font.color.rgb = BLACK
            _add_bottom_border(p)
            continue

        # Additional Experience single line
        m = _ADDITIONAL_EXP_RE.match(stripped)
        if m:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after  = Pt(2)
            r1 = p.add_run("Additional Experience: ")
            r1.bold = True
            r1.font.name = "Calibri"
            r1.font.size = Pt(10)
            r2 = p.add_run(m.group(1))
            r2.font.name = "Calibri"
            r2.font.size = Pt(10)
            continue

        # Bullet
        m = _BULLET_RE.match(stripped)
        if m:
            text = m.group(1)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(1)
            p.paragraph_format.left_indent  = Inches(0.25)
            lm = _INLINE_BOLD_RE.match(text)
            if lm:
                r1 = p.add_run(lm.group(1) + ": ")
                r1.bold = True
                r1.font.name = "Calibri"
                r1.font.size = Pt(10)
                r2 = p.add_run(lm.group(2))
                r2.font.name = "Calibri"
                r2.font.size = Pt(10)
            else:
                r = p.add_run(text)
                r.font.name = "Calibri"
                r.font.size = Pt(10)
            continue

        # Role line  "Title • YYYY–YYYY"  — check before company so it wins
        if _ROLE_RE.search(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(3)
            r = p.add_run(stripped)
            r.font.name = "Calibri"
            r.font.size = Pt(10)
            r.font.color.rgb = BLACK
            continue

        # Company line  "Name | Location"
        if _COMPANY_RE.match(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after  = Pt(0)
            r = p.add_run(stripped)
            r.bold = True
            r.font.name = "Calibri"
            r.font.size = Pt(10.5)
            r.font.color.rgb = BLACK
            continue

        # Body text (summary paragraph, education lines, etc.)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(2)
        r = p.add_run(stripped)
        r.font.name = "Calibri"
        r.font.size = Pt(10)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _add_bottom_border(paragraph, color: str = "000000", sz: str = "4"):
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

    p = doc.add_paragraph(date.today().strftime("%B %d, %Y"))
    p.paragraph_format.space_after = Pt(12)
    for r in p.runs:
        r.font.name = "Calibri"
        r.font.size = Pt(11)

    for para in cover_letter_text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        p = doc.add_paragraph(para)
        p.paragraph_format.space_after = Pt(10)
        for r in p.runs:
            r.font.name = "Calibri"
            r.font.size = Pt(11)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Template injection
# ---------------------------------------------------------------------------

def _inject_into_template(content: str, template_path: str, placeholder: str) -> bytes:
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
            "Placeholder '%s' not found in template %s — appending content.",
            placeholder, template_path
        )
        for line in content.splitlines():
            p = doc.add_paragraph(line.rstrip())
            for r in p.runs:
                r.font.size = Pt(10)
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
