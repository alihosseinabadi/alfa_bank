"""Extract readable block text without executing embedded HTML or scripts."""
import json
import re
import unicodedata
from html.parser import HTMLParser

class StructuredTextExtractor(HTMLParser):
    BREAKS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote", "section"}
    HIDDEN = {"script", "style", "nav", "header", "footer", "noscript", "template"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = tag in self.HIDDEN or "hidden" in attrs or attrs.get("aria-hidden") == "true"
        style = attrs.get("style", "").replace(" ", "").lower()
        hidden = hidden or "display:none" in style or "visibility:hidden" in style
        if tag not in {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "embed", "param", "col", "base", "track"}:
            self.stack.append((tag, hidden))
        if tag in self.BREAKS and not any(x[1] for x in self.stack):
            self.parts.append("\n\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in self.BREAKS and not any(x[1] for x in self.stack):
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not any(x[1] for x in self.stack):
            self.parts.append(data)

def extract_text(value: str | None) -> str:
    parser = StructuredTextExtractor()
    parser.feed(value or "")
    parser.close()
    text = unicodedata.normalize("NFKC", "".join(parser.parts))
    lines = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n+", text)]
    return "\n\n".join(line for line in lines if line)

# Only these textual keys are admitted from Params. URLs, styles, code and opaque
# configuration must never become searchable prose.
TEXT_KEYS = {"text", "title", "caption", "description", "label", "placeholder", "heading", "content", "answer", "question", "alt"}

def parameter_text(value: str | None) -> str:
    if not value:
        return ""
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return ""
    parts = []
    def visit(node):
        if isinstance(node, dict):
            if any(key in node for key in ("advCode", "productCode", "metricTarget")):
                return
            for key, child in node.items():
                if key.lower() in TEXT_KEYS and isinstance(child, str):
                    text = extract_text(child)
                    if text:
                        parts.append(text)
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                if isinstance(child, str):
                    text = extract_text(child)
                    if text:
                        parts.append(text)
                else:
                    visit(child)
    visit(data)
    return "\n\n".join(dict.fromkeys(parts))

def block_text(html: str | None, params: str | None = None) -> str:
    parts = [extract_text(html), parameter_text(params)]
    return "\n\n".join(dict.fromkeys(x for x in parts if x))
