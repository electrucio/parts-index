"""Is this magazine page an advert / price list, or an article?

Two kinds of signal: the text of the page (prices, postage and address words against figure and circuit words) and the
part hits of the page: priced rows (a part and a price in the same block or on the same line) and catalogue runs
(BC107, BC108, BC109 ...). Measured on 128 hand-labelled pages: 88-91 % of the advert pages caught, 3-8 % of good pages
lost, no circuit page lost. Change a weight only together with a re-run of that measurement (schematics/qa).

The magazines are full of mail-order component adverts: pages that name dozens of parts and are useless as a link.
`score(page)` returns (points, fired) from features computed on one page's OCR blocks; `is_ad(page)` applies the
threshold.

A page is {"w":, "h":, "blocks": [{"box":[x0,y0,x1,y1], "text":, "conf":}, ...], "n_parts": distinct known parts}.
"""
import re

# --- prices and money ------------------------------------------------------------------------------------------
# OCR damage: the pound sign comes out as L, f, E or nothing; cents as c or C; decimal point as , or .
PRICE = re.compile(r"(?:[£$LEf€]\s?\d{1,4}[.,]\d{2}\b)"          # $1.25  L2,50  f0.85
                   r"|(?:\b\d{1,4}[.,]\d{2}\s*(?:ea\b|each\b|p\.?p\.?\b|\+\s*vat\b|inc\b))"   # 1.25 ea
                   r"|(?:\b\d{1,3}\s?¢)", re.I)                          # 89¢
WEAK_PRICE = re.compile(r"(?:\b\d{1,2}/(?:-|\d{1,2})d?\b)|(?:\b\d{1,3}p\b(?![a-z]))|(?:\b\d{1,3}c\b(?!\w))", re.I)   # 4/6  7/-  35p  89c — also 1/2 IC1 and 100p (100 pF)
PROSE = re.compile(r"^[A-Za-z(\"'][A-Za-z ,;:'\"()\-]{14,}[a-z.,;:)]$")             # a line of running text, whatever its length
MONEY_WORDS = re.compile(r"\bp\s?&\s?p\b|\bpost(?:age|\s+free|\s+paid)\b|\bs\.?a\.?e\.?\b|\bc\.?w\.?o\.?\b"
                         r"|\bcash\s+with\s+order\b|\bv\.?a\.?t\.?\b|\bmail\s+order\b|\bcatalogu?e\b|\bprice\s+list\b"
                         r"|\bper\s+(?:100|10|doz|dozen|pair)\b|\bmin(?:imum)?\.?\s+order\b|\bdiscount\b|\bcallers?\s+welcome\b"
                         r"|\bmoney\s+back\b|\bsatisfaction\s+guaranteed\b|\bwhile\s+stocks?\s+last\b|\bex[\-\s]?stock\b"
                         r"|\bsend\s+(?:now|for|s\.?a\.?e)\b|\bbargain\b|\bsurplus\b|\bspecial\s+offer\b|\bclearance\b"
                         r"|\bcheque\b|\bpostal\s+order\b|\baccess\b/?\bbarclaycard\b|\bcredit\s+card\b|\border\s+form\b", re.I)
ADDRESS = re.compile(r"\btel(?:ephone)?[.:]\s*\d|\bphone\s*[:\(]?\s*\d|\bdept\.?\s*[A-Z]{1,3}\d|\bfax\b"
                     r"|\b[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}\b"                # UK postcode
                     r"|\b(?:street|road|avenue|lane|estate|works|house)\b,?\s+[A-Z]", re.I)
# a genuine article talks about circuits, not about buying
ARTICLE_WORDS = re.compile(r"\bfig(?:ure)?s?\.?\s*\d|\bcircuit\s+(?:diagram|of|is|shown|operation)\b|\bwaveform\b"
                           r"|\bthe\s+(?:circuit|output|input|signal|supply|amplifier|oscillator)\b|\bcomponents?\s+list\b"
                           r"|\bconstruction\b|\bp\.?c\.?b\.?\s+(?:layout|track|foil)\b|\bveroboard\b|\btable\s+\d"
                           r"|\bresistors?\s+(?:should|are|must|R\d)|\bcapacitors?\s+(?:should|are|must|C\d)"
                           r"|\bis\s+connected\b|\bin\s+series\s+with\b|\bin\s+parallel\s+with\b|\bfeedback\b"
                           r"|\bsee\s+fig\b|\bas\s+shown\b|\bnext\s+month\b|\bpart\s+\d+\b", re.I)
REF_DES = re.compile(r"\b(?:R|C|IC|TR|Q|D|VR|SW|L|T)\d{1,3}\b")            # R15, C3, IC2, TR1 — designators of a real circuit


