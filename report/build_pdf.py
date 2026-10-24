"""Build report/report.pdf from report/report.md: python-markdown (tables, attr) -> HTML with print CSS ->
headless Google Chrome --print-to-pdf. Only the build needs `markdown` (3.7), not the modelling code.
Run: PYTHONPATH=<dir with markdown> /usr/bin/python3 report/build_pdf.py
"""
import re
import subprocess
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "Times New Roman", Times, serif; font-size: 10pt; line-height: 1.25; color: #000; background: #fff; }
h1.title { font-size: 17pt; text-align: center; margin: 0 0 4pt; line-height: 1.2; }
p.byline { text-align: center; font-style: italic; margin: 0 0 10pt; }
h2 { font-size: 11.5pt; text-transform: uppercase; letter-spacing: .03em; margin: 14pt 0 5pt; text-align: center; }
h3 { font-size: 10.5pt; font-style: italic; margin: 9pt 0 3pt; }
p { margin: 0 0 6pt; text-align: justify; }
table { border-collapse: collapse; margin: 4pt auto 8pt; font-size: 8.4pt; line-height: 1.2; page-break-inside: avoid; }
th, td { border-top: .5pt solid #000; border-bottom: .5pt solid #000; padding: 1.6pt 4pt; vertical-align: top; text-align: left; }
th { font-weight: bold; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.6pt; }
div.tb { break-inside: avoid; page-break-inside: avoid; }
div.cols { column-count: 2; column-gap: 6mm; column-fill: auto; }
div.cols table { width: 100%; font-size: 7.8pt; }
div.lead p { text-align: center; }
div.cols h2 { font-size: 10pt; margin: 9pt 0 4pt; }
div.cols p, div.cols li { text-align: justify; hyphens: auto; }
div.appendix { break-before: page; }
div.appendix table { font-size: 7.8pt; }
img { max-width: 100%; display: block; margin: 4pt auto 2pt; border: .5pt solid #999; }
div.fig { break-inside: avoid; margin: 4pt 0 6pt; column-span: all; }
div.fig.col { column-span: none; }
img[src$="hand_join_check.png"], img[src$="hand_ap_check.png"] { width: 100%; }
img[src$="hand_reveal_check.png"] { width: 75%; }
img[src$="kaggle_best_private.png"] { width: 100%; }
div.fig p { text-align: center; font-size: 8.5pt; margin: 0 0 2pt; }
span.missing { display: block; border: 1pt dashed #c00; color: #c00; padding: 10pt 4pt; text-align: center; font-size: 8.5pt; }
ol, ul { margin: 0 0 6pt 16pt; padding: 0; }
li { margin-bottom: 2pt; text-align: justify; }
"""


def main():
    md = (HERE / "report.md").read_text()
    m = re.match(r"---\n(.*?)\n---\n", md, re.S)
    meta = dict(re.findall(r'^(\w+): "(.*)"$', m.group(1), re.M))
    body = markdown.markdown(md[m.end():], extensions=["tables", "sane_lists"])
    # keep each "TABLE ..." caption on the same page as its table
    body = re.sub(r"(<p>TABLE [^<]*(?:<[^/][^>]*>[^<]*</[^>]+>[^<]*)*</p>\s*<table>.*?</table>)", r"<div class='tb'>\1</div>",
                  body, flags=re.S)
    # images: a missing file becomes a visible box instead of a broken image
    def img(m):
        src = m.group(1)
        if (HERE / src).exists():
            return m.group(0)
        return f"<span class='missing'>[image not yet added: {src.replace('../', '')}]</span>"
    body = re.sub(r'<img alt="[^"]*" src="([^"]+)" ?/?>', img, body)
    # keep a figure and its caption together
    body = re.sub(r"(<p>(?:<img[^>]*>|<span class='missing'>[^<]*</span>)</p>\s*<p><em>Fig\.[^<]*</em></p>)",
                  lambda m: f"<div class='fig{' col' if 'kaggle_best_private' in m.group(1) else ''}'>{m.group(1)}</div>", body)
    head, sep, appendix = body.partition("<h2>Appendix</h2>")
    lead, _, rest = head.partition("<h2>Abstract</h2>")
    body = (f"<div class='lead'>{lead}</div><div class='cols' lang='en'><h2>Abstract</h2>{rest}</div>"
            f"<div class='appendix'>{sep}{appendix}</div>")
    html = (f"<!doctype html><html><head><meta charset='utf-8'><title>{meta['title']}</title><style>{CSS}</style>"
            f"</head><body><h1 class='title'>{meta['title']}</h1><p class='byline'>{meta['author']} — {meta['date']}</p>"
            f"{body}</body></html>")
    out_html = HERE / "report.html"
    out_html.write_text(html)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={HERE / 'report.pdf'}", out_html.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"wrote {HERE / 'report.pdf'} ({(HERE / 'report.pdf').stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
