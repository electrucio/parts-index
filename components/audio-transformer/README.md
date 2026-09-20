# audio-transformer — microphone input and valve interstage transformers

`audio-transformer.sub` models small-signal audio transformers:

- **microphone / line input transformers** (step-up into a valve or FET grid);
- **valve interstage transformers**: SE→SE, SE→PP phase splitter, PP→PP;
- **line-output transformers**.

It uses the same approach as `components/output-transformer`: ideal windings on one core
node, with winding resistances, leakage inductance, lumped capacitances, core loss and an
optional flux-saturation knee (including the DC bias flux of a gapped SE core).

Presets reproduce the Jensen JT-115K-E, the Lundahl LL1538 (both connections) and six
connections of the Lundahl LL1660.

## Subckts and pins

| subckt | pins (SpiceOrder) | use |
|---|---|---|
| `atx` | P1 P2 S1 S2 | one primary, one secondary (input, SE interstage, line output) |
| `atx_sct` | P1 P2 S1 SC S2 | centre-tapped secondary (SE → PP phase splitter) |
| `atx_ct` | P1 PC P2 S1 SC S2 | centre-tapped primary and secondary: the general one, which the others wrap |
| `XF_<part>_<conn>` (9 presets) | as their subckt | `sat` (0 = linear core, default), `ksat` |

- **Polarity.** S1 is in phase with P1: V(S1,S2) = +n·V(P1,P2) at mid band (dots on the
  symbol).
- **Centre taps.** PC and SC split each winding into equal halves (half the turns, half the
  DCR).
- **Grounding.** Nothing is tied to ground inside, except 1 GΩ from S2 (or SC) so that a
  floating secondary has a DC path.

**Symbols.** The primary is on the left (pins at x = 0) and the secondary on the right
(x = 128). P1/S1 are at y = 32, the centre taps at y = 80, P2/S2 at y = 128. One `.asy`
per subckt and per preset, all written by `make_symbols.py`.

## Parameters

| name | meaning | default |
|---|---|---|
| `n` | turns ratio, whole secondary ÷ whole primary | 10 |
| `Lp` | primary inductance, whole primary, secondary open | 5 H |
| `Llk` | leakage inductance referred to the whole primary (secondary shorted) | 100 µH |
| `Rp`, `Rs` | primary DCR P1–P2, secondary DCR S1–S2 | 20, 2k |
| `Cp`, `Cs` | effective capacitance across P1–P2 and across S1–S2 | 0, 100 p |
| `Rc`, `Qc` | core-loss resistance across the primary; if `Rc` = 0, Rc = Qc·2π·1 kHz·Lp | 0, 10 |
| `sat` | 1 = flux saturation, 0 = linear core | 0 |
| `Vsat`, `fsat` | the primary rms voltage and frequency at which the core is at its design flux | 1 V, 20 Hz |
| `ksat` | knee flux ÷ design peak flux | 1.25 |
| `Idc` | DC primary current the (gapped) core is biased with | 0 |
| `Lsr`, `wk` | Lp ÷ incremental L deep in saturation; knee width | 100, 0.05 |

## Equations

**Windings.** Every winding is an ideal winding of relative turns N (whole primary 1,
each primary half ½, each secondary half n/2) in series with its DCR. The leakage is all
on the primary, Llk/2 per half. Each winding forces V = N·V(c) and injects N·I into the
core node c.

**Core node.** On c sit the core loss Rc and the magnetising branch:

- i_m = g(λ), with λ = ∫V(c)dt (a lossy integrator, τ = 1000 s, so `.op` is defined and
  the DC flux follows the DC current);
- g(λ) = λ/Lp + sat·[s(λ−Lk) − s(−λ−Lk)]·Lsr/Lp, where s(x) = w·ln(1+e^(x/w)) and
  w = wk·Lk;
- Lk = ksat·[√2·Vsat/(2π·fsat) + Lp·Idc].

**Corners.**

- Low: with a source Rg and load RL on the secondary, f = R′/(2π·Lp), where
  R′ = (Rg + Rp) ‖ (RL + Rs)/n².
- High: Llk with Cs·n² (and Cp) forms a second-order low-pass.

## Presets and provenance

