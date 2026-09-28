"""Measure a bipolar transistor model the way its data sheet is measured, in whichever simulator this is.

Three netlists, one per analysis, because LTspice runs one analysis per netlist:

  dc    hFE at fixed (IC, VCE) — the collector current is forced exactly: a current source pulls IC out of
        the emitter and a current-controlled source pulls the base current out beside it — plus VCE(sat)
        and VBE(sat) with IC and IB forced by current sources.
  ac    fT from |h21| at 100 MHz (IC = 20 mA, VCE = 20 V), and the extrapolated unity-gain frequency;
        Cob (VCB = 10 V, emitter open) and Cib (VEB = 0.5 V, collector open) at 1 MHz.
  tran  switching times in a resistive-load switch, IC = 150 mA, IB1 = IB2 = 15 mA.

Every test circuit of one analysis sits in the same netlist, each with its own nodes, so they are
solved together but do not touch. Several models can be packed into one netlist the same way
(`fragments(..., k)`), which is how a large batch pays each simulator's start-up cost once.

The conditions are those of the 2N2222A data sheet (onsemi 2N2222A/D, "Electrical characteristics").
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import engines, raw  # noqa: E402

HFE_POINTS = [(1e-4, 10), (1e-3, 10), (1e-2, 10), (0.15, 10), (0.5, 10), (0.15, 1)]  # (IC A, VCE V)
SAT_POINTS = [(0.15, 0.015), (0.5, 0.05)]  # (IC A, IB A) — read off the sweep, where IC = 10 IB throughout
SAT_CLAMP = 30.0  # V: where a transistor too weak to sink 10 IB has its collector caught by a diode
# hFE is read off a sweep of the base current, 10 points per decade from 10 nA to 100 mA, made by a
# behavioural source IB = 10^V(x) while the sweep walks V(x): a current into a junction converges in every
# simulator where forcing the collector current does not, and a DC sweep starts each point from the last
# one, so a packed netlist of many models converges as easily as one model alone.
IB_DECADES = (-8, -1)
IB_STEP = 0.1  # decades
FT = (0.02, 20, 100e6)  # IC, VCE, f
COB = (10, 1e6)  # VCB, f
CIB = (0.5, 1e6)  # VEB, f
SW = {"vcc": 30.0, "rl": 200.0, "rb": 1000.0, "von": 15.8, "voff": -14.2, "t_on": 100e-9,
      "t_off": 1.1e-6, "edge": 2e-9, "stop": 1.6e-6, "maxstep": 0.1e-9}

ANALYSES = ("dc", "ac", "tran")


def _n(x):
    return f"{x:.9g}"


def hfe_vces():
    return sorted({vce for _, vce in HFE_POINTS} | {FT[1]})


def _ib_expr(s, scale=1):
    sign = "-" if s < 0 else ""
    factor = f"{_n(scale)}*" if scale != 1 else ""
    return f"I={sign}{factor}exp(2.302585092994046*V(x))"


def fragment_dc(model, s, k, **_):
    lines = []
    for vi, vce in enumerate(hfe_vces()):
        t = f"{k}_{vi}"
        lines += [f"VC{t} c{t} 0 {_n(s * vce)}",
                  f"BIB{t} 0 b{t} {_ib_expr(s)}",
                  f"Q{t} c{t} b{t} 0 {model}"]
    # saturation: IC = 10 IB along the same sweep; the clamp diode only conducts if the transistor
    # cannot take 10 IB, which then shows as a collector near the clamp instead of a run that fails.
    clamp = f"DCL{k} cs{k} cl{k} DCLAMP" if s > 0 else f"DCL{k} cl{k} cs{k} DCLAMP"
    lines += [f"BSB{k} 0 bs{k} {_ib_expr(s)}",
              f"BSC{k} 0 cs{k} {_ib_expr(s, 10)}",
              clamp,
              f"VCL{k} cl{k} 0 {_n(s * SAT_CLAMP)}",
              f"QS{k} cs{k} bs{k} 0 {model}"]
    return lines


def fragment_ac(model, s, k, ib_ft=None, **_):
    """ib_ft: the base current that gives IC = 20 mA at VCE = 20 V, read from this model's DC run."""
    lines = []
    if ib_ft:
        lines += [f"VCT{k} ct{k} 0 {_n(s * FT[1])}",
                  f"IBT{k} 0 bt{k} DC {_n(s * ib_ft)} AC 1",
                  f"QT{k} ct{k} bt{k} 0 {model}"]
    return lines + [
        f"VCO{k} co{k} 0 {_n(s * COB[0])} AC 1",
        f"VBO{k} bo{k} 0 0",
        f"REO{k} eo{k} 0 1e12",
        f"QO{k} co{k} bo{k} eo{k} {model}",
        f"VEI{k} ei{k} 0 {_n(s * CIB[0])} AC 1",
        f"VBI{k} bi{k} 0 0",
        f"RCI{k} ci{k} 0 1e12",
        f"QI{k} ci{k} bi{k} ei{k} {model}",
    ]


