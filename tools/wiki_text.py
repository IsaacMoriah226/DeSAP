"""Turn a saved Fextralife wiki page (HTML) into plain text: the article block only, links kept as text."""
import html
import re
import sys
from pathlib import Path


def page_text(source: str) -> str:
    start = source.find('id="wiki-content-block"')
    body = source[start:] if start != -1 else source
    end = body.find('id="discussions-section"')
    if end != -1:
        body = body[:end]
    body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", "", body)
    body = re.sub(r"(?i)<img[^>]*alt=\"([^\"]*)\"[^>]*>", r" [img: \1] ", body)
    body = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>|</div>|</ul>|</table>", "\n", body)
    body = re.sub(r"(?i)</td>|</th>", " | ", body)
    body = re.sub(r"(?i)<li[^>]*>", "- ", body)
    body = re.sub(r"(?i)<h(\d)[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    title = text.find("\n# ")  # the page title (h1): everything before it is the site's navigation
    if title != -1:
        text = text[title + 1:]
    tail = text.find('\nRetrieved from "')
    if tail != -1:
        text = text[:tail]
    return text


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name in sys.argv[1:]:
        src = Path(name)
        out = src.with_suffix(".txt")
        out.write_text(page_text(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        print(out, out.stat().st_size)