All datasheets were fetched on 2026-09-14. `xf_presets.py` holds every number, its
source code and the fits; `make_symbols.py` writes the preset block into the `.sub`. Each
preset's comment in the `.sub` repeats the source of each parameter.

Source codes: **ds** datasheet value, **der** derived from ds values by the stated
formula, **fit** fitted to ds figures, **est** estimate.

| document | URL | sha256 of the PDF fetched |
|---|---|---|
| Jensen JT-115K-E (2 pp.) | <https://www.jensen-transformers.com/wp-content/uploads/2014/08/jt-115K-e1.pdf> | `a881b2436e1a0e3f9aa42352b86c3b627492f50b4916702c0e70f1551657b0b3` |
| Lundahl LL1660 (R030211, 2 pp.) | <https://www.lundahltransformers.com/wp-content/uploads/datasheets/1660.pdf> | `26c02e97c098cf0910fe6d5a7474fed5da4ca851f64ab0e6170c05a3d5f0593f` |
| Lundahl LL1538/LL1538XL (R980616) | <https://www.lundahltransformers.com/wp-content/uploads/datasheets/1538_8xl.pdf> | `3600d3570e48b57296ec315e5b8a575aa501639a5542596f21aa262291f952d4` |

The PDFs are copies in the session scratch directory, not in `sources/`: add them to
`datasheets/` if you want them archived.

### XF_JT115KE — Jensen JT-115K-E, 1:10 microphone input

All figures come from the p. 2 specification table, test circuit 1 (75 + 75 Ω generator,
150 kΩ load), unless noted.

| parameter | value | source |
|---|---|---|
| n | 10 | ds turns ratio 1:10.00 (1:9.95–1:10.05) |
| Rp / Rs | 19.7 / 2465 Ω | ds DC resistances (RED–BRN / YEL–ORG) |
| Rc | 14.59 kΩ | **fit**: Zi = 1.40 kΩ at 1 kHz |
| Lp | 4.835 H | **fit**: magnitude −0.26 dB at 20 Hz (−20 dBu) |
| Llk, Cs | 3.573 mH, 6.29 pF | **fit**: −0.13 dB at 20 kHz (table) and −3 dB at 90 kHz (p. 1 feature list) |
| Cp | 0 | the ds "475 pF primary to shield" is common-mode with a balanced source |
| Vsat, fsat | 0.581 V (−2.5 dBu), 20 Hz | ds "Maximum 20 Hz input level, 1% THD: −2.5 dBu typ" |
| ksat | 1.193 | **fit** (`fit_sat.py`): 1 % THD at that level in test circuit 1 |

How the fit works (`fit_jt()`): six rounds of bisection, one unknown per target, using a
numpy model of the same circuit. The response is V(S)/V(generator), relative to 1 kHz.

Why a core-loss resistance is needed: 150 kΩ reflected through 1:10 is 1.5 kΩ, above the
published 1.40 kΩ even with zero DCR. The difference is a shunt of about 15 kΩ at the
primary, i.e. core loss. The ds output impedance (17.0 kΩ, with the 150 kΩ load in place)
then follows independently, and the bench checks it.

**The Llk/Cs pair is effective, not physical.** Only one solution exists: Cs ≈ 6 pF, with
the high end set by the leakage. The secondary sees about 17 kΩ of source, and with that
any capacitance above about 100 pF across the secondary could not give −3 dB at 90 kHz.
Jensen's 205 pF "secondary to shield" is therefore mostly not across the secondary in
test circuit 1 (ORG, the cold end, is at shield potential). The pair reproduces the
published response; do not read Cs as the winding capacitance.

### XF_LL1660_M/N/Q/S/T/V — Lundahl LL1660 connections

**Sections.** The winding drawing (p. 1) gives:

- sections A (pins 2–5 and 10–7): 315 Ω, 1 unit of turns each (ds);
- sections B (3–4 and 9–8): 240 Ω, 1 unit each (ds);
- sections C (13–16 and 21–18): 625 Ω, 2.25 units each (ds).

The DCR of each connection follows from the p. 2 drawings (**der**).