def fragment_tran(model, s, k, **_):
    p = SW
    e = p["edge"]
    pwl = [(0, 0), (p["t_on"], 0), (p["t_on"] + e, p["von"]), (p["t_off"], p["von"]),
           (p["t_off"] + e, p["voff"]), (p["stop"], p["voff"])]
    pts = " ".join(f"{_n(t)} {_n(s * v)}" for t, v in pwl)
    return [
        f"VCC{k} vcc{k} 0 {_n(s * p['vcc'])}",
        f"RL{k} vcc{k} csw{k} {_n(p['rl'])}",
        f"QW{k} csw{k} bsw{k} 0 {model}",
        f"RBW{k} in{k} bsw{k} {_n(p['rb'])}",
        f"VIN{k} in{k} 0 PWL({pts})",
    ]


FRAGMENTS = {"dc": fragment_dc, "ac": fragment_ac, "tran": fragment_tran}


def saves(analysis, k, ib_ft=None, **_):
    """The vectors the measurements read, and nothing else: a waveform file of every node and every
    device current is several times larger, and a pack's transient can reach gigabytes."""
    if analysis == "dc":
        vecs = [v for vi in range(len(hfe_vces())) for v in (f"I(VC{k}_{vi})", f"V(b{k}_{vi})")]
        return vecs + [f"V(cs{k})", f"V(bs{k})"]
    if analysis == "ac":
        return ([f"I(VCT{k})"] if ib_ft else []) + [f"I(VCO{k})", f"I(VEI{k})"]
    return [f"V(vcc{k})", f"V(csw{k})"]


def analysis_card(analysis, engine):
    if analysis == "dc":
        lo, hi = IB_DECADES
        return ["VX x 0 0", "RX x 0 1", ".model DCLAMP D(Is=1e-14)", f".dc VX {lo} {hi} {IB_STEP}"]
    if analysis == "ac":
        return [".ac dec 20 1e5 1e10"]
    return [f".tran {_n(SW['maxstep'])} {_n(SW['stop'])} 0 {_n(SW['maxstep'])}"]


def netlist(analysis, engine, duts, title="bench bjt"):
    """duts: [(include_file, model_name, polarity_sign, extra)] — one or many, packed with index k;
    extra holds what the analysis needs from an earlier one (ib_ft for ac)."""
    lines = [f"* {title} - {analysis}"]
    for inc in dict.fromkeys(d[0] for d in duts):
        lines.append(f'.include "{inc}"')
    head = engines.header(engine)
    if head:
        lines.append(head)
    lines += [".options reltol=1e-4", ".temp 25"]
    for k, (_, model, s, extra) in enumerate(duts):
        lines += FRAGMENTS[analysis](model, s, k, **(extra or {}))
    if analysis == "dc":
        lines.append(".save V(x)")
    for k, (_, model, s, extra) in enumerate(duts):
        lines.append(".save " + " ".join(saves(analysis, k, **(extra or {}))))
    lines += analysis_card(analysis, engine)
    lines.append(".end")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- measurements from the waveforms

def _first(data, *names):
    for n in names:
        if n in data:
            return data[n]
    raise KeyError(f"none of {names} in {sorted(data)[:12]}…")


def _v(data, node):
    return _first(data, f"v({node})")


def _i(data, source):
    return _first(data, f"i({source})")


