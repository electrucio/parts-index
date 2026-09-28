"""Ask a vision-language model for the rows of a data sheet's characteristics tables, as JSON.

    uv run python docker/datasheets/extract.py --method image --server http://127.0.0.1:8090 \\
        --golden docker/datasheets/golden.yaml --pdfs private_material/datasheets/vendor \\
        --out private_material/datasheet_lab/runs/<name>

Three ways of showing it a page, one prompt:
  text        the page's own text layer (PyMuPDF), plus any table PyMuPDF's find_tables() rebuilds from
              the drawing, as Markdown — a text model reading what the PDF already knows
  image       the page rendered at 150 dpi — what a scan would give
  image+text  both, so the model can use the picture for the structure and the text for the digits

The model is told to copy numbers exactly; evaluate.py then checks every number it returns against the
page's text layer, because the data sheet is the source and the model only arranges it. One JSON file
per page: the rows, the raw answer, and what the call cost (tokens, seconds).
"""

import argparse
import base64
import json
import re
import time
import urllib.request
from pathlib import Path

import pymupdf
import yaml

SYSTEM = (
    "You transcribe electronic-component data sheets into JSON. You copy; you never compute, convert, "
    "round, or fill in. Every number you output must appear, character for character, on the page."
)

PROMPT = """This is page {page} of a data sheet{maker}. The part of interest is {part}{also}.

Extract every row of the electrical-characteristics tables on this page (static, dynamic, small-signal,
switching, noise: every measured characteristic; not the absolute-maximum ratings or thermal data) that
applies to {part}. When one row gives values for several parts or grades, keep only {part}'s values;
if the sheet lists grades or classes of {part} itself (e.g. {part}A, {part}B, or GR/BL), give one row per
grade and put the grade in "variant". Skip rows that apply only to other parts.

For each row:
  "symbol":     the symbol as printed (e.g. "hFE", "VCE(sat)", "IDSS", "Ciss")
  "parameter":  the parameter name as printed
  "conditions": the test conditions as printed, one string; include conditions stated once for the whole
                table or group (e.g. in its heading) if they apply to the row
  "min", "typ", "max": the values exactly as printed, as strings; null where the sheet has a dash or blank
  "unit":       the unit as printed ("" if none)
  "variant":    the grade/class this row is for, or null

Answer with JSON only: {{"rows": [ ... ]}}"""

SECOND_LOOK = """Look at the page again, table by table and row by row. Which rows of the electrical-characteristics
tables that apply to {part} are missing from your answer? Give only those, in the same form, or an empty
list if none is missing: {{"rows": [ ... ]}}"""


def page_text(doc, pno):
    page = doc[pno - 1]
    text = page.get_text(sort=True)
    tables = []
    try:
        for t in page.find_tables().tables:
            tables.append(t.to_markdown())
    except Exception:  # noqa: BLE001 — a page find_tables cannot read is still a page of text
        pass
    return text, tables


def ask(server, messages, max_tokens=6000):
    body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"{server}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())
    return resp, time.perf_counter() - t0


def parse_rows(content):
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return None
    try:
        return json.loads(m[0]).get("rows")
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["text", "image", "image+text"], required=True)
    ap.add_argument("--server", default="http://127.0.0.1:8090")
    ap.add_argument("--golden", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--pages", required=True, help="folder of rendered pages <doc>_p<n>.png")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None, help="substring of doc names to run")
    ap.add_argument("--second-look", action="store_true",
                    help="after the answer, ask for the rows it left out (a fight against silent omissions)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    golden = yaml.safe_load(open(a.golden))
    for d in golden["docs"]:
        if a.only and a.only not in d["doc"]:
            continue
        doc = pymupdf.open(Path(a.pdfs) / d["pdf"])
        also = f" (the same sheet also covers {', '.join(d['also_in_doc'])})" if d.get("also_in_doc") else ""
        for pno in d["pages"]:
            dest = out / f"{d['doc']}_p{pno}.json"
            if dest.exists():
                continue
            prompt = PROMPT.format(page=pno, maker="", part=d["part"], also=also)
            content = []
            if a.method in ("image", "image+text"):
                png = Path(a.pages) / f"{d['doc']}_p{pno}.png"
                b64 = base64.b64encode(png.read_bytes()).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            if a.method in ("text", "image+text"):
                text, tables = page_text(doc, pno)
                prompt += "\n\nThe page's text layer:\n```\n" + text + "\n```"
                for i, t in enumerate(tables):
                    prompt += f"\n\nTable {i + 1} as rebuilt from the PDF's drawing:\n" + t
            content.append({"type": "text", "text": prompt})
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
            try:
                resp, secs = ask(a.server, messages)
                answer = resp["choices"][0]["message"]["content"]
                rows = parse_rows(answer)
                usage = dict(resp.get("usage") or {})
                added = None
                if a.second_look and rows is not None:
                    messages += [{"role": "assistant", "content": answer},
                                 {"role": "user", "content": SECOND_LOOK.format(part=d["part"])}]
                    resp2, secs2 = ask(a.server, messages)
                    added = parse_rows(resp2["choices"][0]["message"]["content"]) or []
                    rows = rows + added
                    secs += secs2
                    for k, val in (resp2.get("usage") or {}).items():
                        if isinstance(val, int):
                            usage[k] = usage.get(k, 0) + val
                rec = {"doc": d["doc"], "page": pno, "method": a.method + ("+second-look" if a.second_look else ""),
                       "seconds": round(secs, 1), "usage": usage, "timings": resp.get("timings"), "rows": rows,
                       "rows_added_on_second_look": None if added is None else len(added),
                       "parse_error": rows is None, "answer": answer}
            except Exception as exc:  # noqa: BLE001
                rec = {"doc": d["doc"], "page": pno, "method": a.method, "error": str(exc)}
            dest.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
            print(json.dumps({k: rec.get(k) for k in ("doc", "page", "seconds", "parse_error", "error")},
                             ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
