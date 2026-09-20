# output-transformer — tube amp output transformers (push-pull, UL, tapped, SE)

`output-transformer.sub` models the output transformer between the power tubes and the
speaker. It covers:

- **Frequency response.** Primary inductance, leakage inductance and winding capacitance
  shape the bass roll-off and the high-frequency roll-off and resonance.
- **Losses.** Winding DC resistances and core loss.
- **Push-pull or single-ended**, with ultra-linear screen taps and tapped secondaries.
- **Flux saturation.** Bass farting and clipping of small SE and guitar OTs, including
  the DC bias flux of a gapped SE core.

Presets reproduce 19 Hammond transformers: Fender, Marshall and Vox replacements, the
1650 hi-fi series and the 125SE universal SE series. The numbers come from Hammond's
sheets and response graphs.

## Subckts and pins

| subckt | pins (symbol names) | use |
|---|---|---|
| `ot_pp` | P1 CT P2 S+ S− | push-pull, one secondary |
| `ot_pp_ul` | P1 G1 CT G2 P2 S+ S− | push-pull, ultra-linear screen taps G1, G2 |
| `ot_pp_tap` | P1 CT P2 COM S1 S2 S3 | push-pull, tapped secondary (4/8/16 …) |
| `ot_pp_ul_tap` | P1 G1 CT G2 P2 COM S1 S2 S3 | the general one: every other subckt wraps it |
| `ot_se` | P B+ S+ S− | single-ended (gapped core, DC bias flux) |
| `ot_se_tap` | P B+ COM S1 S2 S3 | single-ended, tapped secondary |

The subckt formal names are `SP SN BP`, and the symbols show them as `S+ S− B+`.

**Polarity.** S+ (or S3, the top tap) is in phase with P1 (or P), marked by the dots on
the symbol. To flip the sign of a feedback loop, swap S+/S− or swap the two plates.

**Symbol layout.** Every symbol uses the same geometry: primary on the left, pins at x=0,
P1 at the top, CT at y=96, P2 at y=176. Secondary on the right, pins at x=144, S+/S3 at
the top, COM/S− at the bottom. UL taps are at y=64/128. One `.asy` per subckt and per
preset, all written by `make_symbols.py`.

## Parameters (defaults: a 20 W, 6.6 k guitar OT)

| name | meaning | default |
|---|---|---|
| `Za` | primary impedance, plate-to-plate (PP) or plate-to-B+ (SE) | 6600 (SE 5000) |
| `Zs` / `Z1 Z2 Z3` | secondary impedance / tap impedances COM→S1/S2/S3 | 8 / 4 8 16 |
| `P` | rated power (sets the saturation flux together with `fsat`) | 20 W (SE 5) |
| `ul` | UL tap, fraction of each half-primary's turns from CT | 0.4 |
| `Lp` | primary inductance, whole primary, secondary open | 25 H (SE 15) |
| `flow` | if > 0, sets Lp from the −3 dB low corner with Rs = Za: Lp = (Za/2)/(2π·flow) | 0 |
| `Llk` | leakage inductance, whole primary, secondary shorted | 12 mH (SE 20 m) |
| `fhigh` | if > 0, sets Llk from the −3 dB high corner with Rs = Za: Llk = 2Za/(2π·fhigh) | 0 |
| `Cw` | effective primary winding capacitance, across P1–P2 | 300 p |
| `Rpri`, `rbal` | primary DCR; fraction of it in the P1–CT half | 300, 0.5 |
| `Rsec` / `R1 R2 R3` | secondary DCR / DCR COM→S1/S2/S3 | 0.5 / 0.3 0.5 0.8 |
| `Rc`, `Qc` | core-loss resistance across the primary; if `Rc`=0, Rc = Qc·2π·1 kHz·Lp | 0, 3 |
| `sat` | 1 = flux saturation, 0 = linear core | 1 |
| `fsat` | lowest frequency at which rated power passes unsaturated | 70 Hz |
| `ksat` | knee flux ÷ design peak flux | 1.25 |
| `Idc` | rated DC primary current (SE gapped core; 0 for PP) | 0 (SE 50 mA) |
| `Lsr`, `wk` | Lp ÷ incremental L deep in saturation; knee width as a fraction of knee flux | 100, 0.05 |

## Equations

**Windings.** Each winding is an ideal winding of relative turns N, in series with its
DCR and its share of the leakage. The whole primary has N = 1, each half 0.5, and a tap
has n = √(Z/Za). All leakage is referred to the primary, Llk/2 in each plate half, split
between plate and screen segments in proportion to turns.

Each winding forces V = N·V(c) and injects N·I into a core node c. So the core node
carries the net ampere-turns, referred to the whole primary.

**Core node.** The magnetising branch and the core loss sit on the core node:

- Magnetising current: i_m = g(λ), where λ = ∫V(c)dt (the flux linkage).
- g(λ) = λ/Lp + sat·[s(λ−Lk) − s(−λ−Lk)]·Lsr/Lp
- s(x) = w·ln(1+e^(x/w)), with w = wk·Lk (a softplus knee)
- Knee flux: Lk = ksat·[√(2·P·Za)/(2π·fsat) + Lp·Idc]
- Core loss: Rc in parallel with the magnetising branch.

The bracket in Lk is the design peak flux: the AC flux at rated power and fsat, plus the
DC bias flux of a gapped SE core at its rated current. Below the knee the inductance is
Lp. Above it, the incremental inductance falls to Lp/(1+Lsr).

**DC behaviour.** The flux integrator bleeds with τ = 1000 s, which is Lp·1 mΩ/H in
series with Lp. So `.op` is well defined, and in an SE stage the DC flux follows the
real DC plate current.