def _curve(d, s, k, vi):
    """(IB, IC, VBE) along the sweep of one VCE, in increasing IB; IC from its collector source."""
    x = _v(d, "x")
    ic = _i(d, f"vc{k}_{vi}")
    vb = _v(d, f"b{k}_{vi}")
    return [(10 ** xx, -c * s, v * s) for xx, c, v in zip(x, ic, vb)]


def _at_ic(curve, target):
    """(IB, VBE) where IC = target, interpolated in log IC; None outside the family."""
    for (ib0, ic0, vb0), (ib1, ic1, vb1) in zip(curve, curve[1:]):
        if 0 < ic0 <= target <= ic1:
            w = (math.log(target) - math.log(ic0)) / (math.log(ic1) - math.log(ic0))
            return math.exp(math.log(ib0) + w * (math.log(ib1) - math.log(ib0))), vb0 + w * (vb1 - vb0)
    return None, None


def measure_dc(plot, s, k):
    d = plot["data"]
    out = {}
    curves = {vce: _curve(d, s, k, vi) for vi, vce in enumerate(hfe_vces())}
    for ic, vce in HFE_POINTS:
        ib, vbe = _at_ic(curves[vce], ic)
        out[f"hfe@{ic * 1e3:g}mA,{vce:g}V"] = ic / ib if ib else None
        out[f"vbe@{ic * 1e3:g}mA,{vce:g}V"] = vbe
    out["_ib_ft"] = _at_ic(curves[FT[1]], FT[0])[0]
    x = _v(d, "x")
    vcs = [v * s for v in _v(d, f"cs{k}")]
    vbs = [v * s for v in _v(d, f"bs{k}")]
    ics = [10 * 10 ** xx for xx in x]
    for ic, ib in SAT_POINTS:
        key = f"{ic * 1e3:g}mA/{ib * 1e3:g}mA"
        vce = _interp_log(ics, vcs, ic)
        saturated = vce < SAT_CLAMP - 1
        out[f"vcesat@{key}"] = vce if saturated else None
        out[f"vbesat@{key}"] = _interp_log(ics, vbs, ic) if saturated else None
    return out


def _interp_log(xs, ys, x):
    """ys at x, interpolating in log(x)."""
    lx = math.log10(x)
    for a in range(len(xs) - 1):
        x0, x1 = xs[a], xs[a + 1]
        if x0 <= x <= x1:
            l0, l1 = math.log10(x0), math.log10(x1)
            w = 0 if l1 == l0 else (lx - l0) / (l1 - l0)
            return ys[a] + w * (ys[a + 1] - ys[a])
    raise ValueError(f"{x} outside the sweep")


def measure_ac(plot, s, k):
    d = plot["data"]
    f = [abs(x) for x in _first(d, "frequency")]
    out = {"h21@100MHz": None, "ft_100MHz_method_Hz": None, "ft_unity_Hz": None}
    if f"i(vct{k})" not in d:
        return out | _caps(d, f, k)
    h21 = [abs(x) for x in _i(d, f"vct{k}")]
    h_at = _interp_log(f, h21, FT[2])
    out["h21@100MHz"] = h_at
    out["ft_100MHz_method_Hz"] = h_at * FT[2]
    # where |h21| falls through 1, interpolated in log-log
    ft_cross = None
    for a in range(len(f) - 1):
        if h21[a] >= 1 > h21[a + 1]:
            l0, l1 = math.log10(h21[a]), math.log10(h21[a + 1])
            w = l0 / (l0 - l1)
            ft_cross = 10 ** (math.log10(f[a]) + w * (math.log10(f[a + 1]) - math.log10(f[a])))
            break
    out["ft_unity_Hz"] = ft_cross
    return out | _caps(d, f, k)


def _caps(d, f, k):
    out = {}
    w0 = 2 * math.pi
    ico = [x.imag for x in _i(d, f"vco{k}")]
    iei = [x.imag for x in _i(d, f"vei{k}")]
    out["cob_F"] = abs(_interp_log(f, ico, COB[1])) / (w0 * COB[1])
    out["cib_F"] = abs(_interp_log(f, iei, CIB[1])) / (w0 * CIB[1])
    return out


