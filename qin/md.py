"""Küçük ve güvenli bir Markdown → HTML çevirici (özet e-postaları için).

Sitedeki site/js/md.js ile aynı alt kümeyi destekler: başlıklar, paragraflar, kalın/italik, satır içi
kod, bağlantılar, sıralı/sırasız (iç içe) listeler, alıntı, yatay çizgi, kod bloğu ve basit tablolar.
Ham HTML hiçbir zaman geçirilmez: metnin tamamı önce kaçışlanır, bağlantılar yalnızca http(s)/mailto olabilir.
"""
from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_FENCE = re.compile(r"^\s*```")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")

_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*([^\s()]+(?:\([^\s()]*\)[^\s()]*)*)\s*\)")
_URL = re.compile(r"(?<![\w/\x00])(https?://[^\s<>\x00]+[^\s<>\x00.,;:!?)\]}'\"])")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC = re.compile(r"(?<![\w*])([*_])(?=[^\s*_])(.+?)(?<=[^\s*_])\1(?![\w*])")
_SAFE_URL = re.compile(r"^(https?://|mailto:)", re.I)
_HELD = re.compile(r"\x00(\d+)\x00")


def _attr(tag: str, styles: dict | None, extra: str = "") -> str:
    style = (styles or {}).get(tag)
    return f"<{tag}{extra}" + (f' style="{style}"' if style else "") + ">"


def inline(text: str, styles: dict | None = None) -> str:
    """Satır içi biçimler. Kod ve bağlantılar önce ham metinden ayıklanıp yer tutucuya alınır;
    geri kalan her şey kaçışlanır, sonra kalın/italik uygulanır."""
    held: list[str] = []

    def hold(markup: str) -> str:
        held.append(markup)
        return f"\x00{len(held) - 1}\x00"

    def anchor(label: str, url: str) -> str | None:
        if not _SAFE_URL.match(url):
            return None
        cite = label.isdigit()                      # [3](adres): özetlerdeki atıf numarası
        style = (styles or {}).get("cite" if cite else "a")
        attrs = ' class="cite"' if cite else ""
        attrs += f' style="{style}"' if style else ""
        return hold(f'<a href="{html.escape(url)}"{attrs} target="_blank" rel="noopener noreferrer">'
                    f'{html.escape(label, quote=False)}</a>')

    text = text.replace("\x00", "")                 # yer tutucu işareti metinde bulunamaz
    out = _CODE.sub(lambda m: hold(_attr("code", styles) + html.escape(m.group(1), quote=False) + "</code>"), text)
    out = _LINK.sub(lambda m: anchor(m.group(1), m.group(2)) or m.group(0), out)
    out = _URL.sub(lambda m: anchor(m.group(1), m.group(1)) or m.group(0), out)
    out = html.escape(out, quote=False)
    out = _BOLD.sub(lambda m: f"<strong>{m.group(2)}</strong>", out)
    out = _ITALIC.sub(lambda m: f"<em>{m.group(2)}</em>", out)
    while _HELD.search(out):                        # bağlantı adının içinde kod olabilir: iç içe çöz
        out = _HELD.sub(lambda m: held[int(m.group(1))], out)
    return out


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _list(lines: list[str], styles: dict | None) -> str:
    """Girinti düzeyine göre (iç içe) liste. lines: yalnızca liste satırları ve devam satırları."""
    base = len(_ITEM.match(lines[0]).group(1))
    ordered = lines[0].lstrip()[0].isdigit()
    items: list[tuple[str, list[str]]] = []          # (metin, alt satırlar)
    for line in lines:
        m = _ITEM.match(line)
        if m and len(m.group(1)) <= base + 1:
            items.append((m.group(3), []))
        elif m:
            items[-1][1].append(line)
        elif items[-1][1]:
            items[-1][1].append(line)
        else:
            items[-1] = (items[-1][0] + " " + line.strip(), [])
    tag = "ol" if ordered else "ul"
    body = "".join(_attr("li", styles) + inline(text, styles) + (_list(sub, styles) if sub else "") + "</li>"
                   for text, sub in items)
    return _attr(tag, styles) + body + f"</{tag}>"


def render(text: str, styles: dict | None = None, _depth: int = 0) -> str:
    """Markdown metnini HTML'e çevirir. styles: etiket adı -> satır içi stil (e-posta için)."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _FENCE.match(line):
            j = i + 1
            while j < n and not _FENCE.match(lines[j]):
                j += 1
            out.append(_attr("pre", styles) + html.escape("\n".join(lines[i + 1:j]), quote=False) + "</pre>")
            i = j + 1
            continue
        if m := _HEADING.match(line):
            tag = f"h{min(len(m.group(1)) + 1, 4)}"        # sayfanın kendi h1'i var: # -> h2
            out.append(_attr(tag, styles) + inline(m.group(2), styles) + f"</{tag}>")
            i += 1
            continue
        if _HR.match(line):
            out.append(_attr("hr", styles))
            i += 1
            continue
        if "|" in line and i + 1 < n and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1]:
            head, j, rows = _cells(line), i + 2, []
            while j < n and lines[j].strip() and "|" in lines[j]:
                rows.append(_cells(lines[j]))
                j += 1
            th = "".join(_attr("th", styles) + inline(c, styles) + "</th>" for c in head)
            trs = "".join("<tr>" + "".join(_attr("td", styles) + inline(c, styles) + "</td>"
                                           for c in (r + [""] * len(head))[:len(head)]) + "</tr>" for r in rows)
            out.append(_attr("table", styles) + f"<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>")
            i = j
            continue
        if _QUOTE.match(line) and _depth < 8:
            j, quoted = i, []
            while j < n and _QUOTE.match(lines[j]):
                quoted.append(_QUOTE.match(lines[j]).group(1))
                j += 1
            out.append(_attr("blockquote", styles) + render("\n".join(quoted), styles, _depth + 1) + "</blockquote>")
            i = j
            continue
        if _ITEM.match(line):
            j = i + 1
            while j < n and (_ITEM.match(lines[j]) or (lines[j].strip() and lines[j][:1] in " \t")):
                j += 1
            out.append(_list(lines[i:j], styles))
            i = j
            continue
        j = i + 1                                          # paragraf: bir sonraki blok başlangıcına kadar
        while j < n and lines[j].strip() and not (
                _HEADING.match(lines[j]) or _HR.match(lines[j]) or _ITEM.match(lines[j])
                or (_QUOTE.match(lines[j]) and _depth < 8) or _FENCE.match(lines[j])):
            j += 1
        out.append(_attr("p", styles) + "<br>".join(inline(x.strip(), styles) for x in lines[i:j]) + "</p>")
        i = j
    return "\n".join(out)


def to_text(text: str) -> str:
    """E-postanın düz metin hali: bağlantılar 'başlık (adres)' olur, atıf numaraları sadeleşir."""
    out = re.sub(r"\[(\d{1,3})\]\([^)\s]+\)", r"[\1]", text or "")
    out = _LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", out)
    out = re.sub(r"^#{1,4}\s+", "", out, flags=re.M)
    return re.sub(r"(\*\*|__)", "", out).strip()
