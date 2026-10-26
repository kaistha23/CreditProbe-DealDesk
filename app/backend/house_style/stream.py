"""A fast house-style .xlsx writer for large row exports (stdlib only).

openpyxl spends most of its time per cell; an Early Warning list or a Data Builder extract can be
hundreds of thousands of cells, so this writes the SpreadsheetML directly and streams each sheet into
the zip. The look is the same as backend.house_style.xlsx: header block on rows 1-4, the styled table
header on HEADER_ROW, frozen panes, a filter, banded rows (conditional formatting), widths fitted to
the first rows, a number format per column kind, page numbers in the footer.

    from backend.house_style import Meta, stream
    from backend.house_style.xlsx import Col
    data = stream.write([
        stream.Sheet("Borrowers", meta, [Col("id", "Borrower ID"), Col("ead", "Exposure", "sar_mn")], rows),
        stream.about(meta, [("Rule set", "gw-ews-1.2.0")]),
    ], meta)

Rows are sequences in column order (or dicts, read by column key).
"""
from __future__ import annotations

import io
import itertools
import math
import re
import zipfile
from collections.abc import Iterable, Sequence
from typing import Any
from xml.sax.saxutils import escape

from backend.house_style import (ACCENT, BAND, CENTRED, FONT, FORMATS, HEADER_ROW, INK, MUTED, RULE, STYLE_ID, WHITE,
                                 Meta)
from backend.house_style.xlsx import Col

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
SAMPLE = 500

# cellXfs: fixed styles first, then one numeric style per FORMATS kind.
X_DEFAULT, X_BRAND, X_TITLE, X_META, X_HEADER, X_BODY, X_LABEL, X_NOTE, X_CENTRE = range(9)
_KINDS = [k for k in FORMATS if k not in ("", "text", "rating")]
_KIND_XF = {k: 9 + i for i, k in enumerate(_KINDS)}
X_INT = _KIND_XF["int"]
X_NUM = _KIND_XF["num"]


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _text(v: Any) -> str:
    return escape(_ILLEGAL.sub("", str(v)))[:32767]


def _cell(ref: str, v: Any, num_xf: int, text_xf: int) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return f'<c r="{ref}" t="b" s="{text_xf}"><v>{int(v)}</v></c>'
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return ""
        return f'<c r="{ref}" s="{num_xf}"><v>{v!r}</v></c>' if isinstance(v, float) else f'<c r="{ref}" s="{num_xf}"><v>{v}</v></c>'
    if isinstance(v, (list, tuple, set)):
        v = ", ".join(str(x) for x in v)
    return f'<c r="{ref}" t="inlineStr" s="{text_xf}"><is><t xml:space="preserve">{_text(v)}</t></is></c>'


class Sheet:
    """One house-style table sheet."""

    def __init__(self, name: str, meta: Meta, columns: Sequence[Col], rows: Iterable[Any] = (),
                 title: str | None = None, note: str | None = None, widths: dict[int, float] | None = None,
                 label_first: bool = False):
        self.name = re.sub(r"[\[\]:*?/\\]", "-", name)[:31]
        self.meta = meta
        self.columns = list(columns)
        self.rows = rows
        self.title = title
        self.note = note
        self.widths = widths or {}
        self.label_first = label_first
        self.count = 0           # data rows written


def about(meta: Meta, items: Sequence[tuple[str, Any]] = (), name: str = "About") -> Sheet:
    seen = {k for k, _ in items}
    rows = [(k, v) for k, v in meta.about_items() if k not in seen] + list(items)
    return Sheet(name, meta, [Col("item", "Item"), Col("value", "Value")], rows, title=f"About · {meta.title}",
                 widths={1: 30, 2: 100}, label_first=True)


def write(sheets: list[Sheet], meta: Meta) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        n = len(sheets)
        z.writestr("[Content_Types].xml", _content_types(n))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/'
                   'metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
        z.writestr("docProps/core.xml", _core(meta))
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{_text(s.name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, s in enumerate(sheets))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/'
                             f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                             for i in range(n))
                   + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/'
                     'officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", _styles())
        for i, s in enumerate(sheets):
            with z.open(f"xl/worksheets/sheet{i + 1}.xml", "w") as fh:
                _sheet(fh, s)
    return out.getvalue()