| preset | connection (ds) | n | Rp Ω (der) | Rs Ω (der) | Lp H (ds) | Idc (ds) | ±1 dB band @ source (ds) | Cp (der) | Vsat = Vmax/n @ 30 Hz |
|---|---|---|---|---|---|---|---|---|---|
| XF_LL1660_M | Alt M″ PP→PP 2.25+2.25 : 2+2 (`atx_ct`) | 0.889 | 1250 (C+C) | 1110 (A+B)+(A+B) | 290 | – | 20 Hz–25 kHz @ 15 k | 216 p | 585 V (2×260 V out) |
| XF_LL1660_N | Alt N PP line out 2.25+2.25 : 1 (`atx_ct`, SC unused) | 0.222 | 1250 | 68.1 (4 in parallel) | 290 | – | 16 Hz–30 kHz @ 15 k | 180 p | 585 V (130 V out) |
| XF_LL1660_Q | Alt Q SE line out 4.5 : 1 (`atx`) | 0.222 | 1250 | 68.1 | 100 | 16 mA | 11 Hz–35 kHz @ 3 k | 771 p | 256.5 V (57 V out) |
| XF_LL1660_S | Alt S SE→SE 4 : 4.5 (`atx`) | 1.125 | 1110 (all 4 series) | 1250 | 130 | 10 mA | 25 Hz–40 kHz @ 14 k | 145 p | 222 V (250 V out) |
| XF_LL1660_T | Alt T SE→SE 2 : 4.5 (`atx`) | 2.25 | 277.5 (pairs in parallel) | 1250 | 33 | 20 mA | 25 Hz–30 kHz @ 3.5 k | 771 p | 111 V (250 V out) |
| XF_LL1660_V | Alt V SE→PP 2.25 : 2+2 (`atx_sct`) | 1.778 | 312.5 (C ‖ C) | 1110 | 42 | 18 mA | 25 Hz–30 kHz @ 3.5 k | 771 p | 124 V (220 V out) |

- **Cp (der).** The datasheet measures with the secondaries open, so the upper edge is a
  first-order R–C: −1 dB where ω·Rsrc·Cp = 0.5088. Cp is that effective,
  primary-referred capacitance; Cs = 0.
- **Llk is not published.** It is 0 in the presets, which is harmless with a grid load.
  Set it if you load the secondary heavily.
- **Core loss** uses the default Qc = 10 (est).
- **Saturation.** Vsat is the "max output voltage @ 30 Hz" referred to the primary.
  `ksat` = 1.25 is the output-transformer estimate: Lundahl gives no THD figure. Lundahl
  states the SE gap gives 0.9 T of DC flux at the rated current, leaving 0.7 T for the
  signal. The model puts the DC flux as Lp·Idc into the knee.

### XF_LL1538_5 / XF_LL1538_25 — Lundahl LL1538 microphone input

| parameter | 1:5 (primaries parallel) | 1:2.5 (primaries series) | source |
|---|---|---|---|
| n | 5 | 2.5 | ds turns 1+1 : 5, connection drawings |
| Rp | 22 Ω (44 ‖ 44) | 88 Ω (44 + 44) | ds "static resistance of each primary 44 Ω" |
| Rs | 880 Ω | 880 Ω | ds "static resistance of each secondary 880 Ω" (the drawing shows one secondary, 5–6) |
| Lp | 13.21 H | 52.85 H | **der**: the smallest Lp that keeps 10 Hz within −0.3 dB with 200 Ω and no termination; ×4 in series (N²) |
| Llk, Cs | 145 µH, 175 pF | 579 µH, 175 pF | **est**, see below |
| Vsat, fsat | 2.5 V, 50 Hz | 5 V, 50 Hz | ds "1 % @ +10 dBU (2.5 V rms) primary level, 50 Hz" (primaries parallel); ×2 in series |
| ksat | 1.108 | 1.108 | **fit** (`fit_sat.py`) on 1:5 at +10 dBu = 2.449 V, same core for 1:2.5 |

**Llk and Cs are estimates.** The datasheet gives only "10 Hz–100 kHz ±0.3 dB (source
200 Ω, no termination)" and "self resonance point > 120 kHz". The estimate is a maximally
flat (Q = 0.707) second-order high end at 200 kHz: the lowest resonance that keeps
100 kHz within −0.3 dB. It is made on the 1:5 connection, with Q set by the source
resistance seen from the secondary. The response row does not name a connection; in
1:2.5 the reflected source is smaller, so the same Llk/Cs peak by about +1.9 dB at
100 kHz (bench, info).