**Corners.** With a source Rs = Za and load Zs, the −3 dB points are:

- low: f = (Za/2)/(2π·Lp)
- high: f = 2Za/(2π·Llk)

Cw then adds the Llk–Cw resonance above the high corner. The bench checks both
formulas.

**Saturation calibration.** `ksat` = 1.25 and `wk` = 0.05 are estimates. They are set so
that at rated power and `fsat`, driven from Rs = Za, saturation just begins: about
0.6–1.8 % THD. At fsat/2 (twice the flux) the THD is 15–33 %.

This matches how Hammond states its ratings. The 1650 and 125SE sheets say "response
at full rated power" down to fsat. The guitar sheets say "distortion < 1 % at 70 Hz".
Designers typically run grain-oriented steel at about 0.8 of its knee flux, which
suggests a margin of about 1.25.

The shape parameters (`Lsr`, `wk`) are not fitted to a measured B–H curve.

## Presets (Hammond Mfg.)

Presets are one-line wrappers in the `.sub`, generated by `make_symbols.py` from
`ot_presets.py`. Each preset takes `sat fsat ksat Qc` as parameters, for example
`XOT p1 ct p2 com s1 s2 s3 OT_1760H sat=0`.

| preset | Hammond part | replaces | subckt |
|---|---|---|---|
| OT_1760E | 1760E | Fender 5E3 Deluxe, Princeton | ot_pp_tap 4/8/16 |
| OT_1760H | 1760H | Fender Deluxe / Deluxe Reverb | ot_pp_tap |
| OT_1760J | 1760J | Fender Pro / Bandmaster / Tremolux | ot_pp_tap |
| OT_1760L | 1760L | Fender Bassman 5F6A / AA864 / AB165 | ot_pp_tap |
| OT_1760W | 1760W | Fender Twin Reverb / Showman | ot_pp_tap |
| OT_1750N | 1750N | Marshall JMP / JCM800 50 W | ot_pp_tap |
| OT_1750U | 1750U | Marshall JMP / JCM800 100 W | ot_pp_tap |
| OT_1750Q | 1750Q | Marshall JTM45 | ot_pp_tap |
| OT_1750Y | 1750Y | Vox AC15 vintage | ot_pp 8 Ω |
| OT_1750V / _8 | 1750V | Vox AC30 vintage, 16 / 8 Ω tap | ot_pp |
| OT_1650F/H/N/R/T | 1650F/H/N/R/T | hi-fi UL 25/40/60/100/120 W | ot_pp_ul 40 %, 8 Ω |
| OT_1760C / _5K | 1760C | Fender Champ 5F1 / AA764, Vibro Champ (8 k / 5 k tap) | ot_se_tap 3.2/8/16 |
| OT_125ESE / 125CSE | 125ESE / 125CSE | universal SE 15 W / 8 W | ot_se_tap (8/16/32 Ω lugs at 10 k) |

## Provenance

Each preset's numbers come from its part sheet, `https://www.hammfg.com/files/parts/pdf/<PART>.pdf`
(fetched 2026-09-14), with the Fender/Marshall/Vox cross-references from
<https://www.hammfg.com/electronics/transformers/classic/1750.pdf>. The sheets are
downloaded copies in the scratch directory, not in `sources/`: add them to `sources/`
if you want them archived.

Source codes used in the table:

- **ds**: the sheet, page 1, "Electrical specifications".
- **g**: read off the sheet's response graph (page 2/3; Rs = Za, 27 dBu, 8 Ω curve) at
  20 and 30 kHz. Resolution is about ±0.1 dB and ±2°; the readings are in `fit_presets.py`.
- **fit**: fitted to those graph readings by `fit_presets.py`, using the same equivalent
  circuit the `.sub` implements.
- **sc**: scaled (explained per row).
- **est**: estimate (reasoning below).

