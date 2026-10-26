"""Allow-list HTML sanitiser for message bodies, and a plain-text extractor."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

ALLOWED = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "a", "blockquote", "h3", "h4", "span",
           "div", "table", "thead", "tbody", "tr", "th", "td", "code", "pre"}
VOID = {"br"}
DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript"}
SAFE_HREF = re.compile(r"^(https?://|mailto:|/(?!/))", re.I)


class _Clean(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROP_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED:
            return
        if tag == "b":
            tag = "strong"
        if tag == "i":
            tag = "em"
        if tag == "a":
            href = next((v for k, v in attrs if k == "href" and v), "")
            href = (href or "").strip()
            if SAFE_HREF.match(href):
                self.out.append(f'<a href="{html.escape(href, quote=True)}" rel="noopener noreferrer" target="_blank">')
                self.stack.append("a")
            else:
                self.out.append("<span>")
                self.stack.append("span")
            return
        self.out.append(f"<{tag}>")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        tag = {"b": "strong", "i": "em"}.get(tag, tag)
        if tag in self.stack:
            while self.stack:
                top = self.stack.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def close(self) -> None:
        super().close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")


def sanitize_html(raw: str) -> str:
    p = _Clean()
    p.feed(raw or "")
    p.close()
    return "".join(p.out)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self.skip += 1
        elif tag in {"br", "p", "div", "li", "tr", "h3", "h4", "blockquote"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
        elif tag in {"p", "div", "li", "tr", "h3", "h4", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def to_text(clean_html: str) -> str:
    p = _Text()
    p.feed(clean_html or "")
    p.close()
    text = "".join(p.parts)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()