### Left out

- **Hammond 124-series interstage transformers.** hammfg.com did not answer during this
  work, so no sheet could be read.
- **The LL1538XL**: same structure, 61/975 Ω, 1 % at +13 dBu. It can be added in
  `xf_presets.py`.

## Bench results

Run `python3 bench_audio-transformer.py` with the shell sandbox off. It exits 1 on any
failure. `[fit]`, `[der]` and `[est]` in a row name mark numbers that were used to set the
parameters, so those rows only confirm the implementation. The independent checks are:

- the DCRs and turns ratios;
- the JT-115K-E gain V(S)/V(P) at 1 kHz (ds min–max 19.65–19.85 dB);
- the JT-115K-E output impedance, 17.0 kΩ;
- the JT-115K-E magnitudes within the ds min/max limits;
- the centre-tap balance;
- `.tran` against `.ac`;
- the demo's pin order.

Rows marked "info" are shown for comparison and are not pass/fail.

Full output:

```
-- DC resistance (.op, 1 mA) and turns ratio / polarity (1 kHz, 0 ohm source, open secondary)
XF_JT115KE R(P1-P2) (ds 19.7 (RED-BRN))                                                        got      19.705  want        19.7  tol 0.002r      ok
XF_JT115KE R(S1-S2) (ds 2465 (YEL-ORG))                                                        got      2465.5  want        2465  tol 0.002r      ok
XF_LL1660_M R(P1-P2) (der (sections, see drawing))                                             got      1250.3  want        1250  tol 0.002r      ok
XF_LL1660_M R(S1-S2) (der (sections, see drawing))                                             got      1110.2  want        1110  tol 0.002r      ok
XF_LL1660_N R(P1-P2) (der (sections, see drawing))                                             got      1250.3  want        1250  tol 0.002r      ok
XF_LL1660_N R(S1-S2) (der (sections, see drawing))                                             got      68.122  want      68.108  tol 0.002r      ok
XF_LL1660_Q R(P1-P2) (der (sections, see drawing))                                             got      1250.1  want        1250  tol 0.002r      ok
XF_LL1660_Q R(S1-S2) (der (sections, see drawing))                                             got      68.113  want      68.108  tol 0.002r      ok
XF_LL1660_S R(P1-P2) (der (sections, see drawing))                                             got      1110.1  want        1110  tol 0.002r      ok
XF_LL1660_S R(S1-S2) (der (sections, see drawing))                                             got      1250.2  want        1250  tol 0.002r      ok
XF_LL1660_T R(P1-P2) (der (sections, see drawing))                                             got      277.53  want       277.5  tol 0.002r      ok
XF_LL1660_T R(S1-S2) (der (sections, see drawing))                                             got      1250.2  want        1250  tol 0.002r      ok
XF_LL1660_V R(P1-P2) (der (sections, see drawing))                                             got      312.54  want       312.5  tol 0.002r      ok
XF_LL1660_V R(S1-S2) (der (sections, see drawing))                                             got      1110.1  want        1110  tol 0.002r      ok
XF_LL1538_5 R(P1-P2) (der 44 || 44)                                                            got      22.013  want          22  tol 0.002r      ok
XF_LL1538_5 R(S1-S2) (ds 880 (secondary 5-6))                                                  got      880.33  want         880  tol 0.002r      ok
XF_LL1538_25 R(P1-P2) (der 44 + 44)                                                            got      88.053  want          88  tol 0.002r      ok
XF_LL1538_25 R(S1-S2) (ds 880 (secondary 5-6))                                                 got      880.33  want         880  tol 0.002r      ok
XF_JT115KE V(S1,S2)/V(P1,P2) = n (ds 1:10.00 (1:9.95..1:10.05))                                got        9.98  want          10  tol 0.003r      ok
XF_JT115KE polarity: phase S1 re P1 (deg)                                                      got   -0.060976  want           0  tol 1           ok
XF_LL1660_M V(S1,S2)/V(P1,P2) = n (ds Alt M'' 2.25+2.25 : 2+2)                                 got     0.88883  want     0.88889  tol 0.003r      ok
XF_LL1660_M polarity: phase S1 re P1 (deg)                                                     got    0.039303  want           0  tol 1           ok
XF_LL1660_N V(S1,S2)/V(P1,P2) = n (ds Alt N 2.25+2.25 : 1)                                     got     0.22221  want     0.22222  tol 0.003r      ok
XF_LL1660_N polarity: phase S1 re P1 (deg)                                                     got    0.039303  want           0  tol 1           ok
XF_LL1660_Q V(S1,S2)/V(P1,P2) = n (ds Alt Q 4.5 : 1)                                           got     0.22218  want     0.22222  tol 0.003r      ok
XF_LL1660_Q polarity: phase S1 re P1 (deg)                                                     got     0.11396  want           0  tol 1           ok
XF_LL1660_S V(S1,S2)/V(P1,P2) = n (ds Alt S 4 : 4.5)                                           got      1.1248  want       1.125  tol 0.003r      ok
XF_LL1660_S polarity: phase S1 re P1 (deg)                                                     got    0.077851  want           0  tol 1           ok
XF_LL1660_T V(S1,S2)/V(P1,P2) = n (ds Alt T 2 : 4.5)                                           got      2.2497  want        2.25  tol 0.003r      ok
XF_LL1660_T polarity: phase S1 re P1 (deg)                                                     got    0.076671  want           0  tol 1           ok
XF_LL1660_V V(S1,S2)/V(P1,P2) = n (ds Alt V 2.25 : 2+2)                                        got      1.7776  want      1.7778  tol 0.003r      ok
XF_LL1660_V polarity: phase S1 re P1 (deg)                                                     got    0.067841  want           0  tol 1           ok
XF_LL1538_5 V(S1,S2)/V(P1,P2) = n (ds 1:5)                                                     got      4.9999  want           5  tol 0.003r      ok
XF_LL1538_5 polarity: phase S1 re P1 (deg)                                                     got   -0.074967  want           0  tol 1           ok
XF_LL1538_25 V(S1,S2)/V(P1,P2) = n (ds 1:2.5)                                                  got         2.5  want         2.5  tol 0.003r      ok
XF_LL1538_25 polarity: phase S1 re P1 (deg)                                                    got    -0.07497  want           0  tol 1           ok
-- primary inductance: Im(Z)/w at 20 Hz, secondary open
XF_JT115KE Lp (H) (fit: -0.26 dB at 20 Hz (test circuit 1))                                    got      4.8304  want       4.835  tol 0.01r       ok
XF_LL1660_M Lp (H) (ds)                                                                        got      290.29  want         290  tol 0.01r       ok
XF_LL1660_N Lp (H) (ds)                                                                        got      290.24  want         290  tol 0.01r       ok
XF_LL1660_Q Lp (H) (ds)                                                                        got      100.12  want         100  tol 0.01r       ok
XF_LL1660_S Lp (H) (ds)                                                                        got      130.04  want         130  tol 0.01r       ok
XF_LL1660_T Lp (H) (ds)                                                                        got      33.013  want          33  tol 0.01r       ok
XF_LL1660_V Lp (H) (ds)                                                                        got      42.021  want          42  tol 0.01r       ok
XF_LL1538_5 Lp (H) (der: -0.3 dB at 10 Hz, 200 ohm, no termination)                            got      13.222  want       13.21  tol 0.01r       ok
XF_LL1538_25 Lp (H) (der: 4 x the 1:5 value (N^2))                                             got      52.899  want       52.85  tol 0.01r       ok
-- centre taps: halves balanced; Alt V drives two grids in antiphase (SC grounded)
XF_LL1660_M: |V(S1,SC)| / |V(SC,S2)|                                                           got           1  want           1  tol 0.002       ok
XF_LL1660_M: phase V(S2) re V(S1) (deg)                                                        got         180  want         180  tol 0.5         ok
XF_LL1660_V: |V(S1,SC)| / |V(SC,S2)|                                                           got           1  want           1  tol 0.002       ok
XF_LL1660_V: phase V(S2) re V(S1) (deg)                                                        got         180  want         180  tol 0.5         ok
XF_LL1660_M driven push-pull from PC: V(S1,S2) = n * V(P1,P2)                                  got      0.8879  want     0.88889  tol 0.003r      ok
-- Jensen JT-115K-E, test circuit 1 (75 + 75 ohm generator, 150 k load)
magnitude re 1 kHz at 20 Hz (dB) [Lp fitted]                                                   got    -0.25999  want       -0.26  tol 0.02        ok
magnitude re 1 kHz at 20 kHz (dB) [Llk, Cs fitted]                                             got    -0.12994  want       -0.13  tol 0.02        ok
upper -3 dB point (kHz) [Llk, Cs fitted]                                                       got      90.009  want          90  tol 0.02r       ok
magnitude at 20 Hz within the ds limits -0.50 .. 0.0 dB                                        got    -0.25999  want       -0.25  tol [-0.5,0]    ok
magnitude at 20 kHz within the ds limits -0.25 .. +0.1 dB                                      got    -0.12994  want      -0.075  tol [-0.25,0.1] ok
lower -3 dB point (Hz); ds feature list: 2.5 Hz (level-dependent Lp, see README)               got      4.9831  want         2.5  tol info        
Zi at 1 kHz (ohm) [Rc fitted]                                                                  got        1400  want        1400  tol 0.01r       ok
voltage gain V(S)/V(P) at 1 kHz (dB), ds min/typ/max 19.65/19.75/19.85                         got      19.729  want       19.75  tol [19.65,19.85] ok
Zo at 1 kHz (ohm), ds typ 17.0 k (150 k load in place)                                         got       17155  want       17000  tol 0.03r       ok
-- Jensen JT-115K-E saturation (sat=1): THD at the ds 1 % point (-2.5 dBu at 20 Hz)
  primary rms at -2.5 dBu drive (V)                                                            got     0.56254  want     0.58087  tol info        
THD % of V(S) at -2.5 dBu, 20 Hz: ds max 20 Hz input level, 1 % THD typ (calibration)          got      1.0002  want        1.65  tol [0.3,3]     ok
  primary rms at -20 dBu drive (V)                                                             got    0.075209  want     0.07746  tol info        
THD % of V(S) at -20 dBu, 20 Hz: 20 dB lower: saturation gone                                  got  0.00016242  want       0.025  tol [0,0.05]    ok
THD % at -5 dBu, 20 Hz vs Jensen graph reading                                                 got     0.02533  want         0.4  tol info        
THD % at 0 dBu, 30 Hz vs Jensen graph reading                                                  got     0.16568  want         0.4  tol info        
THD % at -5 dBu, 30 Hz vs Jensen graph reading                                                 got   0.0014694  want        0.13  tol info        
THD % at 0 dBu, 50 Hz vs Jensen graph reading                                                  got    0.008942  want        0.11  tol info        
-- Lundahl LL1538: response with 200 ohm source, no termination, +-0.3 dB 10 Hz-100 kHz (ds)
XF_LL1538_5 re 1 kHz at 10 Hz (dB) [Lp der, Llk/Cs est for this band]                          got    -0.29993  want           0  tol [-0.3,0.3]  ok
XF_LL1538_5 re 1 kHz at 100000 Hz (dB) [Lp der, Llk/Cs est for this band]                      got    -0.26322  want           0  tol [-0.3,0.3]  ok
XF_LL1538_5 self-resonance (phase -90 deg) > 120 kHz (ds) [est]                                got      200.68  want       5e+08  tol [120,1e+09] ok
XF_LL1538_25 re 1 kHz at 10 Hz (dB) [ds band assumed for 1:5 only]                             got   -0.032727  want           0  tol info        
XF_LL1538_25 re 1 kHz at 100000 Hz (dB) [ds band assumed for 1:5 only]                         got      1.8743  want           0  tol info        
XF_LL1538_25 self-resonance (phase -90 deg) > 120 kHz (ds) [est]                               got      200.68  want       5e+08  tol [120,1e+09] ok
-- Lundahl LL1538 1:5 saturation (sat=1), 200 ohm source, 50 Hz
THD % at 10 dBu, 50 Hz (ds 1 % at +10 dBu (calibration))                                       got     0.99593  want        1.65  tol [0.3,3]     ok
THD % at 0 dBu, 50 Hz (ds 0.2 % at 0 dBu: hysteresis, not modelled)                            got    0.024248  want         0.2  tol info        
-- Lundahl LL1660: +-1 dB band edges with the ds source impedance, secondaries open
XF_LL1660_M (Alt M'' 2.25+2.25 : 2+2, 15k) at 20 Hz (dB), ds within +-1 dB                     got    -0.78444  want          -1  tol info        
XF_LL1660_M (Alt M'' 2.25+2.25 : 2+2, 15k) at 25 kHz (dB) [Cp derived from this edge]          got    -0.99701  want          -1  tol 0.05        ok
XF_LL1660_M (Alt M'' 2.25+2.25 : 2+2, 15k): model -1 dB low point (Hz), ds 20                  got      17.493  want          20  tol info        
XF_LL1660_N (Alt N 2.25+2.25 : 1, 15k) at 16 Hz (dB), ds within +-1 dB                         got     -1.1719  want          -1  tol info        
XF_LL1660_N (Alt N 2.25+2.25 : 1, 15k) at 30 kHz (dB) [Cp derived from this edge]              got    -0.99751  want          -1  tol 0.05        ok
XF_LL1660_N (Alt N 2.25+2.25 : 1, 15k): model -1 dB low point (Hz), ds 16                      got      17.498  want          16  tol info        
XF_LL1660_Q (Alt Q 4.5 : 1, 3k) at 11 Hz (dB), ds within +-1 dB                                got     -1.3904  want          -1  tol info        
XF_LL1660_Q (Alt Q 4.5 : 1, 3k) at 35 kHz (dB) [Cp derived from this edge]                     got    -0.99819  want          -1  tol 0.05        ok
XF_LL1660_Q (Alt Q 4.5 : 1, 3k): model -1 dB low point (Hz), ds 11                             got      13.277  want          11  tol info        
XF_LL1660_S (Alt S 4 : 4.5, 14k) at 25 Hz (dB), ds within +-1 dB                               got     -1.8892  want          -1  tol info        
XF_LL1660_S (Alt S 4 : 4.5, 14k) at 40 kHz (dB) [Cp derived from this edge]                    got    -0.99494  want          -1  tol 0.05        ok
XF_LL1660_S (Alt S 4 : 4.5, 14k): model -1 dB low point (Hz), ds 25                            got      36.251  want          25  tol info        
XF_LL1660_T (Alt T 2 : 4.5, 3.5k) at 25 Hz (dB), ds within +-1 dB                              got     -1.8426  want          -1  tol info        
XF_LL1660_T (Alt T 2 : 4.5, 3.5k) at 30 kHz (dB) [Cp derived from this edge]                   got    -0.99484  want          -1  tol 0.05        ok
XF_LL1660_T (Alt T 2 : 4.5, 3.5k): model -1 dB low point (Hz), ds 25                           got      35.695  want          25  tol info        
XF_LL1660_V (Alt V 2.25 : 2+2, 3.5k) at 25 Hz (dB), ds within +-1 dB                           got     -1.2466  want          -1  tol info        
XF_LL1660_V (Alt V 2.25 : 2+2, 3.5k) at 30 kHz (dB) [Cp derived from this edge]                got    -0.99591  want          -1  tol 0.05        ok
XF_LL1660_V (Alt V 2.25 : 2+2, 3.5k): model -1 dB low point (Hz), ds 25                        got      28.323  want          25  tol info        
-- SE interstage with DC: LL1660 Alt S, 10 mA through the primary, 14 k source, sat=1
  V(S) rms (V), target 249.975                                                                 got      239.06  want         nan  tol info        
THD % of V(S), 30 Hz, at the ds max output (250 V at 30 Hz): knee reached                      got      2.1144  want        2.65  tol [0.3,5]     ok
  V(S) rms (V), target 62.4937                                                                 got       60.28  want         nan  tol info        
THD % of V(S), 30 Hz, 12 dB lower: linear                                                      got    0.011061  want        0.05  tol [0,0.1]     ok
DC flux at 10 mA = Lp*Idc (V s); knee = ksat*(AC design + DC)                                  got         1.3  want         nan  tol info        
-- .tran vs .ac: JT-115K-E test circuit 1, 100 mV 1 kHz
amplitude .tran = |V| .ac (V)                                                                  got     0.87567  want     0.87557  tol 0.01r       ok
-- demo_audio-transformer.asc netlisted by asc2net = hand netlist
demo |V(out)| @10 Hz = hand netlist                                                            got      7.8405  want      7.8405  tol 0.0001r     ok
demo |V(out)| @1000 Hz = hand netlist                                                          got      8.7557  want      8.7557  tol 0.0001r     ok
demo |V(out)| @100000 Hz = hand netlist                                                        got      5.7195  want      5.7195  tol 0.0001r     ok

77/77 checks passed
```