def _crossing(ts, ys, level, t_from, rising):
    for a in range(len(ts) - 1):
        if ts[a + 1] < t_from:
            continue
        y0, y1 = ys[a], ys[a + 1]
        if (rising and y0 < level <= y1) or (not rising and y0 > level >= y1):
            return ts[a] + (level - y0) / (y1 - y0) * (ts[a + 1] - ts[a])
    return None


def measure_tran(plot, s, k):
    d = plot["data"]
    t = _first(d, "time")
    vcc = _v(d, f"vcc{k}")
    vc = _v(d, f"csw{k}")
    ic = [(a - b) * s / SW["rl"] for a, b in zip(vcc, vc)]
    on = [x for tt, x in zip(t, ic) if SW["t_on"] + 0.5e-6 <= tt <= SW["t_off"]]
    ic_on = sum(on) / len(on)
    lo, hi = 0.1 * ic_on, 0.9 * ic_on
    edge_on = SW["t_on"] + SW["edge"] * 0.1
    edge_off = SW["t_off"] + SW["edge"] * 0.1
    t10r = _crossing(t, ic, lo, SW["t_on"], True)
    t90r = _crossing(t, ic, hi, SW["t_on"], True)
    t90f = _crossing(t, ic, hi, SW["t_off"], False)
    t10f = _crossing(t, ic, lo, SW["t_off"], False)
    out = {"ic_on_A": ic_on,
           "vce_on_V": sum(v * s for tt, v in zip(t, vc) if SW["t_on"] + 0.5e-6 <= tt <= SW["t_off"]) / len(on),
           "points": len(t)}
    out["td_s"] = t10r - edge_on if t10r else None
    out["tr_s"] = t90r - t10r if t90r and t10r else None
    out["ts_s"] = t90f - edge_off if t90f else None
    out["tf_s"] = t10f - t90f if t10f and t90f else None
    return out


MEASURE = {"dc": measure_dc, "ac": measure_ac, "tran": measure_tran}


def pick_plot(plots, analysis):
    want = {"dc": "dc", "ac": "ac", "tran": "transient"}[analysis]
    for p in plots:
        if want in p["name"].lower():
            return p
    return plots[-1]


def run_bench(model_file, model, polarity, out, repeat=1, engine=None):
    engine = engine or engines.engine_name()
    s = 1 if polarity.lower() == "npn" else -1
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(model_file, out / "model.lib")
    result = {"engine": engine, "version": engines.version(engine), "model": model, "polarity": polarity,
              "runs": [], "measurements": {}}
    extra = {}
    for analysis in ANALYSES:
        net = out / f"{analysis}.cir"
        dut = ("model.lib", model, s, {"ib_ft": extra.get("ib_ft")} if analysis == "ac" else None)
        net.write_text(netlist(analysis, engine, [dut], title=f"bench {model}"))
        for r in range(repeat):
            cost = engines.run(net, engine)
            cost["analysis"] = analysis
            cost["repeat"] = r
            meas = None
            if cost["raw"]:
                try:
                    meas = MEASURE[analysis](pick_plot(raw.read(cost["raw"]), analysis), s, 0)
                except Exception as exc:  # noqa: BLE001 — a failed read is a result too
                    cost["error"] = f"{type(exc).__name__}: {exc}"
            cost["digest"] = _digest(meas)
            result["runs"].append(cost)
            if meas is not None:
                if "_ib_ft" in meas:
                    extra["ib_ft"] = meas.pop("_ib_ft")
                result["measurements"].update(meas)
    (out / "result.json").write_text(json.dumps(result, indent=1, default=str))
    return result


def _digest(meas):
    import hashlib
    if meas is None:
        return None
    return hashlib.sha256(json.dumps(meas, sort_keys=True).encode()).hexdigest()[:16]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model-file", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--polarity", default="npn", choices=["npn", "pnp"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--engine", default=os.environ.get("SIM_ENGINE"))
    a = ap.parse_args(argv)
    res = run_bench(a.model_file, a.model, a.polarity, a.out, a.repeat, a.engine)
    json.dump({"engine": res["engine"], "measurements": res["measurements"],
               "errors": [r.get("error") for r in res["runs"] if r.get("error") or r["returncode"]]},
              sys.stdout, indent=1, default=str)
    print()


if __name__ == "__main__":
    main()