| preset | Za, taps, P (ds) | L on the sheet → model Lp | Llk (whole primary) | Cw | DCR primary (ds) | DCR secondary | fsat | Idc |
|---|---|---|---|---|---|---|---|---|
| OT_1760E | 8500; 4/8/16; 15 W | 21.6 H @1 kHz → 19.9 H | 42.1 mH **fit** (sheet 323.9 mH contradicts its graph) | 99 p fit | 154.40 + 159.20 | 0.410/0.540/0.830 ds | 70 est | – |
| OT_1760H | 6600; 4/8/16; 20 W | 25.8 H → 23.0 H | 12.30 mH ds | 118 p fit | 347.8 | 0.686/0.803/1.157 ds | 70 est | – |
| OT_1760J | 4000; 4/8/16; 40 W | 19.5 H → 19.2 H | 35.93 mH ds | 20 p (floor: the leakage alone gives the graph's phase) | 185.0 | 0.356/0.502/0.910 ds | 70 est | – |
| OT_1760L | 4200; 4/8/16; 50 W | 5.72 H → 5.64 H | 3.506 mH ds | 66 p fit | 46.48 + 51.04 | 0.238/0.405/0.578 ds | 70 est | – |
| OT_1760W | 2000; 4/8/16; 100 W | 4.55 H → 4.54 H | 1.280 mH ds | 20 p (floor) | 13.24 + 14.44 | 0.110/0.175/0.279 ds | 70 est | – |
| OT_1750N | 3200; 4/8/16; 50 W | 18.3 H → 13.6 H | 13.41 mH ds | 477 p fit | 41.74 + 43.14 | 0.770 ds (COM–4 Ω); 8/16 Ω sc ∝ √Z | 70 est | – |
| OT_1750U | 1700; 4/8/16; 100 W | 8.85 H → 8.79 H | 7.97 mH ds | 20 p (floor) | 15.36 + 16.56 | 0.320 ds (COM–16 Ω); 4/8 Ω sc | 70 est | – |
| OT_1750Q | 7371; 4/8/16; 50 W | 38.0 H → 22.6 H | 19.87 mH ds | 453 p fit | 41.74 + 43.14 (sheet identical to 1750N, as published) | 0.580 ds (COM–16 Ω); 4/8 Ω sc | 70 est | – |
| OT_1750Y | 6200; 8; 15 W | 14.6 H → 13.0 H | 14.04 mH ds | 207 p fit | 289.0 | 0.480 ds | 70 est | – |
| OT_1750V(_8) | 4000; 16 (8); 30 W | 6.30 H → 6.10 H | 5.14 mH ds | 135 p fit | 70.37 + 70.30 | 0.720 ds (COM–16 Ω); 8 Ω 0.509 sc | 70 est | – |
| OT_1650F | 7600; 8; 25 W; UL 40 % | 285 H half-primary @60 Hz, 10 V → ×4 = 1140 H apparent → 1134 H | 38.8 mH **fit** (sheet: 10.40 mH on a half-primary) | 32 p fit | 210.0 | 0.245 est | 30 ds | – |
| OT_1650H | 6600; 8; 40 W; UL 40 % | 245 H half → 980 → 969 H | 35.2 mH fit (half 10.60) | 80 p fit | 77.0 + 68.0 | 0.216 est | 30 ds | – |
| OT_1650N | 4300; 8; 60 W; UL 40 % | 134 H half → 536 → 531 H | 17.9 mH fit (half 7.72) | 133 p fit | 82.5 | 0.300 est | 30 ds | – |
| OT_1650R | 5000; 8; 100 W; UL 40 % | 320 H half → 1280 → 1257 H | 26.6 mH fit (half 10.84) | 99 p fit | 54.59 + 46.62 | 0.360 est | 30 ds | – |
| OT_1650T | 1900; 8; 120 W; UL 40 % | 124 H half → 496 → 491 H | 5.96 mH fit (half 4.30) | 151 p fit | 47.10 | 0.295 est | 30 ds | – |
| OT_1760C | 8000; 3.2/8/16; 5 W | 23.0 H → 17.7 H | 6.03 mH sc (5 k fit × 8/5) | 334 p sc (5 k fit × 5/8) | 359.9 | 0.278/0.624/1.491 ds | 70 est | 40 mA ds |
| OT_1760C_5K | 5000; 3.2/8/16; 5 W | 16.2 H → 12.1 H | 3.77 mH fit (sheet 583 mH contradicts its graph) | 534 p fit | 272.08 | as above | 70 est | 40 mA ds |
| OT_125ESE | 10 k; 8/16/32 lugs; 15 W | 5.43 H → 5.21 H | 16.8 mH fit (no leakage on the sheet; amplitude graph only) | 200 p est | 103.0 | 0.225/0.297/0.412 ds | 100 ds | 80 mA ds |
| OT_125CSE | 10 k; 8/16/32 lugs; 8 W | 9.28 H → 8.65 H | 16.5 mH fit (as above) | 200 p est | 200.0 | 0.312/0.428/0.595 ds | 100 ds | 60 mA ds |

### How the derived and estimated numbers were obtained

- **Lp, model vs sheet.** Hammond's L is what an LCR meter reads with the secondary
  open: 1 kHz, 1 V for the 1750/1760/125 sheets, 60 Hz, 10 V for the 1650 sheets. The
  meter sees Lp in parallel with Cw. So model Lp = L_sheet/(1 + ω²·L_sheet·Cw), and the
  bench checks that the model's apparent L equals the sheet within 2 %.
- **1650 half-primary figures.** The 1650 sheets give L and Llk on one half-primary
  (Brown–Red). Magnetising L scales with N², so the whole primary is ×4 (the bench
  measures the half and gets the sheet value). Whole-primary leakage lies between 1× and
  4× the half value depending on interleaving, so it is fitted to the graph within those
  bounds.
- **Leakage figures that contradict their graphs.** The sheets list 323.9 mH (1760E) and
  719.5/583 mH (1760C). These would put the −3 dB point near 8 kHz and 3.5 kHz, but the
  sheets' own graphs are flat to 20 kHz (−0.05 to −0.25 dB). Leakage and Cw were
  therefore fitted to the graph. The 1650E (337.5 mH) has the same problem and was left
  out.
- **1760C 8 k tap.** The graph is measured on the 5 k tap (Rs = 5 k). The 8 k tap's
  Llk (∝ N²) and Cw (∝ 1/N²) are scaled by 8/5 and 5/8.
- **Cw.** Cw is the capacitance that gives the graph's phase at 20 kHz, with the sheet
  leakage. When the leakage alone already gives that phase, Cw is left at a 20 pF floor.
  The 125SE sheets have no phase plot, so Cw there is a 200 pF estimate: the median of
  the fitted guitar OTs is about 100–130 pF, rounded up for the SE bobbin winding.
- **Secondary DCR, scaled (sc).** When a sheet gives one COM–tap DCR, the others are
  scaled ∝ √Z (∝ turns, same wire).
- **1650 secondary DCR.** The 1650 has two secondary windings, and the 8 Ω hook-up
  engages both. The DCR used is the mean of the two published winding DCRs (est).
- **fsat.** The 1650 sheets say "30 Hz to 30 kHz at full rated power" and the 125SE
  sheets "100 Hz – 15 kHz at full rated power", so those are ds. The 1750/1760 sheets
  say "70 Hz – 15 kHz, distortion < 1 % at 70 Hz" without stating the level (their
  graphs are at 27 dBu), so 70 Hz is an estimate.
- **Core loss, Qc = 3 (est).** On sheets where |Z| at 1 kHz is below ωL (a parallel
  model), the implied core Q is 3.9 (1760H), 3.1 (1760E) and 2.2 (1760C).
- **1760 primary halves (rbal).** P1 is the dotted lead on each sheet, and
  rbal = DCR(P1–CT)/DCR(P1–P2).

## Bench results

Run `python3 bench_output-transformer.py` with the shell sandbox off. It exits 1 on any
failure. Rows marked "info" are shown for comparison and are not pass/fail. The full
output follows:

```
-- generic: ratios, UL tap, polarity, impedance (ot_pp_ul_tap, sat=0)
tap S1 ratio sqrt(4/6600)                                                              got    0.024618  want    0.024618  tol 0.001r    ok
tap S2 ratio sqrt(8/6600)                                                              got    0.034816  want    0.034816  tol 0.001r    ok
tap S3 ratio sqrt(16/6600)                                                             got    0.049237  want    0.049237  tol 0.001r    ok
S3 in phase with P1 (deg)                                                              got  6.9508e-07  want           0  tol 0.5       ok
UL tap V(G1,CT)/V(P1,CT) = ul                                                          got         0.4  want         0.4  tol 0.001r    ok
CT at half the primary voltage                                                         got         0.5  want         0.5  tol 0.001r    ok
Zin with Zs on S3 = Za                                                                 got      6601.2  want        6600  tol 0.002r    ok
-- generic: -3 dB corners vs formula (Rs = Za, RL = Zs, no Cw, no loss)
f-3dB low  Lp=25 Llk=12m (Hz)                                                          got          21  want      21.008  tol 0.01r     ok
f-3dB high Lp=25 Llk=12m (Hz)                                                          got  1.7517e+05  want  1.7507e+05  tol 0.01r     ok
f-3dB low  flow=25 fhigh=40k (Hz)                                                      got      24.958  want          25  tol 0.01r     ok
f-3dB high flow=25 fhigh=40k (Hz)                                                      got       40081  want       40000  tol 0.01r     ok
-- presets: DC resistance vs Hammond sheet (.op)
OT_1760E R(P1-CT)                                                                      got      154.39  want       154.4  tol 0.001r    ok
OT_1760E R(CT-P2)                                                                      got      159.22  want       159.2  tol 0.001r    ok
OT_1760E R(COM-S1)                                                                     got     0.41002  want        0.41  tol 0.002r    ok
OT_1760E R(COM-S2)                                                                     got     0.54003  want        0.54  tol 0.002r    ok
OT_1760E R(COM-S3)                                                                     got     0.83004  want        0.83  tol 0.002r    ok
OT_1760H Rpri                                                                          got       347.8  want       347.8  tol 0.001r    ok
OT_1760H R(COM-S1)                                                                     got     0.68603  want       0.686  tol 0.002r    ok
OT_1760H R(COM-S2)                                                                     got     0.80304  want       0.803  tol 0.002r    ok
OT_1760H R(COM-S3)                                                                     got      1.1571  want       1.157  tol 0.002r    ok
OT_1760J Rpri                                                                          got         185  want         185  tol 0.001r    ok
OT_1760J R(COM-S1)                                                                     got     0.35604  want       0.356  tol 0.002r    ok
OT_1760J R(COM-S2)                                                                     got     0.50205  want       0.502  tol 0.002r    ok
OT_1760J R(COM-S3)                                                                     got     0.91008  want        0.91  tol 0.002r    ok
OT_1760L R(P1-CT)                                                                      got      46.479  want       46.48  tol 0.001r    ok
OT_1760L R(CT-P2)                                                                      got      51.043  want       51.04  tol 0.001r    ok
OT_1760L R(COM-S1)                                                                     got     0.23801  want       0.238  tol 0.002r    ok
OT_1760L R(COM-S2)                                                                     got     0.40502  want       0.405  tol 0.002r    ok
OT_1760L R(COM-S3)                                                                     got     0.57802  want       0.578  tol 0.002r    ok
OT_1760W R(P1-CT)                                                                      got       13.24  want       13.24  tol 0.001r    ok
OT_1760W R(CT-P2)                                                                      got      14.442  want       14.44  tol 0.001r    ok
OT_1760W R(COM-S1)                                                                     got     0.11002  want        0.11  tol 0.002r    ok
OT_1760W R(COM-S2)                                                                     got     0.17503  want       0.175  tol 0.002r    ok
OT_1760W R(COM-S3)                                                                     got     0.27904  want       0.279  tol 0.002r    ok
OT_1750N R(P1-CT)                                                                      got      41.745  want       41.74  tol 0.001r    ok
OT_1750N R(CT-P2)                                                                      got      43.137  want       43.14  tol 0.001r    ok
OT_1750N R(COM-S1)                                                                     got     0.77003  want        0.77  tol 0.002r    ok
OT_1750N R(COM-S2) [scaled]                                                            got      1.0889  want      1.0889  tol info      
OT_1750N R(COM-S3) [scaled]                                                            got      1.5401  want        1.54  tol info      
OT_1750U R(P1-CT)                                                                      got      15.361  want       15.36  tol 0.001r    ok
OT_1750U R(CT-P2)                                                                      got      16.561  want       16.56  tol 0.001r    ok
OT_1750U R(COM-S1) [scaled]                                                            got     0.16004  want        0.16  tol info      
OT_1750U R(COM-S2) [scaled]                                                            got     0.22636  want     0.22627  tol info      
OT_1750U R(COM-S3)                                                                     got     0.32008  want        0.32  tol 0.002r    ok
OT_1750Q R(P1-CT)                                                                      got      41.745  want       41.74  tol 0.001r    ok
OT_1750Q R(CT-P2)                                                                      got      43.137  want       43.14  tol 0.001r    ok
OT_1750Q R(COM-S1) [scaled]                                                            got     0.29002  want        0.29  tol info      
OT_1750Q R(COM-S2) [scaled]                                                            got     0.41013  want     0.41012  tol info      
OT_1750Q R(COM-S3)                                                                     got     0.58005  want        0.58  tol 0.002r    ok
OT_1750Y Rpri                                                                          got         289  want         289  tol 0.001r    ok
OT_1750Y Rsec                                                                          got     0.48002  want        0.48  tol 0.002r    ok
OT_1750V R(P1-CT)                                                                      got      70.364  want       70.37  tol 0.001r    ok
OT_1750V R(CT-P2)                                                                      got      70.308  want        70.3  tol 0.001r    ok
OT_1750V Rsec                                                                          got     0.72002  want        0.72  tol 0.002r    ok
OT_1750V_8 R(P1-CT)                                                                    got      70.364  want       70.37  tol 0.001r    ok
OT_1750V_8 R(CT-P2)                                                                    got      70.308  want        70.3  tol 0.001r    ok
OT_1750V_8 Rsec [estimate]                                                             got     0.50911  want     0.50912  tol info      
OT_1650F Rpri                                                                          got         210  want         210  tol 0.001r    ok
OT_1650F Rsec [estimate]                                                               got     0.24607  want       0.245  tol info      
OT_1650H R(P1-CT)                                                                      got      76.995  want          77  tol 0.001r    ok
OT_1650H R(CT-P2)                                                                      got      68.005  want          68  tol 0.001r    ok
OT_1650H Rsec [estimate]                                                               got     0.21716  want       0.216  tol info      
OT_1650N Rpri                                                                          got        82.5  want        82.5  tol 0.001r    ok
OT_1650N Rsec [estimate]                                                               got     0.30099  want         0.3  tol info      
OT_1650R R(P1-CT)                                                                      got      54.593  want       54.59  tol 0.001r    ok
OT_1650R R(CT-P2)                                                                      got      46.617  want       46.62  tol 0.001r    ok
OT_1650R Rsec [estimate]                                                               got     0.36195  want        0.36  tol info      
OT_1650T Rpri                                                                          got        47.1  want        47.1  tol 0.001r    ok
OT_1650T Rsec [estimate]                                                               got     0.29703  want       0.295  tol info      
OT_1760C Rpri                                                                          got      359.92  want       359.9  tol 0.001r    ok
OT_1760C R(COM-S1)                                                                     got     0.27802  want       0.278  tol 0.002r    ok
OT_1760C R(COM-S2)                                                                     got     0.62402  want       0.624  tol 0.002r    ok
OT_1760C R(COM-S3)                                                                     got       1.491  want       1.491  tol 0.002r    ok
OT_1760C_5K Rpri                                                                       got      272.09  want      272.08  tol 0.001r    ok
OT_1760C_5K R(COM-S1)                                                                  got     0.27802  want       0.278  tol 0.002r    ok
OT_1760C_5K R(COM-S2)                                                                  got     0.62403  want       0.624  tol 0.002r    ok
OT_1760C_5K R(COM-S3)                                                                  got       1.491  want       1.491  tol 0.002r    ok
OT_125ESE Rpri                                                                         got      103.01  want         103  tol 0.001r    ok
OT_125ESE R(COM-S1)                                                                    got     0.22501  want       0.225  tol 0.002r    ok
OT_125ESE R(COM-S2)                                                                    got     0.29701  want       0.297  tol 0.002r    ok
OT_125ESE R(COM-S3)                                                                    got     0.41202  want       0.412  tol 0.002r    ok
OT_125CSE Rpri                                                                         got      200.01  want         200  tol 0.001r    ok
OT_125CSE R(COM-S1)                                                                    got     0.31201  want       0.312  tol 0.002r    ok
OT_125CSE R(COM-S2)                                                                    got     0.42802  want       0.428  tol 0.002r    ok
OT_125CSE R(COM-S3)                                                                    got     0.59503  want       0.595  tol 0.002r    ok
-- presets: primary L (secondary open) and leakage (secondary shorted) vs sheet
OT_1760E L_app @1000 Hz (H)                                                            got      21.683  want        21.6  tol 0.02r     ok
OT_1760H L_app @1000 Hz (H)                                                            got       25.86  want        25.8  tol 0.02r     ok
OT_1760J L_app @1000 Hz (H)                                                            got      19.553  want        19.5  tol 0.02r     ok
OT_1760L L_app @1000 Hz (H)                                                            got      5.7339  want        5.72  tol 0.02r     ok
OT_1760W L_app @1000 Hz (H)                                                            got      4.5541  want        4.55  tol 0.02r     ok
OT_1750N L_app @1000 Hz (H)                                                            got      18.338  want        18.3  tol 0.02r     ok
OT_1750U L_app @1000 Hz (H)                                                            got      8.8606  want        8.85  tol 0.02r     ok
OT_1750Q L_app @1000 Hz (H)                                                            got      38.076  want          38  tol 0.02r     ok
OT_1750Y L_app @1000 Hz (H)                                                            got      14.655  want        14.6  tol 0.02r     ok
OT_1750V L_app @1000 Hz (H)                                                            got      6.3209  want         6.3  tol 0.02r     ok
OT_1750V_8 L_app @1000 Hz (H)                                                          got      6.3209  want         6.3  tol 0.02r     ok
OT_1650F L_app @60 Hz (half) (H)                                                       got      285.03  want         285  tol 0.02r     ok
OT_1650H L_app @60 Hz (half) (H)                                                       got      245.03  want         245  tol 0.02r     ok
OT_1650N L_app @60 Hz (half) (H)                                                       got      134.01  want         134  tol 0.02r     ok
OT_1650R L_app @60 Hz (half) (H)                                                       got      320.03  want         320  tol 0.02r     ok
OT_1650T L_app @60 Hz (half) (H)                                                       got      124.01  want         124  tol 0.02r     ok
OT_1760C L_app @1000 Hz (H)                                                            got      23.075  want          23  tol 0.02r     ok
OT_1760C_5K L_app @1000 Hz (H)                                                         got      16.259  want        16.2  tol 0.02r     ok
OT_125ESE L_app @1000 Hz (H)                                                           got      5.4582  want        5.43  tol 0.02r     ok
OT_125CSE L_app @1000 Hz (H)                                                           got      9.3215  want        9.28  tol 0.02r     ok
OT_1760E Llk @1 kHz [fit; sheet 323.9] (mH)                                            got      42.299  want        42.1  tol info      
OT_1760H Llk @1 kHz (mH)                                                               got      12.472  want        12.3  tol 0.05r     ok
OT_1760J Llk @1 kHz (mH)                                                               got      35.997  want       35.93  tol 0.05r     ok
OT_1760L Llk @1 kHz (mH)                                                               got      3.6059  want       3.506  tol 0.05r     ok
OT_1760W Llk @1 kHz (mH)                                                               got      1.2871  want        1.28  tol 0.05r     ok
OT_1750N Llk @1 kHz (mH)                                                               got      13.517  want       13.41  tol 0.05r     ok
OT_1750U Llk @1 kHz (mH)                                                               got      7.9736  want        7.97  tol 0.05r     ok
OT_1750Q Llk @1 kHz (mH)                                                               got      19.902  want       19.87  tol 0.05r     ok
OT_1750Y Llk @1 kHz (mH)                                                               got      14.222  want       14.04  tol 0.05r     ok
OT_1750V Llk @1 kHz (mH)                                                               got      5.2613  want        5.14  tol 0.05r     ok
OT_1750V_8 Llk @1 kHz (mH)                                                             got      5.3887  want        5.14  tol 0.05r     ok
OT_1650F Llk @1 kHz [fit; sheet 10.4] (mH)                                             got        38.8  want        38.8  tol info      
OT_1650H Llk @1 kHz [fit; sheet 10.6] (mH)                                             got      35.199  want        35.2  tol info      
OT_1650N Llk @1 kHz [fit; sheet 7.72] (mH)                                             got      17.897  want        17.9  tol info      
OT_1650R Llk @1 kHz [fit; sheet 10.84] (mH)                                            got      26.595  want        26.6  tol info      
OT_1650T Llk @1 kHz [fit; sheet 4.3] (mH)                                              got      5.9591  want        5.96  tol info      
OT_1760C Llk @1 kHz [sc; sheet 719.5] (mH)                                             got      6.4192  want        6.03  tol info      
OT_1760C_5K Llk @1 kHz [fit; sheet 583] (mH)                                           got      3.9346  want        3.77  tol info      
OT_125ESE Llk @1 kHz [fit; sheet nan] (mH)                                             got      16.873  want        16.8  tol info      
OT_125CSE Llk @1 kHz [fit; sheet nan] (mH)                                             got      16.574  want        16.5  tol info      
-- presets: response re 1 kHz vs Hammond graph (Rs = graph Rs, 8 ohm load)
OT_1760E 20 kHz dB (graph)                                                             got    -0.25983  want       -0.25  tol 0.5       ok
OT_1760E 20 kHz deg (graph)                                                            got     -20.994  want         -20  tol 5         ok
OT_1760E 30 kHz dB (graph)                                                             got    -0.58151  want        -0.6  tol info      
OT_1760E 30 kHz deg (graph)                                                            got     -30.706  want         -31  tol info      
OT_1760H 20 kHz dB (graph)                                                             got   -0.018188  want       -0.05  tol 0.5       ok
OT_1760H 20 kHz deg (graph)                                                            got     -10.146  want         -10  tol 5         ok
OT_1760H 30 kHz dB (graph)                                                             got   -0.045442  want       -0.15  tol info      
OT_1760H 30 kHz deg (graph)                                                            got     -14.845  want         -17  tol info      
OT_1760J 20 kHz dB (graph)                                                             got     -1.0829  want        -1.3  tol 0.5       ok
OT_1760J 20 kHz deg (graph)                                                            got     -28.039  want         -27  tol 5         ok
OT_1760J 30 kHz dB (graph)                                                             got     -2.1445  want        -2.6  tol info      
OT_1760J 30 kHz deg (graph)                                                            got     -38.933  want         -40  tol info      
OT_1760L 20 kHz dB (graph)                                                             got    0.010443  want           0  tol 0.5       ok
OT_1760L 20 kHz deg (graph)                                                            got     -7.0492  want          -7  tol 5         ok
OT_1760L 30 kHz dB (graph)                                                             got   0.0038564  want       -0.05  tol info      
OT_1760L 30 kHz deg (graph)                                                            got     -9.0947  want         -10  tol info      
OT_1760W 20 kHz dB (graph)                                                             got -0.00068777  want           0  tol 0.5       ok
OT_1760W 20 kHz deg (graph)                                                            got     -4.2343  want          -2  tol 5         ok
OT_1760W 30 kHz dB (graph)                                                             got  -0.0082943  want           0  tol info      
OT_1760W 30 kHz deg (graph)                                                            got     -5.4837  want          -3  tol info      
OT_1760C_5K 20 kHz dB (graph)                                                          got     -0.0765  want       -0.05  tol 0.5       ok
OT_1760C_5K 20 kHz deg (graph)                                                         got     -13.922  want         -13  tol 5         ok
OT_1760C_5K 30 kHz dB (graph)                                                          got    -0.17944  want        -0.2  tol info      
OT_1760C_5K 30 kHz deg (graph)                                                         got     -20.257  want         -20  tol info      
OT_1750N 20 kHz dB (graph)                                                             got     -0.1224  want        -0.1  tol 0.5       ok
OT_1750N 20 kHz deg (graph)                                                            got     -20.144  want         -20  tol 5         ok
OT_1750N 30 kHz dB (graph)                                                             got    -0.29838  want        -1.3  tol info      
OT_1750N 30 kHz deg (graph)                                                            got     -30.374  want         -30  tol info      
OT_1750U 20 kHz dB (graph)                                                             got    -0.34219  want        -0.4  tol 0.5       ok
OT_1750U 20 kHz deg (graph)                                                            got     -16.285  want         -15  tol 5         ok
OT_1750U 30 kHz dB (graph)                                                             got    -0.73726  want        -0.7  tol info      
OT_1750U 30 kHz deg (graph)                                                            got     -23.705  want         -22  tol info      
OT_1750Q 20 kHz dB (graph)                                                             got   -0.041282  want        -0.3  tol 0.5       ok
OT_1750Q 20 kHz deg (graph)                                                            got     -22.577  want         -22  tol 5         ok
OT_1750Q 30 kHz dB (graph)                                                             got    -0.15349  want        -2.1  tol info      
OT_1750Q 30 kHz deg (graph)                                                            got     -34.439  want         -38  tol info      
OT_1750Y 20 kHz dB (graph)                                                             got   -0.014956  want       -0.05  tol 0.5       ok
OT_1750Y 20 kHz deg (graph)                                                            got      -14.22  want         -14  tol 5         ok
OT_1750Y 30 kHz dB (graph)                                                             got   -0.047797  want       -0.15  tol info      
OT_1750Y 30 kHz deg (graph)                                                            got     -20.744  want         -21  tol info      
OT_1750V_8 20 kHz dB (graph)                                                           got   0.0028668  want       -0.05  tol 0.5       ok
OT_1750V_8 20 kHz deg (graph)                                                          got     -9.0998  want          -9  tol 5         ok
OT_1750V_8 30 kHz dB (graph)                                                           got  -0.0095284  want       -0.15  tol info      
OT_1750V_8 30 kHz deg (graph)                                                          got     -12.413  want         -14  tol info      
OT_1650F 20 kHz dB (graph)                                                             got    -0.36644  want       -0.35  tol 0.5       ok
OT_1650F 20 kHz deg (graph)                                                            got     -17.387  want         -17  tol 5         ok
OT_1650F 30 kHz dB (graph)                                                             got    -0.78681  want        -0.8  tol info      
OT_1650F 30 kHz deg (graph)                                                            got     -25.748  want         -26  tol info      
OT_1650H 20 kHz dB (graph)                                                             got    -0.36325  want        -0.3  tol 0.5       ok
OT_1650H 20 kHz deg (graph)                                                            got     -19.257  want         -20  tol 5         ok
OT_1650H 30 kHz dB (graph)                                                             got    -0.78415  want        -0.8  tol info      
OT_1650H 30 kHz deg (graph)                                                            got     -28.659  want         -28  tol info      
OT_1650N 20 kHz dB (graph)                                                             got    -0.20576  want        -0.1  tol 0.5       ok
OT_1650N 20 kHz deg (graph)                                                            got     -15.731  want         -15  tol 5         ok
OT_1650N 30 kHz dB (graph)                                                             got    -0.45423  want        -0.5  tol info      
OT_1650N 30 kHz deg (graph)                                                            got     -23.704  want         -24  tol info      
OT_1650R 20 kHz dB (graph)                                                             got    -0.36037  want        -0.3  tol 0.5       ok
OT_1650R 20 kHz deg (graph)                                                            got     -18.957  want         -19  tol 5         ok
OT_1650R 30 kHz dB (graph)                                                             got    -0.77758  want        -0.8  tol info      
OT_1650R 30 kHz deg (graph)                                                            got     -28.208  want         -28  tol info      
OT_1650T 20 kHz dB (graph)                                                             got    -0.12921  want        -0.1  tol 0.5       ok
OT_1650T 20 kHz deg (graph)                                                            got     -11.345  want         -10  tol 5         ok
OT_1650T 30 kHz dB (graph)                                                             got    -0.28642  want        -0.3  tol info      
OT_1650T 30 kHz deg (graph)                                                            got     -17.144  want         -18  tol info      
OT_125ESE 20 kHz dB (graph)                                                            got   -0.071549  want        -0.1  tol 0.5       ok
OT_125ESE 30 kHz dB (graph)                                                            got    -0.19804  want        -0.2  tol info      
OT_125CSE 20 kHz dB (graph)                                                            got   -0.079402  want        -0.1  tol 0.5       ok
OT_125CSE 30 kHz dB (graph)                                                            got    -0.19599  want        -0.2  tol info      
-- saturation: THD of V(S+) at rated power, Rs = Za (calibration target ~1 % at fsat)
ot_se THD % at P, fsat=70 Hz                                                           got      1.7565  want        1.65  tol [0.3,3]   ok
ot_se THD % at P, fsat/2 (2x flux)                                                     got      15.562  want          54  tol [8,100]   ok
ot_se THD % at P, 2 fsat                                                               got     0.10352  want        0.25  tol [0,0.5]   ok
ot_se THD % at P, 1 kHz                                                                got    0.020402  want        0.05  tol [0,0.1]   ok
ot_se THD % at P, fsat/2, sat=0                                                        got  7.2479e-09  want       0.025  tol [0,0.05]  ok
ot_pp THD % at P, fsat=70 Hz                                                           got     0.63421  want        1.65  tol [0.3,3]   ok
ot_pp THD % at P, fsat/2 (2x flux)                                                     got      32.842  want          54  tol [8,100]   ok
ot_pp THD % at P, 2 fsat                                                               got  0.00056098  want        0.25  tol [0,0.5]   ok
ot_pp THD % at P, 1 kHz                                                                got    0.018251  want        0.05  tol [0,0.1]   ok
ot_pp THD % at P, fsat/2, sat=0                                                        got  1.3948e-06  want       0.025  tol [0,0.05]  ok
-- convergence with real tubes (.tran), 6V6GT Reefman model
PP 6V6 -> 1760H, 10 V drive, 1 kHz: Pout (W)                                           got      2.0264  want         nan  tol info      
PP 6V6 -> 1760H, 60 V drive (clipped), 1 kHz: Pout (W)                                 got      34.216  want      27.732  tol [10,45.4631] ok
PP 6V6 -> 1760H, clipped, 82 Hz: Pout (W)                                              got      41.917  want      27.732  tol [10,45.4631] ok
UL 6V6 -> 1650F, 1 kHz: Pout (W)                                                       got      10.022  want        16.5  tol [3,30]    ok
SE 6V6 -> 1760C, 40 Hz: THD % linear core                                              got      13.453  want         nan  tol info      
SE 6V6 -> 1760C, 40 Hz: THD % saturating / linear                                      got      3.8054  want      500.75  tol [1.5,1000] ok
-- demo_output-transformer.asc netlisted by asc2net = hand netlist
demo |V(out)| @100 Hz = hand netlist                                                   got    0.015583  want    0.015583  tol 0.0001r   ok
demo |V(out)| @1000 Hz = hand netlist                                                  got    0.016033  want    0.016033  tol 0.0001r   ok
demo |V(out)| @10000 Hz = hand netlist                                                 got    0.016028  want    0.016028  tol 0.0001r   ok

154/154 checks passed
```

## What it does not model

- **One core node.** All leakage is referred to the primary, so the tap-dependent
  high-frequency roll-off in Hammond's graphs is not reproduced (the 4 Ω curve is
  usually worst). The class-B half-to-half leakage is not separate: each half simply
  carries Llk/2.