def features(page):
    blocks = [b for b in (page.get("blocks") or []) if b.get("conf", 1) >= 0.8 and (b.get("text") or "").strip()]
    text = " | ".join(b["text"] for b in blocks)
    words = text.split()
    nw = max(len(words), 1)
    w = page.get("w") or 1
    money = len(MONEY_WORDS.findall(text))
    prices = len(PRICE.findall(text)) + (len(WEAK_PRICE.findall(text)) if money else 0)
    prose_words = sum(len(b["text"].split()) for b in blocks if len(b["text"].split()) >= 8 or (len(b["text"].split()) >= 4 and PROSE.match(b["text"].strip())))
    long_blocks = [b for b in blocks if len(b["text"].split()) >= 8]
    upper = [b for b in blocks if len(b["text"]) >= 6 and b["text"].upper() == b["text"] and any(c.isalpha() for c in b["text"])]
    f = {
        "n_blocks": len(blocks),
        "n_words": nw,
        "n_parts": page.get("n_parts", 0),
        "prices": prices,
        "bare_prices": sum(1 for b in blocks if re.fullmatch(r"[£$]?\d{1,3}[.,]\d{2}p?", b["text"].strip())),
        "price_density": prices / nw * 100,
        "money_words": len(MONEY_WORDS.findall(text)),
        "address": len(ADDRESS.findall(text)),
        "contacts": len(re.findall(r"(?i)\b(?:tel|fax|phone)\b|www\.|\.co\.uk|\.com\b", text)),
        "article_words": len(ARTICLE_WORDS.findall(text)),
        "ref_des": len(set(REF_DES.findall(text))),
        "long_blocks": len(long_blocks),
        "long_block_frac": len(long_blocks) / max(len(blocks), 1),
        "prose_frac": prose_words / nw,                       # text-layer PDFs and narrow columns give short line blocks: count words, not blocks
        "upper_frac": len(upper) / max(len(blocks), 1),
        "median_block_w": (sorted(b["box"][2] - b["box"][0] for b in blocks)[len(blocks) // 2] / w) if blocks else 0,
        "parts_per_100w": page.get("n_parts", 0) / nw * 100,
    }
    return f, text


def priced_rows(page, part_blocks):
    """Blocks that name a part and a price, or a part with a price block to its right on the same line."""
    blocks = [b for b in (page.get("blocks") or []) if (b.get("text") or "").strip()]
    w = page.get("w") or 1
    priced = [i for i, b in enumerate(blocks) if PRICE.search(b["text"])]
    n = 0
    for i in set(part_blocks):
        if i >= len(blocks):
            continue
        b = blocks[i]
        if PRICE.search(b["text"]):
            n += 1
            continue
        x1, yc, h = b["box"][2], (b["box"][1] + b["box"][3]) / 2, max(b["box"][3] - b["box"][1], 1)
        if any(abs((blocks[j]["box"][1] + blocks[j]["box"][3]) / 2 - yc) < 0.6 * h and 0 <= blocks[j]["box"][0] - x1 < 0.3 * w for j in priced):
            n += 1
    return n


def seq_run(parts):
    """Share of the distinct parts whose numeric neighbour (+-1..3, same prefix) is on the page too: a catalogue enumerates, a circuit does not."""
    by = {}
    for p in set(parts):
        m = re.fullmatch(r"(\D*\d?\D+)(\d{2,5})[A-Z]{0,3}", p)
        if m:
            by.setdefault(m.group(1), set()).add(int(m.group(2)))
    tot = sum(len(v) for v in by.values())
    run = sum(1 for v in by.values() for x in v if any(x + d in v for d in (-3, -2, -1, 1, 2, 3)))
    return run / tot if tot >= 6 else 0.0


def score(page):
    """-> (points, fired). Positive points mean advert. Tuned in eval_adfilter.py."""
    f, _ = features(page)
    fired = []
    def add(pts, why):
        fired.append((pts, why))
    # placeholder weights: replaced once the workflow's measured features land
    if f["prices"] >= 6:
        add(3, f"prices x{f['prices']}")
    elif f["prices"] >= 2:
        add(1, f"prices x{f['prices']}")
    if f["money_words"] >= 3:
        add(3, f"money words x{f['money_words']}")
    elif f["money_words"] >= 1:
        add(1, f"money words x{f['money_words']}")
    if f["address"]:
        add(1, "dealer address / phone")
    if f["prose_frac"] < 0.25 and f["n_blocks"] >= 25:
        add(2, f"little running text ({f['prose_frac']:.2f})")
    if f["article_words"] >= 4:
        add(-3, f"article words x{f['article_words']}")
    elif f["article_words"] >= 2:
        add(-1, f"article words x{f['article_words']}")
    if f["ref_des"] >= 5 and f["n_parts"] <= 40:                 # valve price lists are full of U25, R19, X66: they are type names there
        add(-3, f"designators x{f['ref_des']}")
    if page.get("priced_rows", 0) >= 5:
        add(3, f"priced part rows x{page['priced_rows']}")
    elif page.get("priced_rows", 0) >= 2:
        add(1, f"priced part rows x{page['priced_rows']}")
    if page.get("seq_run", 0) >= 0.4 and f["n_parts"] >= 15 and f["ref_des"] < 5:
        add(3, f"catalogue run {page['seq_run']:.2f} over {f['n_parts']} parts")
    if f["bare_prices"] >= 15 and f["n_parts"] >= 10:            # "2N3703 | 0.15 | ZTX300 | 0.14": price lists that print no currency sign
        add(4, f"bare prices x{f['bare_prices']} with {f['n_parts']} parts")
    if f["bare_prices"] >= 25 and f["ref_des"] < 5:              # a price column without currency signs (readers' services, classified ads)
        add(3, f"bare prices x{f['bare_prices']}, no circuit")
    if f["address"] >= 3 and f["contacts"] >= 4 and f["ref_des"] < 5:      # several dealers with phone numbers and web sites: a directory or a showcase
        add(2, f"contacts x{f['contacts']} with {f['address']} addresses")
    if f["n_parts"] > 40:
        add(3, f"{f['n_parts']} distinct parts on one page")
    if 12 <= f["n_parts"] <= 25 and f["ref_des"] < 3:            # data and comparison tables: a dozen type numbers and no circuit
        add(2, f"{f['n_parts']} parts, no designators")
    if f["n_parts"] > 25 and f["ref_des"] < 5:                  # a listing even without prices: equivalence tables (Elektor TUP/TUN), indexes, data pages
        add(3, f"{f['n_parts']} distinct parts, no circuit")
    return sum(p for p, _ in fired), fired


def is_ad(page, threshold=3):
    return score(page)[0] >= threshold
