"""Measure a model at the exact conditions of its data sheet's rows, and say whether it is inside the limits.

    python3 /sim/bench/spec.py JOB.json OUT.json          (inside a simulator image; SIM_ENGINE decides)

JOB: {"kind": "bjt"|"jfet", "polarity": "npn"|"pnp"|"n"|"p", "card": ".model ... text", "model": "NAME",
      "rows": [{"id", "sym", "cond": {NAME: SI value, ...}, "min", "typ", "max"} ...]}   (magnitudes, SI)
Symbols understood — bipolar: hFE, hfe, vbe, vcesat, vbesat, ft, cob, cib, nf; JFET: idss, vgsoff, vgs,
gfs, igss, ciss, crss, en, nf. Anything else is returned as "not modelled" (breakdown voltages, leakage,
switching times: a plain SPICE card either does not model them or needs a fixture of its own).

Each row is simulated at its own conditions: the DC sweeps are generated per distinct VCE (or VDS), the
saturation sweeps per IC/IB ratio, AC and noise runs per bias point. A row with a min/max is "inside",
"below" or "above"; a row with only a typical value gets the ratio model/typical.
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import engines, raw  # noqa: E402

ENGINE = engines.engine_name()
K_B = 1.380649e-23
T_K = 298.15
LN10 = 2.302585092994046


def _n(x):
    return f"{x:.9g}"


class Runner:
    def __init__(self, workdir, card):
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "model.lib").write_text(card + "\n")
        self.k = 0

    def run(self, body):
        self.k += 1
        net = self.dir / f"r{self.k}.cir"
        head = engines.header(ENGINE)
        net.write_text(f"* spec {self.k}\n.include \"model.lib\"\n{head}\n.options reltol=1e-4\n.temp 25\n{body}\n.end\n")
        cost = engines.run(net, ENGINE, timeout=120)
        if not cost["raw"]:
            raise RuntimeError("no waveform: " + (net.with_suffix('.out').read_text(errors='replace')[-300:]))
        plots = raw.read(cost["raw"])
        return plots

    @staticmethod
    def data(plots, *keys):
        for p in plots:
            if any(k in p["name"].lower() for k in keys):
                return p["data"], p["name"]
        return plots[0]["data"], plots[0]["name"]


def v(d, *names):
    for n in names:
        if n in d:
            return list(d[n])
    raise KeyError(f"{names} not in {sorted(d)[:12]}")


def log_interp(xs, ys, x):
    """ys at x, xs increasing and positive; interpolation in log x."""
    for a in range(len(xs) - 1):
        x0, x1 = xs[a], xs[a + 1]
        if x0 > 0 and x1 > 0 and x0 <= x <= x1:
            w = (math.log(x) - math.log(x0)) / (math.log(x1) - math.log(x0)) if x1 != x0 else 0
            return ys[a] + w * (ys[a + 1] - ys[a])
    return None


def noise_in(plots):
    d, name = Runner.data(plots, "spectral", "noise")
    f = [abs(x) for x in v(d, "frequency")]
    on = [abs(x) for x in v(d, "v(onoise_spectrum)", "v(onoise)")]
    if "v(inoise_spectrum)" in d or "v(inoise)" in d:
        inn = [abs(x) for x in v(d, "v(inoise_spectrum)", "v(inoise)")]
    else:
        g = [abs(x) for x in v(d, "v(gain)", "gain")]
        inn = [o / gg for o, gg in zip(on, g)]
    if "^2" in name:
        inn = [math.sqrt(x) for x in inn]
    return f, inn


def at_f(f, ys, target):
    k = min(range(len(f)), key=lambda j: abs(math.log10(f[j] / target)))
    return ys[k]


# ---------------------------------------------------------------- bipolar
def bjt(job, r):
    s = 1 if job["polarity"] == "npn" else -1
    m = job["model"]
    rows = job["rows"]
    out = {}
    vces = sorted({row["cond"].get("VCE") for row in rows if row["sym"] in ("hFE", "vbe", "ft", "hfe", "nf")
                   and row["cond"].get("VCE")})
    ratios = sorted({round(row["cond"]["IC"] / row["cond"]["IB"], 6) for row in rows
                     if row["sym"] in ("vcesat", "vbesat") and row["cond"].get("IC") and row["cond"].get("IB")})
    body = []
    for i, vce in enumerate(vces):
        body += [f"VC{i} c{i} 0 {_n(s * vce)}", f"BB{i} 0 b{i} I={'-' if s < 0 else ''}exp({LN10}*V(x))",
                 f"Q{i} c{i} b{i} 0 {m}"]
    for j, ratio in enumerate(ratios):
        body += [f"BSB{j} 0 bs{j} I={'-' if s < 0 else ''}exp({LN10}*V(x))",
                 f"BSC{j} 0 cs{j} I={'-' if s < 0 else ''}{_n(ratio)}*exp({LN10}*V(x))",
                 (f"DCL{j} cs{j} cl{j} DCLMP" if s > 0 else f"DCL{j} cl{j} cs{j} DCLMP"),
                 f"VCL{j} cl{j} 0 {_n(s * 30)}", f"QS{j} cs{j} bs{j} 0 {m}"]
    curves, sat = {}, {}
    if vces or ratios:
        body += ["VX x 0 0", "RX x 0 1", ".model DCLMP D(Is=1e-14)", ".dc VX -9 -0.5 0.02"]
        d, _ = r.data(r.run("\n".join(body)), "dc")
        x = v(d, "v(x)")
        ib = [10 ** xx for xx in x]
        for i, vce in enumerate(vces):
            ic = [-c * s for c in v(d, f"i(vc{i})")]
            vb = [b * s for b in v(d, f"v(b{i})")]
            curves[vce] = (ib, ic, vb)
        for j, ratio in enumerate(ratios):
            sat[ratio] = ([ratio * b for b in ib], [c * s for c in v(d, f"v(cs{j})")],
                          [b * s for b in v(d, f"v(bs{j})")])

    def ib_at(vce, ic_t):
        ib, ic, vb = curves[vce]
        pts = [(c, b, vv) for c, b, vv in zip(ic, ib, vb) if c > 0]
        pts.sort()
        xs = [p[0] for p in pts]
        lib = log_interp(xs, [math.log(p[1]) for p in pts], ic_t)
        vbe = log_interp(xs, [p[2] for p in pts], ic_t)
        return (math.exp(lib) if lib is not None else None), vbe

    for row in rows:
        c, sym = row["cond"], row["sym"]
        try:
            if sym in ("hFE", "vbe") and c.get("IC") and c.get("VCE"):
                ibx, vbe = ib_at(c["VCE"], c["IC"])
                val = (c["IC"] / ibx if ibx else None) if sym == "hFE" else vbe
                # The sweep drives the base from a behavioural source. QSPICE, with a card whose RB is ~0
                # (1 uOhm), settles on a wrong solution there (hFE ~1e6) though a plain current source is
                # right: a value no transistor has is reported as suspect, not as a measurement.
                if val is not None and ((sym == "hFE" and val > 1e4) or (vbe is not None and not 0.2 < vbe < 1.6)):
                    val = {"error": f"suspect: hFE={c['IC'] / ibx if ibx else None}, VBE={vbe}"}
                out[row["id"]] = val
            elif sym in ("vcesat", "vbesat") and c.get("IC") and c.get("IB"):
                ics, vcs, vbs = sat[round(c["IC"] / c["IB"], 6)]
                val = log_interp(ics, vcs if sym == "vcesat" else vbs, c["IC"])
                out[row["id"]] = val if (val is not None and log_interp(ics, vcs, c["IC"]) < 29) else None
            elif sym in ("ft", "hfe") and c.get("IC") and c.get("VCE"):
                ibx, _ = ib_at(c["VCE"], c["IC"])
                if not ibx:
                    out[row["id"]] = None
                    continue
                f = c.get("F") or (None if sym == "ft" else 1e3)
                d, _ = r.data(r.run(f"VCT ct 0 {_n(s * c['VCE'])}\nIBT 0 bt DC {_n(s * ibx)} AC 1\nQT ct bt 0 {m}\n"
                                    f".save I(VCT)\n.ac dec 40 100 1e10"), "ac")
                fr = [abs(z) for z in v(d, "frequency")]
                h = [abs(z) for z in v(d, "i(vct)")]
                if sym == "hfe":
                    out[row["id"]] = at_f(fr, h, f)
                elif f:
                    out[row["id"]] = at_f(fr, h, f) * f
                else:
                    out[row["id"]] = next((fr[k] for k in range(len(h)) if h[k] < 1), None)
            elif sym in ("cob", "cib"):
                vv = c.get("VCB") if sym == "cob" else c.get("VEB")
                f = c.get("F") or 1e6
                if sym == "cob":
                    body = f"V1 a 0 DC {_n(s * vv)} AC 1\nVB b 0 0\nRE e 0 1e12\nQ1 a b e {m}"
                else:
                    body = f"V1 a 0 DC {_n(s * vv)} AC 1\nVB b 0 0\nRC cc 0 1e12\nQ1 cc b a {m}"
                d, _ = r.data(r.run(body + "\n.save I(V1)\n.ac dec 20 1e3 1e8"), "ac")
                fr = [abs(z) for z in v(d, "frequency")]
                out[row["id"]] = abs(at_f(fr, [z.imag for z in v(d, "i(v1)")], f)) / (2 * math.pi * f)
            elif sym == "nf" and c.get("IC") and c.get("VCE") and (c.get("RG")):
                f = c.get("F")
                if not f:
                    out[row["id"]] = None
                    continue
                ibx, vbe = ib_at(c["VCE"], c["IC"])
                if not ibx or vbe is None:
                    out[row["id"]] = None
                    continue
                rg = c["RG"]
                body = (f"VSENSE c cc 0\nVC cc 0 {_n(s * c['VCE'])}\nIB 0 b DC {_n(s * ibx)}\n"
                        f"VIN in 0 DC {_n(s * vbe)} AC 1\nRG in b {_n(rg)}\nQ1 c b 0 {m}\n"
                        f"H1 out 0 VSENSE 1000\nRLOAD out 0 1meg\n.noise V(out) VIN dec 20 1 1e6")
                fr, inn = noise_in(r.run(body))
                out[row["id"]] = 10 * math.log10(at_f(fr, inn, f) ** 2 / (4 * K_B * T_K * rg))
        except Exception as exc:  # noqa: BLE001
            out[row["id"]] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


# ---------------------------------------------------------------- JFET
def jfet(job, r):
    s = 1 if job["polarity"] in ("n", "njf") else -1
    m = job["model"]
    rows = job["rows"]
    out = {}
    vdss = sorted({row["cond"].get("VDS") for row in rows
                   if row["sym"] in ("idss", "vgsoff", "vgs", "gfs", "en", "nf") and row["cond"].get("VDS")})
    curves = {}
    if vdss:
        body = []
        for i, vds in enumerate(vdss):
            body += [f"VD{i} d{i} 0 {_n(s * vds)}", f"J{i} d{i} g 0 {m}"]
        body += ["VG g 0 0", ".dc VG 0 " + _n(-s * 10) + " " + _n(-s * 0.002)]
        d, _ = r.data(r.run("\n".join(body)), "dc")
        n = len(v(d, "i(vd0)"))
        vg = [0.002 * k for k in range(n)]  # |VGS|
        for i, vds in enumerate(vdss):
            curves[vds] = (vg, [-x * s for x in v(d, f"i(vd{i})")])

    def vg_at(vds, idt):
        vg, ids = curves[vds]
        for k in range(len(ids) - 1):
            a, b = ids[k], ids[k + 1]
            if a >= idt > b and a > 0 and b > 0:
                w = (math.log(idt) - math.log(a)) / (math.log(b) - math.log(a))
                return vg[k] + w * (vg[k + 1] - vg[k])
            if a >= idt > b:
                return vg[k] + (a - idt) / (a - b) * (vg[k + 1] - vg[k])
        return None

    for row in rows:
        c, sym = row["cond"], row["sym"]
        try:
            if sym == "idss" and c.get("VDS"):
                out[row["id"]] = curves[c["VDS"]][1][0]
            elif sym in ("vgsoff", "vgs") and c.get("VDS") and c.get("ID"):
                out[row["id"]] = vg_at(c["VDS"], c["ID"])
            elif sym == "gfs" and c.get("VDS"):
                vg, ids = curves[c["VDS"]]
                k = 0 if not c.get("ID") else min(range(len(ids)), key=lambda j: abs(ids[j] - c["ID"]))
                k = min(k, len(ids) - 2)
                out[row["id"]] = abs(ids[k] - ids[k + 1]) / (vg[k + 1] - vg[k])
            elif sym == "igss" and c.get("VGS"):
                d, _ = r.data(r.run(f"VG g 0 {_n(-s * c['VGS'])}\nVD d 0 0\nJ1 d g 0 {m}\nVX x 0 0\nRX x 0 1\n"
                                    ".dc VX 0 1 1"), "dc")
                out[row["id"]] = abs(v(d, "i(vg)")[0])
            elif sym in ("ciss", "crss"):
                f = c.get("F") or 1e6
                if c.get("VDG") and "ID" not in c:  # "VDG = 10 V, ID = 0": pinched off, gate at -VDG
                    vd, vgb = 0.0, c["VDG"]
                else:
                    vd, vgb = c.get("VDS") or c.get("VDG") or 10.0, 0.0
                body = (f"VD d 0 DC {_n(s * vd)}\nVG g 0 DC {_n(-s * vgb)} AC 1\nJ1 d g 0 {m}\n"
                        ".save I(VG) I(VD)\n.ac dec 20 1e3 1e8")
                d, _ = r.data(r.run(body), "ac")
                fr = [abs(z) for z in v(d, "frequency")]
                cur = v(d, "i(vg)" if sym == "ciss" else "i(vd)")
                out[row["id"]] = abs(at_f(fr, [z.imag for z in cur], f)) / (2 * math.pi * f)
            elif sym in ("en", "nf") and c.get("VDS") and c.get("F"):
                vgb = vg_at(c["VDS"], c["ID"]) if c.get("ID") else 0.0
                rg = c.get("RG") if sym == "nf" else None
                gate = f"VIN in 0 DC {_n(-s * vgb)} AC 1\n" + (f"RG in g {_n(rg)}\n" if rg else "RG0 in g 0.001\n")
                body = (gate + f"VSENSE dd d 0\nVD dd 0 {_n(s * c['VDS'])}\nJ1 d g 0 {m}\n"
                        f"H1 out 0 VSENSE 1000\nRLOAD out 0 1meg\n.noise V(out) VIN dec 20 1 1e6")
                fr, inn = noise_in(r.run(body))
                val = at_f(fr, inn, c["F"])
                out[row["id"]] = 10 * math.log10(val ** 2 / (4 * K_B * T_K * rg)) if rg else val
        except Exception as exc:  # noqa: BLE001
            out[row["id"]] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


def verdict(row, val):
    if val is None or isinstance(val, dict):
        return "not measured" if val is None else ("suspect" if "suspect" in str(val) else "error")
    lo, hi, typ = row.get("min"), row.get("max"), row.get("typ")
    if lo is None and hi is None:
        return f"x{val / typ:.2f} of typ" if typ else "—"
    if lo is not None and val < lo * (1 - 1e-3):
        return "below"
    if hi is not None and val > hi * (1 + 1e-3):
        return "above"
    return "inside"


def main():
    jobs = json.loads(Path(sys.argv[1]).read_text())
    results = []
    for n, job in enumerate(jobs):
        r = Runner(Path("/tmp/spec") / f"j{n}", job["card"])
        try:
            vals = (bjt if job["kind"] == "bjt" else jfet)(job, r)
        except Exception as exc:  # noqa: BLE001
            vals = {row["id"]: {"error": f"{type(exc).__name__}: {exc}"[:200]} for row in job["rows"]}
        rows = []
        for row in job["rows"]:
            val = vals.get(row["id"])
            rows.append({"id": row["id"], "sym": row["sym"], "value": val, "verdict": verdict(row, val)})
        results.append({"part": job["part"], "model_id": job["model_id"], "engine": ENGINE, "rows": rows})
    Path(sys.argv[2]).write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
