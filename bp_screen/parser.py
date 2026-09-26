# -*- coding: utf-8 -*-
"""L1 文档解析：PDF(pdfplumber) / Excel(openpyxl) / Word(zip+xml) / 文本 —— 统一输出 pages 结构"""
import os, re, zipfile
from dataclasses import dataclass, field


@dataclass
class ParsedFile:
    filename: str
    ftype: str                       # pdf/excel/word/text/image/unknown
    pages: list = field(default_factory=list)   # [{page, text, tables:[[{cell}]] , source:"页3/Sheet2"}]
    error: str = ""


def parse_file(path, filename) -> ParsedFile:
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext == ".pdf":
            return _parse_pdf(path, filename)
        if ext in (".xlsx", ".xls", ".csv"):
            return _parse_excel(path, filename)
        if ext in (".docx",):
            return _parse_docx(path, filename)
        if ext in (".txt", ".md"):
            return _parse_text(path, filename)
        return ParsedFile(filename=filename, ftype="unknown", error=f"暂不支持 {ext} 格式（MVP：PDF/Word/Excel/TXT）")
    except Exception as e:
        return ParsedFile(filename=filename, ftype=ext.lstrip("."), error=f"解析失败：{e}")


def _parse_pdf(path, filename):
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages, 1):
            text = pg.extract_text() or ""
            tables = pg.extract_tables() or []
            # 表格文本并入正文，保证正则可命中
            tbl_text = "\n".join(" ".join(str(c) for c in row if c) for t in tables for row in t)
            pages.append({"page": i, "text": text + "\n" + tbl_text, "tables": tables, "source": f"PDF第{i}页"})
    return ParsedFile(filename=filename, ftype="pdf", pages=pages)


def _parse_excel(path, filename):
    pages = []
    if filename.lower().endswith(".csv"):
        import pandas as pd
        df = pd.read_csv(path, header=None).fillna("")
        text = "\n".join(" ".join(str(v) for v in row) for row in df.values.tolist())
        pages.append({"page": 1, "text": text, "tables": [df.values.tolist()], "source": "CSV"})
        return ParsedFile(filename=filename, ftype="excel", pages=pages)
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v) for v in row]
            if any(v.strip() for v in vals):
                rows.append(vals)
        text = "\n".join(" ".join(v for v in r if v.strip()) for r in rows)
        pages.append({"page": ws.title, "text": text, "tables": [rows], "source": f"Sheet[{ws.title}]"})
    wb.close()
    return ParsedFile(filename=filename, ftype="excel", pages=pages)


def _parse_docx(path, filename):
    """docx = zip + document.xml；提取 w:t 文本与表格（无 python-docx 依赖）"""
    out_pages, buf = [], []
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    # 段落切分
    paras = re.split(r"</w:p>", xml)
    for p in paras:
        ts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)
        if ts:
            buf.append("".join(ts))
        if len(buf) >= 40:   # 40 段一页
            out_pages.append({"page": len(out_pages) + 1, "text": "\n".join(buf), "tables": [], "source": f"Word段{len(out_pages)*40-39}+"})
            buf = []
    if buf:
        out_pages.append({"page": len(out_pages) + 1, "text": "\n".join(buf), "tables": [], "source": f"Word段{len(out_pages)*40-39}+"})
    return ParsedFile(filename=filename, ftype="word", pages=out_pages)


def _parse_text(path, filename):
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)]
    return ParsedFile(filename=filename, ftype="text",
                      pages=[{"page": i + 1, "text": c, "tables": [], "source": f"文本块{i+1}"} for i, c in enumerate(chunks)])


def full_text(pf: ParsedFile) -> str:
    return "\n".join(p["text"] for p in pf.pages)
