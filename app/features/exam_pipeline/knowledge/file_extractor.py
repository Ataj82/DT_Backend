"""
Backend/app/features/exam_pipeline/knowledge/file_extractor.py

Lightweight, robust, pure-Python document text extractor for academic exam materials.
Supports:
- Text files: .txt, .md, .csv, .json (with multi-encoding support: utf-8, windows-1256, etc.)
- Office documents: .docx, .pptx (via standard zipfile and xml parsing)
- PDF documents: .pdf (via stream extraction and FlateDecode decompression)
"""

from __future__ import annotations

import io
import json
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib

logger = logging.getLogger("file_extractor")


def extract_text_from_file_bytes(filename: str, content_bytes: bytes, max_chars: int = 25000) -> str:
    """
    Extracts text from file bytes based on the file extension.
    Truncates to `max_chars` to keep within reasonable LLM context limits.
    """
    if not content_bytes:
        return ""

    ext = filename.lower().split(".")[-1] if "." in filename else ""

    text = ""
    try:
        if ext in ("txt", "md", "csv", "rst"):
            text = _extract_plain_text(content_bytes)
        elif ext == "json":
            text = _extract_json_text(content_bytes)
        elif ext == "docx":
            text = _extract_docx(content_bytes)
        elif ext == "pptx":
            text = _extract_pptx(content_bytes)
        elif ext == "pdf":
            text = _extract_pdf(content_bytes)
        else:
            # Fallback attempt plain text
            text = _extract_plain_text(content_bytes)
    except Exception as exc:
        logger.warning("Failed to parse file %s as %s: %s. Falling back to plain text.", filename, ext, exc)
        text = _extract_plain_text(content_bytes)

    cleaned = _clean_text(text)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n\n[...ادامه متن به دلیل محدودیت پردازش کوتاه شد...]"
    return cleaned


def _extract_plain_text(content_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "windows-1256", "cp1256", "latin-1", "iso-8859-1"):
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content_bytes.decode("utf-8", errors="ignore")


def _extract_json_text(content_bytes: bytes) -> str:
    raw_str = _extract_plain_text(content_bytes)
    try:
        data = json.loads(raw_str)
        if isinstance(data, list):
            parts = []
            for item in data:
                if isinstance(item, dict):
                    parts.append(" - ".join(str(v) for v in item.values() if v))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        elif isinstance(data, dict):
            return "\n".join(f"{k}: {v}" for k, v in data.items() if v)
        return str(data)
    except Exception:
        return raw_str


def _extract_docx(content_bytes: bytes) -> str:
    """Extracts text from word/document.xml in DOCX zip archive."""
    with io.BytesIO(content_bytes) as bio:
        with zipfile.ZipFile(bio) as zf:
            xml_content = zf.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Namespace for Word OpenXML
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for p in tree.iterfind(".//w:p", ns):
                texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                if texts:
                    paragraphs.append("".join(texts))
            return "\n".join(paragraphs)


