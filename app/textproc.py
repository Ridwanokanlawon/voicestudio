"""Script reading and splitting: episodes, [pause] markers, sentences, .docx."""
import io
import re
import zipfile
from xml.etree import ElementTree

EP_HEAD = re.compile(r"^## (EP\d+) \|\s*(.*?)\s*$", re.M)
PAUSE = re.compile(r"\[pause\]", re.I)
SENT_SPLIT = re.compile(r"(?<=[.?!])[\"')\]]*\s+")


def parse_episodes(md: str):
    """Find '## EPxx | Title' blocks and return each one's voiceover ('> ' lines)."""
    heads = list(EP_HEAD.finditer(md))
    eps = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        body = md[h.end():end]
        vo = [l[2:].strip() for l in body.splitlines() if l.startswith("> ")]
        if vo:
            eps.append({"id": h.group(1), "title": h.group(2), "text": " ".join(vo)})
    return eps


def docx_to_text(data: bytes) -> str:
    """Plain text from a .docx using only the standard library."""
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines = []
    for p in root.iter(ns + "p"):
        parts = []
        for node in p.iter():
            if node.tag == ns + "t" and node.text:
                parts.append(node.text)
            elif node.tag in (ns + "tab",):
                parts.append("\t")
            elif node.tag in (ns + "br", ns + "cr"):
                parts.append("\n")
        style = p.find(f"{ns}pPr/{ns}pStyle")
        text = "".join(parts)
        if style is not None and text.strip():
            val = style.get(ns + "val", "")
            if val in ("Heading2", "heading 2") and not text.startswith("## "):
                text = "## " + text
            elif val in ("Quote", "IntenseQuote") and not text.startswith("> "):
                text = "> " + text
        lines.append(text)
    return "\n".join(lines)


def clean(text: str) -> str:
    lines = []
    for l in text.replace("\r", "").split("\n"):
        l = l.strip()
        if l.startswith("> "):
            l = l[2:]
        lines.append(l)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def split_script(text: str):
    """-> [{'type': 's', 'text': ...} | {'type': 'pause'}] in speaking order."""
    items = []
    segs = PAUSE.split(clean(text))
    for i, seg in enumerate(segs):
        sents = [s.strip() for s in SENT_SPLIT.split(seg) if s.strip()]
        sents = [s for s in sents if re.search(r"[A-Za-z0-9]", s)]
        if i and sents and items and items[-1]["type"] != "pause":
            items.append({"type": "pause"})
        items.extend({"type": "s", "text": s} for s in sents)
    while items and items[-1]["type"] == "pause":
        items.pop()
    return items


def sentences(text: str):
    return [it["text"] for it in split_script(text) if it["type"] == "s"]