## What it does not model

- **Constant permeability below the knee.** Real Lp rises with level, and the datasheets
  show it.
  - The JT-115K-E table gives −0.26 dB at 20 Hz at −20 dBu (Lp = 4.8 H here), while its
    feature list gives −3 dB at 2.5 Hz. The model, fitted to the table, has its −3 dB
    point near 5 Hz.
  - With the published LL1660 Lp and the primary DCR, the model's −1 dB points are
    17.5, 17.5, 13.3, 36, 36 and 28 Hz for M″, N, Q, S, T, V. The datasheet gives 20,
    16, 11, 25, 25 and 25 Hz: only M″ meets its edge. Lundahl's footnote says the source
    impedances are "a recommended upper limit", and its Lp is evidently a working-level
    figure.
  - So at low level the modelled bass roll-off is pessimistic. Override `Lp` if you have
    a working-level value.
- **No hysteresis.** The datasheets' low-level THD floors (JT-115K-E 0.065 % at 20 Hz,
  −20 dBu; LL1538 0.2 % at 0 dBu, 50 Hz) are absent: the model gives about 0 below the
  knee. The shape of the saturation knee is the generic softplus one, calibrated only at
  the 1 % point.
- **The knee is too sharp.** Below the 1 % point the model's THD falls much faster than
  Jensen's THD-vs-level graph (info rows):
  - 20 Hz, −5 dBu: 0.03 % in the model against about 0.4 % on the graph;
  - 30 Hz, 0 dBu: 0.17 % against 0.4 %;
  - 50 Hz, 0 dBu: 0.009 % against 0.11 %.

  Mu-metal's permeability bends gradually, so use `sat=1` for the onset of bass
  saturation, not for low-level colouration.