def _width_of(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, float):
        return len(f"{v:,.2f}")
    if isinstance(v, int) and not isinstance(v, bool):
        return len(f"{v:,}")
    return max((len(x) for x in str(v).split("\n")), default=0)


def _sheet(fh: Any, s: Sheet) -> None:
    cols = s.columns
    nc = max(1, len(cols))
    it = iter(s.rows)
    head_rows = [list(r.get(c.key) for c in cols) if isinstance(r, dict) else list(r) for r in itertools.islice(it, SAMPLE)]
    widths = [min(28, len(c.header())) + 2 for c in cols]
    for r in head_rows:
        for j, v in enumerate(r[:nc]):
            widths[j] = max(widths[j], _width_of(v))
    widths = [max(8, min(60, w + 2)) for w in widths]
    for j, w in s.widths.items():
        if 1 <= j <= len(widths):
            widths[j - 1] = w
    last_col = _col(nc - 1)
    head = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetPr><tabColor rgb="FF{ACCENT}"/><pageSetUpPr fitToPage="1"/></sheetPr>'
            '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
            f'<pane ySplit="{HEADER_ROW}" topLeftCell="A{HEADER_ROW + 1}" activePane="bottomLeft" state="frozen"/>'
            f'<selection pane="bottomLeft" activeCell="A{HEADER_ROW + 1}" sqref="A{HEADER_ROW + 1}"/>'
            '</sheetView></sheetViews>'
            "<cols>" + "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
            + "</cols><sheetData>")
    fh.write(head.encode())
    lines = s.meta.lines()
    if s.title:
        lines[1] = s.title
    top = []
    for i, (text, xf) in enumerate(zip(lines, (X_BRAND, X_TITLE, X_META, X_META)), start=1):
        ht = ' ht="22" customHeight="1"' if i == 2 else ""
        top.append(f'<row r="{i}"{ht}><c r="A{i}" t="inlineStr" s="{xf}"><is><t xml:space="preserve">{_text(text)}</t></is></c></row>')
    if s.note:
        top.append(f'<row r="5"><c r="A5" t="inlineStr" s="{X_NOTE}"><is><t xml:space="preserve">{_text(s.note)}</t></is></c></row>')
    top.append(f'<row r="{HEADER_ROW}" ht="30" customHeight="1">'
               + "".join(f'<c r="{_col(j)}{HEADER_ROW}" t="inlineStr" s="{X_HEADER}"><is><t xml:space="preserve">'
                         f'{_text(c.header())}</t></is></c>' for j, c in enumerate(cols)) + "</row>")
    fh.write("".join(top).encode("utf-8"))
    letters = [_col(j) for j in range(nc)]
    num_xf = [_KIND_XF.get(c.kind) for c in cols]
    text_xf = [X_CENTRE if c.kind in CENTRED else X_BODY for c in cols]
    if s.label_first:
        text_xf[0] = X_LABEL
    r = HEADER_ROW
    buf: list[str] = []

    def rows_iter():
        yield from head_rows
        for x in it:
            yield list(x.get(c.key) for c in cols) if isinstance(x, dict) else list(x)

    for row in rows_iter():
        r += 1
        cells = []
        for j, v in enumerate(row[:nc]):
            nx = num_xf[j] if num_xf[j] is not None else (X_INT if isinstance(v, int) else X_NUM)
            cells.append(_cell(f"{letters[j]}{r}", v, nx, text_xf[j]))
        buf.append(f'<row r="{r}">{"".join(cells)}</row>')
        if len(buf) >= 2000:
            fh.write("".join(buf).encode("utf-8"))
            buf = []
    s.count = r - HEADER_ROW
    if r == HEADER_ROW:
        r += 1
        buf.append(f'<row r="{r}"><c r="A{r}" t="inlineStr" s="{X_NOTE}"><is><t>(no rows)</t></is></c></row>')
    if buf:
        fh.write("".join(buf).encode("utf-8"))
    tail = (f'</sheetData><autoFilter ref="A{HEADER_ROW}:{last_col}{r}"/>'
            f'<conditionalFormatting sqref="A{HEADER_ROW + 1}:{last_col}{max(r, HEADER_ROW + 1)}">'
            '<cfRule type="expression" dxfId="0" priority="1"><formula>MOD(ROW(),2)=0</formula></cfRule>'
            '</conditionalFormatting>'
            '<pageMargins left="0.5" right="0.5" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
            '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
            f'<headerFooter><oddHeader>&amp;R{_text(s.meta.classification)}</oddHeader>'
            '<oddFooter>&amp;CCreditProbe · &amp;A · Page &amp;P of &amp;N</oddFooter></headerFooter>'
            '</worksheet>')
    fh.write(tail.encode("utf-8"))


