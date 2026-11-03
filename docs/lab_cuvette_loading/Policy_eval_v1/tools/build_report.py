"""Render a source-backed Chinese policy evaluation report with python-docx.

Run with the Codex bundled Python. Authoring is an explicit caller action:
the caller must run the documents skill artifact marker immediately before
the first authoring invocation, then render and inspect every resulting page.
This builder does not run the marker, download fonts, run models or train.

Input report_content.json consists of 8--12 deliberately composed pages. Each
page has a title and paragraph, heading, bullets, table, image or code blocks.
Numbers and conclusions are supplied by the analysis; missing values remain
N/A. No task outcome, interval, cost or sample count is invented here.

Examples of content blocks::

    {"type": "paragraph", "text": "Actual analysis narrative"}
    {"type": "table", "headers": ["Metric", "GPT", "Pi05"],
     "rows": [["Count", 1, 1]], "widths_cm": [7.2, 4.8, 4.8]}
    {"type": "image", "path": "analysis:figures/stages.png",
     "width_cm": 16.4, "height_cap_cm": 8.0, "caption": "Actual figure"}

Explicit image roots are analysis:, evidence: and content:. Absolute image
paths are allowed only inside those roots. A provenance list may bind actual
JSON/CSV/config inputs to the document's embedded core-property hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata


SCHEMA = "labsim.Policy_eval_v1.docx_builder.v1"
PAGE_WIDTH_CM = 21.0
MARGIN_CM = 2.1
CONTENT_WIDTH_CM = PAGE_WIDTH_CM - 2 * MARGIN_CM
MIN_PAGES = 8
MAX_PAGES = 12
KINDS = {"paragraph", "heading", "bullets", "table", "image", "code"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def display(value) -> str:
    """Retain missingness and exact supplied numbers rather than filling zeros."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite report value; use explicit null/N/A")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return str(value)


def load_json(path: Path):
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON constant in {path}: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def source_path(value, roots: dict[str, Path]) -> Path:
    """Resolve a declared evidence path without following an out-of-root link."""
    raw = str(value)
    match = re.match(r"^(analysis|evidence|content):(.*)$", raw)
    if match:
        root = roots[match.group(1)]
        relative = Path(match.group(2))
        if relative.is_absolute():
            raise ValueError("Prefixed source paths must be relative: " + raw)
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Source path escapes declared root: " + raw)
    else:
        supplied = Path(raw).expanduser()
        path = supplied.resolve() if supplied.is_absolute() else (roots["content"] / supplied).resolve()
        if not any(path.is_relative_to(root) for root in roots.values()):
            raise ValueError("Absolute source is outside declared roots: " + raw)
    if not path.is_file():
        raise FileNotFoundError("Report input does not exist: " + str(path))
    return path


def text_width(text) -> float:
    lines = display(text).splitlines() or [""]
    return max(sum(1.8 if unicodedata.east_asian_width(c) in "WF" else 1.0
                   for c in line) for line in lines)


def table_widths(block: dict) -> list[float]:
    headers = block["headers"]
    requested = block.get("widths_cm")
    if requested is not None:
        if len(requested) != len(headers):
            raise ValueError("Table widths must match header count")
        widths = [float(value) for value in requested]
        if (not all(math.isfinite(value) and value >= .7 for value in widths)
                or sum(widths) > CONTENT_WIDTH_CM + .01):
            raise ValueError(f"Table widths must be >=.7cm and total <={CONTENT_WIDTH_CM:.2f}cm")
        return widths
    # Deliberately allocate compact numerical/status columns and more room to
    # descriptive columns. Explicit widths remain preferable for final QA.
    rows = block["rows"]
    weights = []
    for index, header in enumerate(headers):
        entries = [text_width(header)] + [text_width(row[index]) for row in rows]
        mean = sum(entries) / len(entries)
        weights.append(max(1.0, math.sqrt(max(entries) * .45 + mean * .55)))
    minimum = 1.0
    remaining = CONTENT_WIDTH_CM - minimum * len(weights)
    if remaining <= 0:
        raise ValueError("Too many table columns for readable page width")
    total = sum(weights)
    return [minimum + remaining * value / total for value in weights]