- **Lumped capacitances.** There are no shield or common-mode capacitances (so no CMRR),
  no interwinding capacitance, and no distributed-winding resonances above the
  second-order high end.
- **One core node.** All leakage is on the primary, and the two halves of a centre-tapped
  winding are perfectly coupled (no half-to-half leakage for class-B/AB drive).
- **Core loss is a fixed resistor** (no frequency or flux dependence).

## How to use it in LTspice

1. Put `audio-transformer.sub` and the `.asy` files next to your schematic (or in your
   LTspice `lib/sub` and `lib/sym` folders).
2. Place e.g. `XF_JT115KE`. Its `ModelFile` attribute points at `audio-transformer.sub`;
   if LTspice does not find it, add `.lib audio-transformer.sub`.
3. Set `sat=1` for level-dependent saturation.

Netlist examples:

- `XT1 in1 in2 g 0 XF_JT115KE`: a mic transformer into a grid at node g.
- `XT2 p bplus g1 0 g2 XF_LL1660_V sat=1`: an SE plate driving a push-pull pair, with the
  SC pin grounded (or to the bias supply).
- A generic one: `XT3 p 0 s 0 atx n=5 Lp=10 Llk=200u Rp=30 Rs=900 Cs=150p`.

The demo (`demo_audio-transformer.asc`) is the JT-115K-E in Jensen's test circuit 1:
150 Ω balanced source, 150 kΩ load.

## Files

- `audio-transformer.sub`: the subckts and the generated presets.
- `xf_presets.py`: the datasheet numbers, the source codes, the JT-115K-E fit and the
  LL1538/LL1660 derivations.
- `fit_sat.py`: the ksat calibration (LTspice).
- `make_symbols.py`: writes the presets, all `.asy` symbols and
  `demo_audio-transformer.asc`.
- `bench_audio-transformer.py`: the bench.

## Sources of inspiration

- `components/output-transformer/output-transformer.sub`: winding and core structure,
  softplus saturation.
- Ideal windings on a shared core node (E/F sources): `Winding_LCR` in
  `sources/ltwiki/extracted/lib/lib/sub/Transformers.lib`.

No text was copied from these sources.

## Local copies of the cited documents

The PDFs cited above are archived in `datasheets/components/` with URL, date and sha256
(`datasheets/components/SOURCES.md`).