def _font(size: float, color: str, bold: bool = False, italic: bool = False) -> str:
    return (f'<font>{"<b/>" if bold else ""}{"<i/>" if italic else ""}<sz val="{size}"/>'
            f'<color rgb="FF{color}"/><name val="{FONT}"/></font>')


def _styles() -> str:
    numfmts = {k: 164 + i for i, k in enumerate(_KINDS)}
    fonts = [_font(11, INK), _font(9, ACCENT, bold=True), _font(15, INK, bold=True), _font(9, MUTED),
             _font(10, WHITE, bold=True), _font(10, INK), _font(10, INK, bold=True), _font(9, MUTED, italic=True)]
    fills = ('<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
             f'<fill><patternFill patternType="solid"><fgColor rgb="FF{ACCENT}"/><bgColor indexed="64"/></patternFill></fill>')
    borders = ('<border><left/><right/><top/><bottom/><diagonal/></border>'
               f'<border><left/><right/><top/><bottom style="medium"><color rgb="FF{ACCENT}"/></bottom><diagonal/></border>'
               f'<border><left/><right/><top/><bottom style="thin"><color rgb="FF{RULE}"/></bottom><diagonal/></border>')
    xfs = ['<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>',
           '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
           '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
           '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
           '<xf numFmtId="0" fontId="4" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" '
           'applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>',
           '<xf numFmtId="0" fontId="5" fillId="0" borderId="2" xfId="0" applyFont="1" applyBorder="1"/>',
           '<xf numFmtId="0" fontId="6" fillId="0" borderId="2" xfId="0" applyFont="1" applyBorder="1"/>',
           '<xf numFmtId="0" fontId="7" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
           '<xf numFmtId="0" fontId="5" fillId="0" borderId="2" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">'
           '<alignment horizontal="center"/></xf>']
    xfs += [f'<xf numFmtId="{numfmts[k]}" fontId="5" fillId="0" borderId="2" xfId="0" applyNumberFormat="1" '
            'applyFont="1" applyBorder="1"/>' for k in _KINDS]
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<numFmts count="{len(numfmts)}">'
            + "".join(f'<numFmt numFmtId="{i}" formatCode="{escape(FORMATS[k], {chr(34): "&quot;"})}"/>' for k, i in numfmts.items())
            + f'</numFmts><fonts count="{len(fonts)}">' + "".join(fonts) + '</fonts>'
            f'<fills count="3">{fills}</fills><borders count="3">{borders}</borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">' + "".join(xfs) + '</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            f'<dxfs count="1"><dxf><fill><patternFill patternType="solid"><fgColor rgb="FF{BAND}"/>'
            f'<bgColor rgb="FF{BAND}"/></patternFill></fill></dxf></dxfs>'
            '</styleSheet>')


def _core(meta: Meta) -> str:
    when = meta.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{_text(meta.title)}</dc:title><dc:subject>{_text(meta.scope_line())}</dc:subject>'
            f'<dc:creator>{_text(meta.generated_by or "CreditProbe")}</dc:creator>'
            f'<cp:keywords>{STYLE_ID}</cp:keywords><dc:description>{_text(meta.generated_line())}</dc:description>'
            '<cp:category>CreditProbe export</cp:category>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{when}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{when}</dcterms:modified>'
            '</cp:coreProperties>')


def _content_types(n: int) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.'
            'core-properties+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/'
                      'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(n))
            + "</Types>")


__all__ = ["Sheet", "about", "write"]
