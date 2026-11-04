"""Minimal inline Markdown: **bold**, *italic*, `code`, [text](url). Output is HTML-escaped."""
import html
import re

_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")


def esc(s):
    return html.escape(str(s), quote=True)


def inline(text):
    slots = []

    def keep(h):
        slots.append(h)
        return f"\x00{len(slots) - 1}\x00"

    text = _CODE.sub(lambda m: keep(f"<code>{esc(m.group(1))}</code>"), text)

    def link(m):
        url = m.group(2)
        if url.lower().startswith("javascript:"):
            url = "#"
        return keep(f'<a href="{esc(url)}" target="_blank" rel="noopener">{inline(m.group(1))}</a>')

    text = _LINK.sub(link, text)
    text = esc(text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITAL.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)
