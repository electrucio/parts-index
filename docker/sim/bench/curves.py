"""The graphs a data sheet draws, drawn again for a model.

Called by spec.py for a job that carries `figures`: each has a bench id, its axis range and its series, in
SI units (the job builder converts them from the figure's units, and the publisher converts back). Each
bench returns, per series, the points [x, y] of the curve, in SI:

    bjt-hfe            DC current gain against IC at VCE, one curve per temperature
    bjt-on-voltages    VBE(sat) and VCE(sat) at a forced IC/IB, and VBE at a VCE, against IC
    bjt-tempco         the temperature coefficients of VCE(sat) and VBE(sat) between two temperatures
    bjt-saturation     VCE against IB, one curve per collector current fed to the collector
    bjt-capacitance    Cibo and Cobo against the reverse voltage across their junction, at f
    bjt-hparams        hfe, hie, hre, hoe against IC at VCE and f
    bjt-nf-frequency   spot noise figure against frequency, one curve per (RS, IC)
    bjt-nf-source      spot noise figure against source resistance at f, one curve per IC

The circuits are those of spec.py's rows, swept: a base driven by a behavioural current source whose
value is 10^V(x), so a DC sweep of V(x) walks the base current in equal steps per decade and each point
starts from the last.
"""
import math

from bench.spec import K_B, LN10, T_K, _n, at_f, h_parameters, log_interp, noise_in, v

POINTS = 24


def grid(lo, hi, scale, n=POINTS):
    if scale == "log":
        return [lo * (hi / lo) ** (k / (n - 1)) for k in range(n)]
    return [lo + (hi - lo) * k / (n - 1) for k in range(n)]


def sweep(r, m, s, vces=(), ratios=(), temp=25, lo=-9.0, hi=-0.5):
    """The DC sweep of spec.py's bipolar bench: base current 10^V(x) A; one transistor per VCE (collector
    held) and one per forced ratio IC/IB (collector fed ratio × IB, a diode to 30 V catching a transistor
    too weak to take it). Returns {vce: (ib, ic, vbe)}, {ratio: (ic, vce, vbe)}."""
    body = []
    for i, vce in enumerate(vces):
        body += [f"VC{i} c{i} 0 {_n(s * vce)}", f"BB{i} 0 b{i} I={'-' if s < 0 else ''}exp({LN10}*V(x))",
                 f"Q{i} c{i} b{i} 0 {m}"]
    for j, ratio in enumerate(ratios):
        body += [f"BSB{j} 0 bs{j} I={'-' if s < 0 else ''}exp({LN10}*V(x))",
                 f"BSC{j} 0 cs{j} I={'-' if s < 0 else ''}{_n(ratio)}*exp({LN10}*V(x))",
                 (f"DCL{j} cs{j} cl{j} DCLMP" if s > 0 else f"DCL{j} cl{j} cs{j} DCLMP"),
                 f"VCL{j} cl{j} 0 {_n(s * 30)}", f"QS{j} cs{j} bs{j} 0 {m}"]
    body += ["VX x 0 0", "RX x 0 1", ".model DCLMP D(Is=1e-14)", f".dc VX {_n(lo)} {_n(hi)} 0.02"]
    d, _ = r.data(r.run("\n".join(body), temp=temp), "dc")
    ib = [10 ** xx for xx in v(d, "v(x)")]
    curves = {vce: (ib, [-c * s for c in v(d, f"i(vc{i})")], [b * s for b in v(d, f"v(b{i})")])
              for i, vce in enumerate(vces)}
    sat = {ratio: ([ratio * b for b in ib], [c * s for c in v(d, f"v(cs{j})")], [b * s for b in v(d, f"v(bs{j})")])
           for j, ratio in enumerate(ratios)}
    return curves, sat


def along_ic(ic, ys, targets):
    """ys at each target collector current, interpolated in log IC; points outside the sweep left out."""
    pts = sorted((c, y) for c, y in zip(ic, ys) if c > 0)
    xs = [p[0] for p in pts]
    out = []
    for t in targets:
        y = log_interp(xs, [p[1] for p in pts], t)
        if y is not None:
            out.append([t, y])
    return out


def ib_for(curve, ic_t):
    ib, ic, _ = curve
    pts = sorted((c, b) for c, b in zip(ic, ib) if c > 0)
    y = log_interp([p[0] for p in pts], [math.log(p[1]) for p in pts], ic_t)
    return math.exp(y) if y is not None else None