def validate_content(content, roots):
    if not isinstance(content, dict):
        raise ValueError("report_content must be a JSON object")
    if not isinstance(content.get("title"), str) or not content["title"].strip():
        raise ValueError("A specific document title is required")
    pages = content.get("pages")
    if not isinstance(pages, list) or not MIN_PAGES <= len(pages) <= MAX_PAGES:
        raise ValueError(f"Provide {MIN_PAGES}--{MAX_PAGES} deliberately composed pages")
    evidence = []
    for page_index, page in enumerate(pages, 1):
        if not isinstance(page, dict) or not str(page.get("title", "")).strip():
            raise ValueError(f"Page {page_index} needs a title")
        blocks = page.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError(f"Page {page_index} needs content blocks")
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") not in KINDS:
                raise ValueError(f"Unsupported block on page {page_index}: {block!r}")
            kind = block["type"]
            if kind in {"paragraph", "heading", "code"}:
                if "text" not in block:
                    raise ValueError(f"{kind} needs text on page {page_index}")
                display(block["text"])
            elif kind == "bullets":
                if not isinstance(block.get("items"), list):
                    raise ValueError("bullets needs items")
            elif kind == "table":
                headers, rows = block.get("headers"), block.get("rows")
                if not isinstance(headers, list) or not 1 <= len(headers) <= 10:
                    raise ValueError("Table requires 1--10 headers")
                if not isinstance(rows, list) or not rows:
                    raise ValueError("Table requires actual rows")
                if any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
                    raise ValueError("Every table row must match header count")
                table_widths(block)
                for row in [headers, *rows]:
                    for cell in row:
                        display(cell)
            elif kind == "image":
                from PIL import Image
                path = source_path(block["path"], roots)
                with Image.open(path) as picture:
                    picture.verify()
                width = float(block.get("width_cm", CONTENT_WIDTH_CM))
                height = float(block.get("height_cap_cm", 9.0))
                if not .5 <= width <= CONTENT_WIDTH_CM + .01 or not .5 <= height <= 22:
                    raise ValueError("Image dimensions exceed page bounds")
                evidence.append(path)
    for value in content.get("sources", []):
        evidence.append(source_path(value["path"] if isinstance(value, dict) else value, roots))
    return list(dict.fromkeys(evidence))


def font_xml(properties, east_asian: str, size_pt: float | None = None):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    fonts = properties.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.insert(0, fonts)
    for attribute in ("ascii", "hAnsi", "cs"):
        fonts.set(qn("w:" + attribute), "Arial")
    fonts.set(qn("w:eastAsia"), east_asian)
    for attribute in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "csTheme"):
        fonts.attrib.pop(qn("w:" + attribute), None)
    if size_pt is not None:
        for tag in ("sz", "szCs"):
            item = properties.find(qn("w:" + tag))
            if item is None:
                item = OxmlElement("w:" + tag)
                properties.append(item)
            item.set(qn("w:val"), str(round(size_pt * 2)))


def style_run(run, *, size=None, bold=None, heading=False):
    from docx.shared import Pt, RGBColor
    run.font.name = "Arial"
    run.font.color.rgb = RGBColor(0, 0, 0)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    font_xml(run._element.get_or_add_rPr(), "黑体" if heading else "宋体", size)
    return run


def paragraph(document, text, *, size=None, bold=False, style=None):
    p = document.add_paragraph(style=style)
    p.paragraph_format.widow_control = True
    style_run(p.add_run(display(text)), size=size, bold=bold)
    return p