def _extract_pptx(content_bytes: bytes) -> str:
    """Extracts text from ppt/slides/slide*.xml in PPTX zip archive."""
    paragraphs = []
    with io.BytesIO(content_bytes) as bio:
        with zipfile.ZipFile(bio) as zf:
            slide_names = sorted([n for n in zf.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", n)])
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for idx, sname in enumerate(slide_names):
                paragraphs.append(f"\n--- اسلاید {idx + 1} ---")
                xml_content = zf.read(sname)
                tree = ET.fromstring(xml_content)
                for p in tree.iterfind(".//a:p", ns):
                    texts = [node.text for node in p.iterfind(".//a:t", ns) if node.text]
                    if texts:
                        paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def _extract_pdf(content_bytes: bytes) -> str:
    """
    Extracts readable text from PDF streams (handling FlateDecode streams and ASCII/Unicode strings).
    """
    extracted_chunks = []

    # 1. Match stream blocks
    stream_pattern = re.compile(b"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
    for match in stream_pattern.finditer(content_bytes):
        stream_data = match.group(1)
        decompressed = None
        try:
            decompressed = zlib.decompress(stream_data)
        except Exception:
            try:
                # Handle raw deflate without header
                decompressed = zlib.decompress(stream_data, -zlib.MAX_WBITS)
            except Exception:
                decompressed = stream_data

        if not decompressed:
            continue

        # Look for PDF text show operators: (text) Tj or [(text)] TJ
        try:
            tj_matches = re.findall(b"\\(([^)]*)\\)\\s*(?:Tj|TJ|\')?", decompressed)
            for raw_chunk in tj_matches:
                for enc in ("utf-8", "utf-16-be", "windows-1256", "latin-1"):
                    try:
                        decoded = raw_chunk.decode(enc)
                        if len(decoded.strip()) > 1 and any("\u0600" <= c <= "\u06FF" or c.isalnum() for c in decoded):
                            extracted_chunks.append(decoded)
                            break
                    except UnicodeDecodeError:
                        continue

            hex_matches = re.findall(b"<([0-9a-fA-F]{4,})>\\s*(?:Tj|TJ|\')?", decompressed)
            for hx in hex_matches:
                try:
                    raw_bytes = bytes.fromhex(hx.decode("ascii"))
                    for enc in ("utf-16-be", "utf-8", "windows-1256"):
                        try:
                            dec = raw_bytes.decode(enc)
                            if len(dec.strip()) > 1 and any("\u0600" <= c <= "\u06FF" or c.isalnum() for c in dec):
                                extracted_chunks.append(dec)
                                break
                        except UnicodeDecodeError:
                            continue
                except Exception:
                    pass
        except Exception:
            pass

    # 2. If stream parsing gave very little text, scan top-level printable characters
    if len("".join(extracted_chunks).strip()) < 50:
        words = re.findall(rb"[\x20-\x7E\xD8\xA0-\xDB\xBF]{3,}", content_bytes)
        for w in words[:500]:
            try:
                s = w.decode("utf-8", errors="ignore").strip()
                if len(s) > 3 and not s.startswith("obj") and not s.startswith("endobj"):
                    extracted_chunks.append(s)
            except Exception:
                pass

    return "\n".join(extracted_chunks)


def _clean_text(text: str) -> str:
    """Clean redundant spaces and lines."""
    if not text:
        return ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def optimize_content_for_llm(text: str, filename: str = "", max_chars: int = 2000) -> str:
    """
    Intelligently extracts and condenses the highest-signal educational concepts,
    chapter/section headings, outlines, and definitions from document text.
    Guarantees the output length stays strictly under `max_chars` (default 2000 chars),
    safely fitting within the LLM 4096-token context window without 400 Bad Request errors.
    """
    if not text or not text.strip():
        return ""

    cleaned = _clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned

    # 1. Clean and filter out noise lines (page numbers, PDF metadata, isolated symbols)
    raw_lines = [l.strip() for l in cleaned.splitlines()]
    meaningful_lines = []
    seen = set()

    for line in raw_lines:
        if not line or len(line) < 3:
            continue

        norm = line.lower()
        if norm in seen:
            continue
        seen.add(norm)

        # Skip noise / PDF artifact lines
        if re.match(r"^[\d\s\-_./\\()]+$", line):
            continue
        if re.match(r"^(page|صفحه)\s*[\d۰-۹]+(\s*(of|از)\s*[\d۰-۹]+)?", line, re.IGNORECASE):
            continue
        if any(bad in line for bad in ["<<", ">>", "/Type", "/Font", "/Filter", "endobj", "stream"]):
            continue

        meaningful_lines.append(line)

    if not meaningful_lines:
        return cleaned[:max_chars]

    # 2. Identify high-signal pedagogical lines
    heading_pattern = re.compile(
        r"^(فصل|بخش|مبحث|درس|جلسه|واحد|پروژه|مقدمه|خلاصه|سرفصل|اهداف|تعریف|الگوریتم|روش|انواع|معماری|سیستم|"
        r"chapter|section|unit|lecture|topic|syllabus|overview|summary|algorithm|concept|architecture|outline)",
        re.IGNORECASE
    )
    bullet_pattern = re.compile(r"^([\d۰-۹]+[-.)]|[-*•▪▫])\s*")
    concept_keywords = [
        "تعریف", "مفهوم", "ویژگی", "مزایا", "معایب", "کاربرد", "نحوه عملکرد", "ساختار", "فرآیند", "ریسه‌بندی",
        "حافظه", "زمان‌بندی", "بن‌بست", "همگام‌سازی", "امنیت", "ارزیابی", "طراحی", "پیاده‌سازی", "مدیریت",
        "definition", "algorithm", "process", "thread", "memory", "paging", "deadlock", "scheduling", "cache"
    ]

    high_priority = []
    other_lines = []

    for idx, line in enumerate(meaningful_lines):
        is_heading = bool(heading_pattern.search(line)) or (len(line) < 80 and not line.endswith("."))
        is_bullet = bool(bullet_pattern.search(line))
        has_keywords = any(kw in line.lower() for kw in concept_keywords)

        if is_heading or is_bullet or has_keywords:
            high_priority.append((idx, line))
        else:
            other_lines.append((idx, line))

    collected = []
    current_length = 0

    # 3. Take high-priority headings and outline items up to 70% of budget
    target_high_budget = int(max_chars * 0.70)
    for idx, line in high_priority:
        if current_length + len(line) + 2 <= target_high_budget:
            collected.append((idx, line))
            current_length += len(line) + 2
        else:
            break

    # 4. Fill remaining space by stratified sampling from the document
    if current_length < max_chars and other_lines:
        step = max(1, len(other_lines) // 6)
        for i in range(0, len(other_lines), step):
            idx, line = other_lines[i]
            if current_length + len(line) + 2 <= max_chars:
                collected.append((idx, line))
                current_length += len(line) + 2
            else:
                break

    # 5. Fallback: if very few lines were selected, take early lines
    if not collected:
        for idx, line in enumerate(meaningful_lines):
            if current_length + len(line) + 2 <= max_chars:
                collected.append((idx, line))
                current_length += len(line) + 2
            else:
                break

    collected.sort(key=lambda x: x[0])
    result = "\n".join(item[1] for item in collected)
    if len(result) > max_chars:
        result = result[:max_chars].rsplit("\n", 1)[0]
    return result.strip()
