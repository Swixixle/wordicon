"""A Word document (.docx) from a document's structure — the export the
workspace instructions required beside text, Markdown and print (the
review of 6e5b59c: it was missing).

Minimal, hand-built OOXML (WordprocessingML), no library: the package is a
zip with [Content_Types].xml, the package relationships, word/document.xml,
word/styles.xml (Heading 1–6, List Bullet, List Number, Quote, Hyperlink),
word/numbering.xml (a bullet definition and one decimal definition per
ordered list, so each list starts at 1), the document's relationships (one
per hyperlink target) and docProps/core.xml (the title). What the schema
holds is what the file holds: paragraphs, headings (1–6), bullet and
ordered lists (nested, each item's first paragraph numbered, later
paragraphs indented under it), block quotes, bold, italic, links, hard
breaks. Text is written exactly (XML-escaped; xml:space="preserve" on
every run so leading and trailing spaces survive). Nothing is inferred
from the words; nothing is sent anywhere.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

import document_schema as ds

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _t(s: str) -> str:
    """Text for an XML text node: escaped; characters XML 1.0 cannot carry
    (the schema already refuses controls, but a plain body may hold them)
    become U+FFFD so the file stays well-formed."""
    return escape(_XML_BAD.sub("�", s))


class _Builder:
    def __init__(self):
        self.rels: list[tuple[str, str]] = []        # (rId, href)
        self.nums: list[str] = []                     # numbering instances: "bullet" | "decimal"
        self.body: list[str] = []

    def rel(self, href: str) -> str:
        rid = f"rId{len(self.rels) + 10}"
        self.rels.append((rid, href))
        return rid

    def num(self, kind: str) -> int:
        self.nums.append(kind)
        return len(self.nums)                         # numId, 1-based

    # ---- inline ----
    def runs(self, inline: list) -> str:
        out = []
        i = 0
        while i < len(inline):
            n = inline[i]
            if n.get("type") == "hard_break":
                out.append("<w:r><w:br/></w:r>")
                i += 1
                continue
            marks = {m["type"]: m for m in (n.get("marks") or [])}
            if "link" in marks:
                href = marks["link"]["attrs"]["href"]
                # consecutive text nodes under the same link share one hyperlink element
                group = []
                while i < len(inline) and inline[i].get("type") == "text" and any(m["type"] == "link" and m["attrs"]["href"] == href for m in (inline[i].get("marks") or [])):
                    group.append(inline[i])
                    i += 1
                rid = self.rel(href)
                out.append(f'<w:hyperlink r:id="{rid}">' + "".join(self.run(g, hyperlink=True) for g in group) + "</w:hyperlink>")
                continue
            out.append(self.run(n))
            i += 1
        return "".join(out)

    def run(self, n: dict, hyperlink: bool = False) -> str:
        marks = {m["type"] for m in (n.get("marks") or [])}
        props = []
        if hyperlink:
            props.append('<w:rStyle w:val="Hyperlink"/>')
        if "strong" in marks:
            props.append("<w:b/><w:bCs/>")
        if "em" in marks:
            props.append("<w:i/><w:iCs/>")
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        return f'<w:r>{rpr}<w:t xml:space="preserve">{_t(n.get("text", ""))}</w:t></w:r>'

    # ---- blocks ----
    def paragraph(self, inline: list, style: str = "", num: tuple[int, int] | None = None, indent_level: int | None = None) -> str:
        ppr = []
        if style:
            ppr.append(f'<w:pStyle w:val="{style}"/>')
        if num is not None:
            ppr.append(f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>')
        elif indent_level is not None:
            ppr.append(f'<w:ind w:left="{720 * (indent_level + 1)}"/>')
        ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
        return f"<w:p>{ppr_xml}{self.runs(inline)}</w:p>"

    def block(self, b: dict, quote: bool = False, list_ctx: tuple[int, int] | None = None) -> list[str]:
        t = b.get("type")
        if t == "paragraph":
            return [self.paragraph(b.get("content") or [], style=("Quote" if quote else ""))]
        if t == "heading":
            lvl = int((b.get("attrs") or {}).get("level") or 1)
            return [self.paragraph(b.get("content") or [], style=f"Heading{min(max(lvl, 1), 6)}")]
        if t == "blockquote":
            out = []
            for k in b.get("content") or []:
                out.extend(self.block(k, quote=True, list_ctx=list_ctx))
            return out
        if t in ("bullet_list", "ordered_list"):
            if list_ctx is None:
                num_id, level = self.num("bullet" if t == "bullet_list" else "decimal"), 0
            else:
                # a nested list continues its parent's numbering instance one level deeper;
                # a nested list of the other kind gets its own instance at that depth
                parent_id, parent_level = list_ctx
                if self.nums[parent_id - 1] == ("bullet" if t == "bullet_list" else "decimal"):
                    num_id, level = parent_id, parent_level + 1
                else:
                    num_id, level = self.num("bullet" if t == "bullet_list" else "decimal"), parent_level + 1
            out = []
            for item in b.get("content") or []:
                kids = item.get("content") or []
                for j, k in enumerate(kids):
                    if k.get("type") == "paragraph":
                        out.append(self.paragraph(k.get("content") or [], style=("Quote" if quote else ("ListBullet" if t == "bullet_list" else "ListNumber")),
                                                  num=(num_id, level) if j == 0 else None, indent_level=(level if j > 0 else None)))
                    else:
                        out.extend(self.block(k, quote=quote, list_ctx=(num_id, level)))
            return out
        return []


def build_docx(title: str, doc: dict) -> bytes:
    """The .docx bytes for a validated structure (document_schema v1)."""
    doc = ds.validate(doc)
    b = _Builder()
    for blk in doc.get("content") or []:
        b.body.extend(b.block(blk))
    if not b.body:
        b.body.append("<w:p/>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS_W}" xmlns:r="{NS_R}"><w:body>' + "".join(b.body) +
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
        + "".join(f'<Relationship Id="{rid}" Type="{REL_HYPERLINK}" Target="{escape(href, {chr(34): "&quot;"})}" TargetMode="External"/>' for rid, href in b.rels)
        + "</Relationships>"
    )
    abstract = []
    instances = []
    for i, kind in enumerate(b.nums, start=1):
        lvls = []
        for lvl in range(9):
            if kind == "bullet":
                lvls.append(f'<w:lvl w:ilvl="{lvl}"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="{"•" if lvl % 2 == 0 else "◦"}"/><w:lvlJc w:val="left"/>'
                            f'<w:pPr><w:ind w:left="{720 * (lvl + 1)}" w:hanging="360"/></w:pPr><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr></w:lvl>')
            else:
                fmt = ("decimal", "lowerLetter", "lowerRoman")[lvl % 3]
                lvls.append(f'<w:lvl w:ilvl="{lvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="%{lvl + 1}."/><w:lvlJc w:val="left"/>'
                            f'<w:pPr><w:ind w:left="{720 * (lvl + 1)}" w:hanging="360"/></w:pPr></w:lvl>')
        abstract.append(f'<w:abstractNum w:abstractNumId="{i}"><w:multiLevelType w:val="hybridMultilevel"/>' + "".join(lvls) + "</w:abstractNum>")
        instances.append(f'<w:num w:numId="{i}"><w:abstractNumId w:val="{i}"/></w:num>')
    numbering = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'<w:numbering xmlns:w="{NS_W}">' + "".join(abstract) + "".join(instances) + "</w:numbering>")
    heading_styles = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        f'<w:pPr><w:keepNext/><w:spacing w:before="{360 - 40 * n}" w:after="120"/><w:outlineLvl w:val="{n - 1}"/></w:pPr>'
        f'<w:rPr><w:b/><w:bCs/><w:sz w:val="{max(24, 40 - 4 * n)}"/><w:szCs w:val="{max(24, 40 - 4 * n)}"/></w:rPr></w:style>'
        for n in range(1, 7))
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{NS_W}">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia" w:cs="Georgia"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
        + heading_styles +
        '<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="ListNumber"><w:name w:val="List Number"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="999999"/></w:pBdr><w:ind w:left="567"/></w:pPr><w:rPr><w:i/><w:iCs/></w:rPr></w:style>'
        '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/></w:style>'
        '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
        "</w:styles>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{_t(title or '')}</dc:title><dc:creator>Nikodemus</dc:creator></cp:coreProperties>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


def docx_for_document(row: dict) -> bytes:
    """The .docx for a notebook head as notebook.get returns it: its
    structure when it carries one, else its plain body as paragraphs
    (blank-line separated, exactly as the plain projection reads it)."""
    import json
    if row.get("doc_json"):
        doc = row["doc_json"] if isinstance(row["doc_json"], dict) else json.loads(row["doc_json"])
    else:
        doc = ds.parse_plain(row.get("body") or "")
    return build_docx(row.get("display_title") or row.get("title") or "", doc)