def hfe(r, m, s, fig):
    vce = fig["fixed"]["VCE"]
    out = {}
    for se in fig["series"]:
        curves, _ = sweep(r, m, s, vces=[vce], temp=se["cond"].get("TJ", 25))
        ib, ic, _ = curves[vce]
        out[se["label"]] = along_ic(ic, [c / b for c, b in zip(ic, ib)], grid(*fig["x"]))
    return out


def on_voltages(r, m, s, fig, temp=25):
    vces = sorted({se["cond"]["VCE"] for se in fig["series"] if se["cond"].get("VCE")})
    ratios = sorted({se["cond"]["ratio"] for se in fig["series"] if se["cond"].get("ratio")})
    curves, sat = sweep(r, m, s, vces=vces, ratios=ratios, temp=temp)
    out = {}
    for se in fig["series"]:
        q = se["cond"]["quantity"]
        if q == "vbe":
            ib, ic, vb = curves[se["cond"]["VCE"]]
            out[se["label"]] = along_ic(ic, vb, grid(*fig["x"]))
        else:
            ic, vc, vb = sat[se["cond"]["ratio"]]
            ok = [k for k in range(len(ic)) if vc[k] < 29]          # collector not caught by the 30 V diode
            out[se["label"]] = along_ic([ic[k] for k in ok], [(vc if q == "vcesat" else vb)[k] for k in ok],
                                        grid(*fig["x"]))
    return out


def tempco(r, m, s, fig):
    ratio = fig["fixed"]["ratio"]
    temps = sorted({t for se in fig["series"] for t in se["cond"]["T"]})
    lo, hi, scale = fig["x"]
    targets = grid(max(lo, hi / 100), hi, scale)
    at = {}
    for t in temps:
        _, sat = sweep(r, m, s, ratios=[ratio], temp=t)
        ic, vc, vb = sat[ratio]
        ok = [k for k in range(len(ic)) if vc[k] < 29]
        at[t] = {"vcesat": dict(along_ic([ic[k] for k in ok], [vc[k] for k in ok], targets)),
                 "vbesat": dict(along_ic([ic[k] for k in ok], [vb[k] for k in ok], targets))}
    out = {}
    for se in fig["series"]:
        q, (t1, t2) = se["cond"]["quantity"], se["cond"]["T"]
        a, b = at[t1][q], at[t2][q]
        out[se["label"]] = [[x, (b[x] - a[x]) / (t2 - t1)] for x in targets if x in a and x in b]
    return out


def saturation(r, m, s, fig):
    lo, hi, _ = fig["x"]
    body = []
    series = fig["series"]
    for k, se in enumerate(series):
        body += [f"ICS{k} 0 c{k} DC {_n(s * se['cond']['IC'])}",
                 (f"DCL{k} c{k} cl{k} DCLMP" if s > 0 else f"DCL{k} cl{k} c{k} DCLMP"), f"VCL{k} cl{k} 0 {_n(s * 10)}",
                 f"BB{k} 0 b{k} I={'-' if s < 0 else ''}exp({LN10}*V(x))", f"Q{k} c{k} b{k} 0 {m}"]
    body += ["VX x 0 0", "RX x 0 1", ".model DCLMP D(Is=1e-14)",
             f".dc VX {_n(math.log10(lo))} {_n(math.log10(hi))} 0.02"]
    d, _ = r.data(r.run("\n".join(body), temp=fig["fixed"].get("TJ", 25)), "dc")
    ib = [10 ** xx for xx in v(d, "v(x)")]
    return {se["label"]: [[b, s * c] for b, c in zip(ib, v(d, f"v(c{k})"))] for k, se in enumerate(series)}


def capacitance(r, m, s, fig):
    f = fig["fixed"].get("f", 1e6)
    body, where = [], {}
    k = 0
    for se in fig["series"]:
        lo, hi = se["cond"]["VR"]
        for vr in grid(lo, hi, "log", 14):
            if se["cond"]["junction"] == "CB":        # Cobo: collector reverse-biased from the base, emitter open
                body += [f"V1{k} a{k} 0 DC {_n(s * vr)} AC 1", f"VB{k} b{k} 0 0", f"RE{k} e{k} 0 1e12",
                         f"Q{k} a{k} b{k} e{k} {m}"]
            else:                                      # Cibo: emitter reverse-biased from the base, collector open
                body += [f"V1{k} a{k} 0 DC {_n(s * vr)} AC 1", f"VB{k} b{k} 0 0", f"RC{k} cc{k} 0 1e12",
                         f"Q{k} cc{k} b{k} a{k} {m}"]
            where[k] = (se["label"], vr)
            k += 1
    body += [".save " + " ".join(f"I(V1{j})" for j in where), f".ac dec 10 {_n(f / 10)} {_n(f * 10)}"]
    d, _ = r.data(r.run("\n".join(body)), "ac")
    fr = [abs(z) for z in v(d, "frequency")]
    out = {}
    for j, (label, vr) in where.items():
        c = abs(at_f(fr, [z.imag for z in v(d, f"i(v1{j})")], f)) / (2 * math.pi * f)
        out.setdefault(label, []).append([vr, c])
    return out