- **High end is second-order only.** The steep drop of 1750N and 1750Q above 20 kHz
  (−1.3 and −2.1 dB at 30 kHz, against −0.3 and −0.15 dB in the model) needs the
  distributed winding capacitance.
- **Constant permeability below the knee.** Real Lp rises with flux. The Hammond graphs
  at 27 dBu show 2–5× more inductance at 50 Hz than the 1 kHz, 1 V figure; for example
  1760L is −1 dB at 50 Hz where the model gives about −4 dB. So the modelled bass
  roll-off at low level is pessimistic. Override `Lp` or `flow` if you have a
  working-level figure.
- **No hysteresis.** There is no remanence and no low-level hysteresis distortion. The
  graphs show 0.2–1.8 % THD at 50 Hz at 27 dBu; the model gives ≈0 below the knee.
- **Generic saturation shape.** Softplus knee, Lsr = 100, wk = 0.05, ksat = 1.25, as
  calibrated above, not fitted to a measured B–H curve.
- **Missing elements.** No primary-to-secondary or primary-to-core capacitance, no
  frequency-dependent eddy loss (Rc is constant), no temperature effects.

## Files

- `output-transformer.sub`: the subckts and the generated presets.
- `ot_presets.py`: the preset table, with sheet numbers and sources.
- `fit_presets.py`: the Cw/Llk fit and the graph readings.
- `make_symbols.py`: writes the presets, all `.asy` symbols and
  `demo_output-transformer.asc`.
- `bench_output-transformer.py`: the bench.

The demo is a Deluxe Reverb OT (OT_1760H) driven from Rs = Za, with 8 Ω on the 8 Ω
tap. The bench netlists it with `tools/ltspice/asc2net.py` and checks it against a hand
netlist, which verifies the pin order.

## Sources of inspiration

- Coupled-inductor OTs with a UL split primary and Cp across the plates: Norman Koren's
  PAT-4006 and Dynaco models, `sources/koren/extracted/Tubemods/Tube.lib`, and the
  article `sources/koren/raw/Tubemodspice_article.html` ("Output transformers").
- Ideal windings on a shared core node (E/F sources): `Winding_LCR` in
  `sources/ltwiki/extracted/lib/lib/sub/Transformers.lib`.
- Ampeg OTs as coupled inductors with DCR and K = 0.9988 (no C, no saturation):
  `sources/suusi-tubes/extracted/SuusiTubes_V1/OT8950030.net`.
- Fender push-pull OT (`transPPc.INC`): `sources/robrobinette/extracted/Deluxe/`.
- The Trace Elliot OT models listed on
  `sources/duncanamps/raw/pages/spicetransformers.html`.

No text was copied from these sources.