def configure(document, content):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(MARGIN_CM)
    section.top_margin, section.bottom_margin = Cm(1.65), Cm(1.65)
    section.header_distance = section.footer_distance = Cm(.75)
    for name in ("Normal", "Body Text", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3", "Caption", "Header", "Footer", "List Bullet"):
        style = document.styles[name]
        style.font.name = "Arial"
        style.font.color.rgb = RGBColor(0, 0, 0)
        is_heading = name in {"Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3", "Header"}
        size = {"Title": 22, "Subtitle": 11, "Heading 1": 16, "Heading 2": 12,
                "Heading 3": 11, "Caption": 9, "Header": 8.5, "Footer": 8.5}.get(name, 10.5)
        style.font.size = Pt(size)
        font_xml(style.element.get_or_add_rPr(), "黑体" if is_heading else "宋体", size)
        pf = style.paragraph_format
        pf.widow_control = True
        pf.space_before = Pt(8 if name.startswith("Heading") else 0)
        pf.space_after = Pt(5 if not name.startswith("Heading") else 6)
        pf.line_spacing = 1.22
        if name.startswith("Heading") or name == "Title":
            pf.keep_with_next = True
        # Inherited theme/title rules must not introduce a colored underline.
        props = style.element.get_or_add_pPr()
        for border in list(props.findall(qn("w:pBdr"))):
            props.remove(border)
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    style_run(header.add_run(content.get("header", "LabSim 器皿装载策略量化评测")), size=8.5, heading=True)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for text, field in (("第 ", None), (None, "PAGE"), (" 页  共 ", None), (None, "NUMPAGES"), (" 页", None)):
        if field:
            simple = OxmlElement("w:fldSimple")
            simple.set(qn("w:instr"), field)
            r = OxmlElement("w:r")
            properties = OxmlElement("w:rPr")
            font_xml(properties, "宋体", 8.5)
            r.append(properties)
            t = OxmlElement("w:t")
            t.text = "1"
            r.append(t)
            simple.append(r)
            footer._p.append(simple)
        else:
            style_run(footer.add_run(text), size=8.5)
    settings = document.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")
    document.core_properties.title = content["title"]
    document.core_properties.subject = content.get("subject", "固定场景下两套冻结策略的真实执行与成本评测")
    document.core_properties.author = content.get("author", "LabSim 项目组")
    document.core_properties.keywords = "LabSim, policy evaluation, Progress v1.2"


def add_table(document, block):
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
    if block.get("caption"):
        cap = paragraph(document, block["caption"], size=9)
        cap.paragraph_format.keep_with_next = True
    widths = table_widths(block)
    table = document.add_table(rows=1, cols=len(widths))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    props = table._tbl.tblPr
    table_width = props.find(qn("w:tblW"))
    if table_width is not None:
        table_width.set(qn("w:type"), "dxa")
        table_width.set(qn("w:w"), str(round(sum(widths) / 2.54 * 1440)))
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        side = OxmlElement("w:" + edge)
        side.set(qn("w:val"), "single")
        side.set(qn("w:sz"), "4")
        side.set(qn("w:color"), "D9D9D9")
        borders.append(side)
    props.append(borders)
    size = float(block.get("font_size_pt", 9.2))
    if not 8 <= size <= 12:
        raise ValueError("Table font must remain readable at 8--12 pt")
    for column, width in zip(table.columns, widths):
        column.width = Cm(width)
    values = [block["headers"], *block["rows"]]
    alignment = block.get("alignments")
    if alignment is not None and len(alignment) != len(widths):
        raise ValueError("Table alignments must match column count")
    for row_index, value_row in enumerate(values):
        row = table.rows[0] if row_index == 0 else table.add_row()
        trprops = row._tr.get_or_add_trPr()
        trprops.append(OxmlElement("w:cantSplit"))
        if row_index == 0:
            trprops.append(OxmlElement("w:tblHeader"))
        for index, (cell, value, width) in enumerate(zip(row.cells, value_row, widths)):
            cell.width = Cm(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            properties = cell._tc.get_or_add_tcPr()
            margins = OxmlElement("w:tcMar")
            for edge, amount in (("top", 70), ("bottom", 70), ("left", 85), ("right", 85)):
                item = OxmlElement("w:" + edge)
                item.set(qn("w:w"), str(amount))
                item.set(qn("w:type"), "dxa")
                margins.append(item)
            properties.append(margins)
            if row_index == 0 or row_index % 2 == 0:
                shading = OxmlElement("w:shd")
                shading.set(qn("w:fill"), "E9EDF1" if row_index == 0 else "F7F8F9")
                properties.append(shading)
            p = cell.paragraphs[0]
            pf = p.paragraph_format
            pf.space_before = pf.space_after = Pt(0)
            pf.line_spacing = 1.12
            pf.widow_control = True
            if alignment:
                align = alignment[index]
            else:
                align = "center" if row_index == 0 or (index > 0 and text_width(value) <= 22) else "left"
            p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                           "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
            style_run(p.add_run(display(value)), size=size, bold=row_index == 0, heading=row_index == 0)
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(3)
    spacer.paragraph_format.space_before = Pt(0)
    style_run(spacer.add_run(""), size=2)


def add_image(document, block, roots):
    from PIL import Image
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt
    path = source_path(block["path"], roots)
    with Image.open(path) as picture:
        width_px, height_px = picture.size
    width = float(block.get("width_cm", CONTENT_WIDTH_CM))
    height_cap = float(block.get("height_cap_cm", 9.0))
    height = width * height_px / width_px
    if height > height_cap:
        width *= height_cap / height
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = bool(block.get("caption"))
    run = p.add_run()
    shape = run.add_picture(str(path), width=Cm(width))
    shape._inline.docPr.set("descr", str(block.get("alt", block.get("caption", path.stem))))
    if block.get("caption"):
        cap = paragraph(document, block["caption"], size=9, style="Caption")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER


def build(content, roots, output, provenance):
    from docx import Document
    from docx.shared import Pt
    document = Document()
    configure(document, content)
    # Core properties have a 255-character limit. Preserve complete input
    # hashes in the printed receipt and bind their manifest inside the DOCX.
    source_manifest = json.dumps(provenance["inputs"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    source_manifest_sha = hashlib.sha256(source_manifest.encode()).hexdigest()
    document.core_properties.comments = (f"protocol={provenance['protocol_sha256']};"
                                        f"content={provenance['content_sha256']};"
                                        f"sources={source_manifest_sha}")
    for page_index, page in enumerate(content["pages"]):
        if page_index == 0:
            title = document.add_paragraph(style="Title")
            style_run(title.add_run(content["title"]), size=22, bold=True, heading=True)
            if content.get("subtitle"):
                paragraph(document, content["subtitle"], size=10.5)
            if content.get("metadata_lines"):
                for text in content["metadata_lines"]:
                    paragraph(document, text, size=9)
        heading = document.add_paragraph(style="Heading 1")
        heading.paragraph_format.page_break_before = page_index > 0
        style_run(heading.add_run(str(page["title"])), size=16, bold=True, heading=True)
        for block in page["blocks"]:
            kind = block["type"]
            if kind == "paragraph":
                p = paragraph(document, block["text"], size=block.get("font_size_pt"), bold=block.get("bold", False))
                p.paragraph_format.keep_with_next = bool(block.get("keep_with_next", False))
            elif kind == "heading":
                level = int(block.get("level", 2))
                if level not in (2, 3):
                    raise ValueError("In-page headings must use level2 or3")
                p = document.add_paragraph(style=f"Heading {level}")
                style_run(p.add_run(display(block["text"])), size=12 if level == 2 else 11, bold=True, heading=True)
            elif kind == "bullets":
                for item in block["items"]:
                    paragraph(document, item, style="List Bullet")
            elif kind == "code":
                for line in display(block["text"]).splitlines():
                    p = paragraph(document, line, size=9)
                    p.paragraph_format.space_after = Pt(1)
                    p.paragraph_format.line_spacing = 1.08
            elif kind == "table":
                add_table(document, block)
            elif kind == "image":
                add_image(document, block, roots)
    # Binary exclusive creation protects existing reports even if the caller
    # races another author after the preflight existence check.
    with output.open("xb") as destination:
        document.save(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New .docx file; never overwrite")
    parser.add_argument("--content", type=Path, help="Default: ANALYSIS_DIR/report_content.json")
    parser.add_argument("--validate-only", action="store_true", help="Inspect actual inputs without creating a document")
    args = parser.parse_args(argv)
    analysis = args.analysis_dir.expanduser().resolve()
    evidence = args.evidence_dir.expanduser().resolve()
    protocol = args.protocol.expanduser().resolve()
    content_path = (args.content or analysis / "report_content.json").expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not analysis.is_dir() or not evidence.is_dir():
        parser.error("Analysis and evidence directories must exist")
    if not protocol.is_file() or not content_path.is_file():
        parser.error("Protocol and report_content JSON must exist")
    if output.exists() or output.suffix.lower() != ".docx":
        parser.error("Output must be a new .docx file")
    roots = {"analysis": analysis, "evidence": evidence, "content": content_path.parent}
    content = load_json(content_path)
    load_json(protocol)  # Reject malformed/non-finite frozen protocol JSON.
    inputs = validate_content(content, roots)
    sources = list(dict.fromkeys([protocol, content_path, *inputs]))
    provenance = dict(schema=SCHEMA, protocol_sha256=digest(protocol), content_sha256=digest(content_path),
                      inputs=[dict(path=str(path), sha256=digest(path)) for path in sources],
                      planned_pages=len(content["pages"]), rendered_pages=None,
                      render_verification="Required after authoring; use bundled documents render_docx.py and inspect every PNG")
    if args.validate_only:
        print(json.dumps(dict(valid=True, authoring_performed=False, **provenance), ensure_ascii=False, indent=2))
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    build(content, roots, output, provenance)
    print(json.dumps(dict(created=True, output=str(output), bytes=output.stat().st_size,
                          sha256=digest(output), **provenance), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