def hparams(r, m, s, fig, memo):
    vce, f = fig["fixed"]["VCE"], fig["fixed"].get("f", 1e3)
    key = ("h", vce, f, tuple(fig["x"]))
    if key not in memo:
        curves, _ = sweep(r, m, s, vces=[vce])
        pts = {}
        for ic in grid(*fig["x"], 13):
            ib = ib_for(curves[vce], ic)
            if ib:
                pts[ic] = h_parameters(r, m, s, vce, ib, f)
        memo[key] = pts
    q = fig["quantity"]
    return {fig["series"][0]["label"]: [[ic, h[q]] for ic, h in memo[key].items()]}


def nf_run(r, m, s, vce, ib, vbe, rs, fmin, fmax, per_dec=20):
    body = (f"VSENSE c cc 0\nVC cc 0 {_n(s * vce)}\nIB 0 b DC {_n(s * ib)}\n"
            f"VIN in 0 DC {_n(s * vbe)} AC 1\nRG in b {_n(rs)}\nQ1 c b 0 {m}\n"
            f"H1 out 0 VSENSE 1000\nRLOAD out 0 1meg\n.noise V(out) VIN dec {per_dec} {_n(fmin)} {_n(fmax)}")
    fr, inn = noise_in(r.run(body))
    return fr, [10 * math.log10(x ** 2 / (4 * K_B * T_K * rs)) for x in inn]


def bias(r, m, s, vce, ic, memo):
    if ("sweep", vce) not in memo:
        memo[("sweep", vce)] = sweep(r, m, s, vces=[vce])[0][vce]
    curve = memo[("sweep", vce)]
    ib = ib_for(curve, ic)
    ibs, ics, vbs = curve
    pts = sorted((c, vb) for c, vb in zip(ics, vbs) if c > 0)
    vbe = log_interp([p[0] for p in pts], [p[1] for p in pts], ic)
    return ib, vbe


def nf_frequency(r, m, s, fig, memo):
    vce = fig["fixed"]["VCE"]
    lo, hi, _ = fig["x"]
    out = {}
    for se in fig["series"]:
        ib, vbe = bias(r, m, s, vce, se["cond"]["IC"], memo)
        if ib and vbe is not None:
            fr, nf = nf_run(r, m, s, vce, ib, vbe, se["cond"]["RS"], lo, hi, 10)
            out[se["label"]] = [[f, y] for f, y in zip(fr, nf) if lo * 0.99 <= f <= hi * 1.01]
    return out


def nf_source(r, m, s, fig, memo):
    vce, f = fig["fixed"]["VCE"], fig["fixed"]["f"]
    out = {}
    for se in fig["series"]:
        ib, vbe = bias(r, m, s, vce, se["cond"]["IC"], memo)
        if not ib or vbe is None:
            continue
        pts = []
        for rs in grid(*fig["x"], 10):
            fr, nf = nf_run(r, m, s, vce, ib, vbe, rs, f / 1.2, f * 1.2, 5)
            pts.append([rs, at_f(fr, nf, f)])
        out[se["label"]] = pts
    return out


BENCHES = {"bjt-hfe": hfe, "bjt-on-voltages": on_voltages, "bjt-tempco": tempco, "bjt-saturation": saturation,
           "bjt-capacitance": capacitance, "bjt-hparams": hparams, "bjt-nf-frequency": nf_frequency,
           "bjt-nf-source": nf_source}
WITH_MEMO = {"bjt-hparams", "bjt-nf-frequency", "bjt-nf-source"}


def run_figures(job, r):
    """{figure n: {series label: [[x, y], ...]}} or {figure n: {"error": …}}, SI units."""
    s = 1 if job["polarity"] in ("npn", "n") else -1
    m = job["model"]
    memo = {}
    out = {}
    for fig in job.get("figures") or []:
        fn = BENCHES.get(fig["bench"])
        if fn is None:
            continue
        try:
            out[str(fig["n"])] = fn(r, m, s, fig, memo) if fig["bench"] in WITH_MEMO else fn(r, m, s, fig)
        except Exception as exc:  # noqa: BLE001
            out[str(fig["n"])] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return out
