"""DOCX из научных текстов: native стили, таблицы, поля и Office Math."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT/"docs/publication"
AUTHOR = "Россинский Андрей Евгеньевич"
TITLE = "Метод семантической верификации восстановления вызовов инструментов при эволюции контрактов Model Context Protocol"
WIDTH = 9354


def element(name, **attributes):
    node = OxmlElement(name)
    for key, value in attributes.items():
        node.set(qn(key), str(value))
    return node


def font(style, size=14, bold=False):
    style.font.name = "Times New Roman"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attribute in list(fonts.attrib):
        if "theme" in attribute.lower():
            del fonts.attrib[attribute]
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:"+name), "Times New Roman")


def field(paragraph, instruction, cached):
    for kind in ("begin", "separate", "end"):
        run = paragraph.add_run()
        if kind == "begin":
            run._r.append(element("w:fldChar", **{"w:fldCharType": kind}))
            text = element("w:instrText", **{"xml:space": "preserve"})
            text.text = " "+instruction+" "
            run._r.append(text)
        elif kind == "separate":
            run._r.append(element("w:fldChar", **{"w:fldCharType": kind}))
            paragraph.add_run(str(cached))
        else:
            run._r.append(element("w:fldChar", **{"w:fldCharType": kind}))


def numbering(doc, *, headings=False):
    root = doc.part.numbering_part.element
    abstract_id = max(int(n.get(qn("w:abstractNumId"))) for n in root.findall(qn("w:abstractNum")))+1
    node = element("w:abstractNum", **{"w:abstractNumId": abstract_id})
    node.append(element("w:multiLevelType", **{"w:val": "multilevel" if headings else "singleLevel"}))
    for level in range(2 if headings else 1):
        item = element("w:lvl", **{"w:ilvl": level})
        item.append(element("w:start", **{"w:val": 1}))
        item.append(element("w:numFmt", **{"w:val": "decimal"}))
        item.append(element("w:lvlText", **{"w:val": "%1" if headings and not level else "%1.%2" if headings else "%1."}))
        item.append(element("w:suff", **{"w:val": "space"}))
        properties = element("w:pPr")
        properties.append(element("w:ind", **{"w:left": 0 if headings else 709,
                                                 "w:hanging": 0 if headings else 354}))
        item.append(properties)
        node.append(item)
    root.append(node)
    num = root.add_num(abstract_id)
    return num.numId


def set_number(paragraph, num_id, level=0):
    properties = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    properties.get_or_add_numId().val = num_id
    properties.get_or_add_ilvl().val = level


def math_run(text):
    run = element("m:r")
    child = element("m:t")
    child.text = text
    run.append(child)
    return run


def math_parts(text):
    if text == r"1-0{,}05^{1/n}":
        return [math_run("1 − "), fractional_power("0,05", "1", "n")]
    replacements = {r"\pi": "π", r"\land": "∧", r"\iff": "⇔", r"\sim": "∼",
                    r"\alpha": "α", r"\nu": "ν", r"\mathrm": "", r"\left": "", r"\right": ""}
    for old, new in replacements.items():
        text = text.replace(old, new)
    nodes = []
    offset = 0
    for match in re.finditer(r"([A-Za-zΑ-ω∼]+)_(?:\{([^}]+)\}|([A-Za-z0-9]+))", text):
        if match.start() > offset:
            nodes.append(math_run(text[offset:match.start()].replace("{", "").replace("}", "")))
        sub = element("m:sSub")
        for name, value in (("m:e", match[1]), ("m:sub", match[2] or match[3])):
            child = element(name)
            child.append(math_run(value))
            sub.append(child)
        nodes.append(sub)
        offset = match.end()
    if offset < len(text):
        nodes.append(math_run(text[offset:].replace("{", "").replace("}", "")))
    return nodes


def fraction(top, bottom):
    node = element("m:f")
    for name, value in (("m:num", top), ("m:den", bottom)):
        child = element(name)
        child.extend(math_parts(value))
        node.append(child)
    return node


def fractional_power(base_text, top, bottom):
    node = element("m:sSup")
    base, power = element("m:e"), element("m:sup")
    base.append(math_run(base_text))
    power.append(fraction(top, bottom))
    node.extend([base, power])
    return node


def equation_nodes(source):
    if "FAR" in source:
        return [math_run("FAR = "), fraction("FP", "FP + TN")]
    if "CRR" in source:
        return [math_run("CRR = "), fraction("C", "R"), math_run(";  UHR = "), fraction("U", "E"),
                math_run(";  FBR = "), fraction("B", "R")]
    if "alpha" in source:
        return [math_run("p ≤ 1 − "), fractional_power("α", "1", "n"), math_run(";  k = 0")]
    if "EXECUTE" in source:
        return math_parts(r"A = EXECUTE \iff D(P) \land V_{x} \land V_{y} \land Q \land H \land V_{S}")
    if "F_{old}" in source:
        return math_parts(r"N(\pi_{P}(F_{old}(x,S))) = N(\pi_{P}(F_{new}(T(x),S)))")
    if "W" in source:
        return math_parts(r"W = (h(C_{old}), h(C_{new}), h(x), h(T(x)), h(S), I, P, \nu, V, Q, H)")
    raise ValueError("unsupported publication equation: "+source)


class Builder:
    def __init__(self, report, page_map):
        self.doc, self.report, self.page_map = Document(), report, page_map
        for border in self.doc.styles.element.xpath(".//w:pBdr"):
            border.getparent().remove(border)
        section = self.doc.sections[0]
        section.page_width, section.page_height = Mm(210), Mm(297)
        section.left_margin, section.right_margin = Mm(30), Mm(15)
        section.top_margin = section.bottom_margin = Mm(20)
        section.header_distance = section.footer_distance = Mm(10)
        section.different_first_page_header_footer = report
        self.headings = numbering(self.doc, headings=True)
        self.heading_index, self.table_index, self.figure_index, self.equation_index = 0, 0, 0, 0
        self.ordered_num = None
        for name, size, bold in [("Normal", 14, False), ("Title", 14, True),
                                 ("Heading 1", 14, True), ("Heading 2", 14, True),
                                 ("Heading 3", 14, True), ("Caption", 14, False)]:
            font(self.doc.styles[name], size, bold)
        body = self.doc.styles["Normal"].paragraph_format
        body.alignment, body.first_line_indent = WD_ALIGN_PARAGRAPH.JUSTIFY, Cm(1.25)
        body.line_spacing, body.space_before, body.space_after = 1.5, Pt(0), Pt(0)
        body.widow_control = True
        for name in ("FrontHeading", "TableText", "TOC 1", "Equation", "FieldBoundary"):
            if name not in self.doc.styles:
                self.doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            font(self.doc.styles[name])
            fmt = self.doc.styles[name].paragraph_format
            fmt.first_line_indent, fmt.space_before, fmt.space_after = Cm(0), Pt(0), Pt(0)
            fmt.line_spacing, fmt.alignment = 1.5, WD_ALIGN_PARAGRAPH.LEFT
        font(self.doc.styles["FrontHeading"], bold=True)
        self.doc.styles["Normal"].element.get_or_add_rPr().append(element("w:lang", **{"w:val": "ru-RU"}))
        for name in ("Heading 1", "Heading 2", "Heading 3", "FrontHeading"):
            fmt = self.doc.styles[name].paragraph_format
            fmt.first_line_indent, fmt.space_before, fmt.space_after = Cm(0), Pt(12), Pt(6)
            fmt.keep_with_next = True
            fmt.line_spacing = 1.5
        self.doc.styles["FieldBoundary"].font.size = Pt(1)
        self.doc.styles["FieldBoundary"].paragraph_format.line_spacing = Pt(1)
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.paragraph_format.first_line_indent = Cm(0)
        field(footer, "PAGE", 1)
        if not report:
            section.different_first_page_header_footer = False
        self.doc.settings.element.append(element("w:updateFields", **{"w:val": "true"}))
        self.doc.core_properties.author = AUTHOR
        self.doc.core_properties.last_modified_by = AUTHOR
        self.doc.core_properties.title = TITLE
        self.doc.core_properties.subject = "Научная специальность 2.3.5"
        self.doc.core_properties.comments = ""
        self.doc.core_properties.created = self.doc.core_properties.modified = datetime.now(timezone.utc)

    def inline(self, paragraph, text):
        pattern = r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\\\(.*?\\\))"
        for piece in re.split(pattern, text):
            if piece.startswith("**"):
                paragraph.add_run(piece[2:-2]).bold = True
            elif piece.startswith("`"):
                paragraph.add_run(piece[1:-1])
            elif piece.startswith("\\("):
                node = element("m:oMath")
                node.extend(math_parts(piece[2:-2]))
                paragraph._p.append(node)
            elif (match := re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", piece)):
                hyperlink = element("w:hyperlink", **{"r:id": paragraph.part.relate_to(
                    match[2], "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)})
                run, node = element("w:r"), element("w:t")
                node.text = match[1]
                run.append(node)
                hyperlink.append(run)
                paragraph._p.append(hyperlink)
            else:
                paragraph.add_run(piece)

    def heading(self, title, level=1):
        paragraph = self.doc.add_paragraph(title, style="Heading "+str(level))
        set_number(paragraph, self.headings, level-1)
        if level == 1:
            self.heading_index += 1
            paragraph._p.append(element("w:bookmarkStart", **{"w:id": self.heading_index, "w:name": f"chapter{self.heading_index}"}))
            paragraph._p.append(element("w:bookmarkEnd", **{"w:id": self.heading_index}))
        return paragraph

    def toc(self, titles):
        start = self.doc.add_paragraph(style="FieldBoundary")
        start.add_run()._r.append(element("w:fldChar", **{"w:fldCharType": "begin"}))
        instruction = element("w:instrText", **{"xml:space": "preserve"})
        instruction.text = ' TOC \\o "1-1" \\h \\z \\u '
        start.add_run()._r.append(instruction)
        start.add_run()._r.append(element("w:fldChar", **{"w:fldCharType": "separate"}))
        for i, title in enumerate(titles, 1):
            paragraph = self.doc.add_paragraph(style="TOC 1")
            paragraph.paragraph_format.tab_stops.add_tab_stop(Mm(163), WD_TAB_ALIGNMENT.RIGHT)
            self.inline(paragraph, f"{i} {title}")
            paragraph.add_run("\t")
            field(paragraph, f"PAGEREF chapter{i} \\h", self.page_map.get(title, 0))
        paragraph.add_run()._r.append(element("w:fldChar", **{"w:fldCharType": "end"}))
        self.doc.add_page_break()

    def caption(self, kind, title):
        attribute = "table_index" if kind == "Таблица" else "figure_index"
        count = getattr(self, attribute)+1
        setattr(self, attribute, count)
        paragraph = self.doc.add_paragraph(style="Caption")
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.line_spacing = 1.5
        paragraph.paragraph_format.keep_with_next = kind == "Таблица"
        paragraph.paragraph_format.space_before = Pt(6)
        paragraph.paragraph_format.space_after = Pt(6)
        paragraph.add_run(kind+" ")
        field(paragraph, "SEQ "+("Table" if kind == "Таблица" else "Figure")+" \\* ARABIC", count)
        paragraph.add_run(" — "+title)

    def table(self, lines):
        rows = [[v.strip() for v in line.strip().strip("|").split("|")] for line in lines]
        rows = [row for row in rows if not all(re.fullmatch(r"[: -]+", cell) for cell in row)]
        columns = len(rows[0])
        if not all(len(row) == columns for row in rows):
            raise ValueError("ragged publication table")
        table = self.doc.add_table(rows=0, cols=columns)
        table.autofit = False
        width = WIDTH-120
        weights = [1.4]+[1]*(columns-1)
        widths = [round(width*w/sum(weights)) for w in weights]
        widths[-1] = width-sum(widths[:-1])
        properties = table._tbl.tblPr
        properties.find(qn("w:tblW")).set(qn("w:type"), "dxa")
        properties.find(qn("w:tblW")).set(qn("w:w"), str(width))
        properties.append(element("w:tblInd", **{"w:w": 120, "w:type": "dxa"}))
        margins = element("w:tblCellMar")
        for key, value in (("top", 70), ("bottom", 70), ("start", 120), ("end", 120)):
            margins.append(element("w:"+key, **{"w:w": value, "w:type": "dxa"}))
        properties.append(margins)
        borders = element("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(element("w:"+side, **{"w:val": "single", "w:sz": 4, "w:color": "777777"}))
        properties.append(borders)
        for grid, value in zip(table._tbl.tblGrid.gridCol_lst, widths):
            grid.set(qn("w:w"), str(value))
        for index, values in enumerate(rows):
            row = table.add_row()
            row._tr.get_or_add_trPr().append(element("w:cantSplit"))
            if index == 0:
                row._tr.get_or_add_trPr().append(element("w:tblHeader", **{"w:val": "true"}))
            for column, (cell, text, cell_width) in enumerate(zip(row.cells, values, widths)):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                cell._tc.get_or_add_tcPr().find(qn("w:tcW")).set(qn("w:w"), str(cell_width))
                paragraph = cell.paragraphs[0]
                paragraph.style = self.doc.styles["TableText"]
                if len(text) < 32 and column > 0:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self.inline(paragraph, text)
                if index == 0:
                    for run in paragraph.runs:
                        run.bold = True

    def equation(self, source):
        self.equation_index += 1
        paragraph = self.doc.add_paragraph(style="Equation")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = paragraph.paragraph_format.space_after = Pt(6)
        node = element("m:oMath")
        node.extend(equation_nodes(source))
        paragraph._p.append(node)
        paragraph.add_run("  (")
        field(paragraph, "SEQ Equation \\* ARABIC", self.equation_index)
        paragraph.add_run(")")

    def build(self, source):
        lines = source.splitlines()
        titles = [line[3:] for line in lines if line.startswith("## ") and line[3:] not in ("Аннотация", "Ключевые слова", "Оглавление")]
        if self.report:
            self.doc.add_paragraph("НАУЧНО-ТЕХНИЧЕСКИЙ ОТЧЁТ", style="Title")
            paragraph = self.doc.add_paragraph(TITLE, style="Title")
            paragraph.paragraph_format.space_before = Pt(65)
            paragraph.paragraph_format.space_after = Pt(35)
            for text in ("MCP-Compat", "Научная специальность 2.3.5", AUTHOR, "Франкфурт", "dennrbone@gmail.com", "2026"):
                p = self.doc.add_paragraph(text)
                p.alignment, p.paragraph_format.first_line_indent = WD_ALIGN_PARAGRAPH.CENTER, Cm(0)
            for p in self.doc.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.first_line_indent = Cm(0)
            self.doc.add_page_break()
        else:
            p = self.doc.add_paragraph(TITLE, style="Title")
            p.alignment, p.paragraph_format.first_line_indent = WD_ALIGN_PARAGRAPH.CENTER, Cm(0)
            p = self.doc.add_paragraph(AUTHOR+"\nФранкфурт; dennrbone@gmail.com")
            p.alignment, p.paragraph_format.first_line_indent = WD_ALIGN_PARAGRAPH.CENTER, Cm(0)
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith("# "):
                i += 1
                continue
            if line.startswith("## "):
                title = line[3:]
                if title in ("Аннотация", "Ключевые слова", "Оглавление"):
                    if title == "Оглавление":
                        self.doc.add_page_break()
                    self.doc.add_paragraph(title, style="FrontHeading")
                    if title == "Оглавление":
                        self.toc(titles)
                else:
                    self.heading(title)
                self.ordered_num = None
            elif line.startswith("### "):
                self.heading(line[4:], 2)
            elif line.startswith("Таблица — "):
                self.caption("Таблица", line[10:])
            elif line.startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                self.table(table_lines)
                continue
            elif line == r"\[":
                formula = []
                i += 1
                while lines[i].strip() != r"\]":
                    formula.append(lines[i])
                    i += 1
                self.equation(" ".join(formula))
            elif line.startswith("!["):
                match = re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)", line)
                p = self.doc.add_paragraph()
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.keep_with_next = True
                p.add_run().add_picture(str(CONTENT/match[2]), width=Mm(160))
                self.caption("Рисунок", match[1])
            else:
                text = [line]
                while i+1 < len(lines) and lines[i+1].strip() and not re.match(r"^(#|\||!\[|Таблица —|\\\[|\d{1,2}\.)", lines[i+1].strip()):
                    i += 1
                    text.append(lines[i].strip())
                value = " ".join(text)
                paragraph = self.doc.add_paragraph()
                ordered = re.match(r"^(\d{1,2})\.\s+(.+)", value)
                if ordered:
                    if self.ordered_num is None or ordered[1] == "1":
                        self.ordered_num = numbering(self.doc)
                    set_number(paragraph, self.ordered_num)
                    paragraph.paragraph_format.left_indent = Cm(1.25)
                    paragraph.paragraph_format.first_line_indent = Cm(-.625)
                    value = ordered[2]
                else:
                    self.ordered_num = None
                self.inline(paragraph, value)
            i += 1
        return self.doc


def build(output, page_map=None):
    output.mkdir(parents=True, exist_ok=True)
    page_map = CONTENT/"report-pages.json" if page_map is None else page_map
    mapping = json.loads(page_map.read_bytes()) if page_map.exists() else {}
    for name, report in (("SCIENTIFIC_REPORT", True), ("ARTICLE", False)):
        source = (CONTENT/(name+".md")).read_text()
        builder = Builder(report, mapping)
        doc = builder.build(source)
        assert builder.heading_index > 10 and builder.table_index > 1 and builder.equation_index > 2
        assert builder.figure_index >= 1
        target = output/("MCP_COMPAT_SCIENTIFIC_REPORT.docx" if report else "MCP_COMPAT_ARTICLE_VAK.docx")
        doc.save(target)
        check = Document(target)
        assert abs(check.sections[0].page_width - Mm(210)) < 635
        assert len(check.tables) == builder.table_index
        references = source.split("## Литература\n", 1)[1].split("\n## ", 1)[0]
        expected = len(re.findall(r"^\d{1,2}\. ", references, re.MULTILINE))
        paragraphs = check.paragraphs
        start = next(i for i, p in enumerate(paragraphs) if p.text == "Литература")
        cited = []
        for paragraph in paragraphs[start+1:]:
            if paragraph.style.name.startswith("Heading"):
                break
            if paragraph._p.xpath("./w:pPr/w:numPr"):
                cited.append(paragraph.text)
        assert len(cited) == expected == 18
        assert "1998." in cited[2]
        assert not any("^" in node.text or "\\" in node.text
                       for node in check.element.xpath(".//m:t") if node.text)
        print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=CONTENT)
    parser.add_argument("--page-map", type=Path)
    args = parser.parse_args()
    build(args.output, args.page_map)
