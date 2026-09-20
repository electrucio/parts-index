# mains-transformer — power transformers for tube and solid-state amps

`mains-transformer.sub` models mains (power) transformers as a single saturable core
with ideal windings. Each winding has its measured DC resistance and a per-unit
leakage. The core has a magnetising inductance set from the no-load current, a
core-loss resistor and a flux knee.

Presets reproduce Hammond tube-amp transformers (370 series; 290 series Fender
replacements) and a 2×18 V 160 VA toroid (Hammond 1182N18) for solid-state amps.
From one set of parameters the model gives:

- no-load voltages;
- regulation;
- rectifier conduction (sag, ripple);
- magnetising current;
- behaviour off rating: over-voltage, a 60 Hz part on 50 Hz, and inrush at switch-on.

## Subckts and pins

| subckt | pins | use |
|---|---|---|
| `pt_tube` | P1 P2 HV1 BIAS HVCT HV2 H1 HCT H2 | tube amp: HV centre-tapped, bias tap on the HV1 half, heater with CT |
| `pt_tube_aux` | … + A1 A2 | + an auxiliary winding (5 V rectifier heater, 2nd heater) |
| `pt_ss` | P1 P2 SA1 SA2 SB1 SB2 | solid state, two equal secondaries |
| `pt_ss_ct` | P1 P2 S1 SCT S2 | the same, series-connected (centre tap) |

In-phase ends (dots on the symbols): P1, HV1, H1, A1, SA1, SB1, S1.

The symbols are written by `make_symbols.py`. The primary is on the left (P1 at y=16,
P2 at y=112); the secondaries are stacked on the right at x=160, in pin order.

## Parameters

Winding voltages are **RMS no-load voltages at rated primary voltage**. They set the
turns ratios, and makers publish them as "N.L.V.". Currents are rated currents as the
maker states them; for an HV centre-tapped winding that is the DC load current.

| name | meaning | default (`pt_tube*` / `pt_ss*`) |
|---|---|---|
| `Vp` | rated primary voltage | 120 / 230 |
| `fline` | frequency at which `Iex` is specified | 60 / 50 |
| `fmin` | lowest rated mains frequency (sets the design flux) | 50 |
| `Vhv Ihv` | HV winding end to end, rating | 600, 0.1 |
| `Vb Ib` | bias tap HVCT→BIAS voltage, rating (`Vb`=0: no tap) | 50, 10 m |
| `Vh Ih` | heater end to end, rating | 6.8, 3 |
| `Va Ia` | auxiliary winding | 5.3, 3 |
| `Vs Is` | each secondary of `pt_ss*` | 19.4, 4.44 |
| `Iex` | no-load primary current at Vp, fline (magnetising + loss) | 0.1 / 20 m |
| `Pfe` | core loss at Vp (0 = 3 % of VA / 1 % of VA) | 0 |
| `reg` | full-load regulation used for any DCR left at 0 | 0.08 |
| `Rp Rhv Rh Ra Rs1 Rs2` | DC resistances (0 = from `reg`) | 0 |
| `hbal`, `Rb` | fraction of Rhv in the HV1 half; HVCT–BIAS DCR (0 = pro rata) | 0.5, 0 |
| `xlk` | leakage reactance per unit of each winding's own rating | 0.01 / 0.0025 |
| `sat ksat Lsr wk` | saturation on; knee ÷ design flux; Lm ÷ incremental L deep in saturation; knee width | 1, 1.25, 1000, 0.02 |

Presets take `pri` and `sat`. `pri=1` puts the two primaries in parallel (120 V, or
117 V for the toroid). `pri=2` puts them in series (240/234 V).

## Equations

**Windings.** The primary is an ideal winding with N = 1; secondary k has
N_k = V_k(no load)/Vp. Every winding k is DCR + L_k + an ideal winding on a core node.
The core node voltage is the primary voltage, and the node carries the net
ampere-turns.

**Defaults when a value is left at 0.**

- DC resistance: R_k = (reg/2)·V_k/I_k, so half of the full-load drop is in the winding
  and half in the primary. The resulting regulation at a resistive rated load is
  exactly `reg`; the bench checks this.
- Leakage: L_k = (xlk/2)·V_k/(I_k·2π·fline).

**Core (referred to the primary).**

- Core loss: Rc = Vp²/Pfe.
- Magnetising inductance: Im = √(Iex² − (Pfe/Vp)²), Lm = Vp/(2π·fline·Im). So the total
  no-load current equals `Iex`.
- Magnetising current: i = g(λ), with λ = ∫V dt and
  g(λ) = λ/Lm + sat·[s(λ−Lk) − s(−λ−Lk)]·Lsr/Lm, s(x) = w·ln(1+e^(x/w)).
- Knee flux: Lk = ksat·√2·Vp/(2π·fmin), with w = wk·Lk.

At rated voltage and fmin the core is 1/ksat below the knee. Twice the flux (inrush)
or 20 % more (a 60 Hz part on 50 Hz) takes it into saturation. Deep in saturation the
inductance is Lm/(1+Lsr), so inrush is limited mainly by the primary DCR.

The flux integrator bleeds with τ = 10⁵ s. That makes `.op` well defined, at the cost
of an Lm/10⁵ Ω resistance in series with Lm at DC.

**Starting a `.tran`.** A mains source `SINE(0 {Vpk} {f})` starts at 0 V. That is a
switch-on at a zero crossing: the worst-case inrush, with a flux offset that decays
through Rp (slowly for a toroid).

For a quick steady state, use a soft start:

`B1 p1 0 V=Vpk*sin(2*pi*f*time)*min(time/50m,1)`

This is what the demo and the bench do. Never start the source at its peak without
`uic`, because `.op` would put DC across the primary.

## Presets and provenance

The Hammond sheets are image PDFs at `https://www.hammfg.com/files/parts/pdf/<PART>.pdf`
(fetched 2026-09-14). Each gives:

- no-load voltages ("Sec. N.L.V.", at 120 V 60 Hz, or 117 V 60 Hz for the toroid);
- DCR at 20 °C;
- the maximum no-load current Iex (Hammond gives a maximum; it is used as the value);
- secondary ratings "under load".

The Fender cross-references come from the 290 series catalogue
<https://www.hammfg.com/electronics/transformers/classic/290.pdf>. Copies of the sheets
are in the scratch directory, not in `sources/`.

| preset | ratings (sheet) | N.L.V. used (V) | DCR used (Ω) | Iex | estimates |
|---|---|---|---|---|---|
| `PT_370AX` | 2×(0-100-110-120 V) 50/60 Hz; 480 V CT @ 58 mA; 50 V bias; 6.3 V CT @ 2.5 A; 44 VA | HV 520.1, half 260.1, bias 50.06, heater 7.013 | primaries 19.45 ‖ 21.36; HV 333.2; heater 0.150 | 80 mA | xlk 0.01, Pfe 3 %, Ib 10 mA |
| `PT_370CX` | 550 V CT @ 75 mA; 50 V bias; 6.3 V CT @ 2.5 A (H); 6.3 V CT @ 0.6 A (aux) | 608.8, 304.4, 50.00, 6.977, 6.977 | 14.39 ‖ 15.81; 361.3; 0.112 (H); 0.435 (aux) | 77 mA | as above |
| `PT_370FX` | 550 V CT @ 173 mA; 50 V bias; 6.3 V CT @ 5 A; 5 V CT @ 3 A (aux); 141 VA | 586.3, 293.2, 50.13, 6.835, 5.316 | 4.541 ‖ 4.902; 106.0; 0.053; 0.063 | 132 mA | as above |
| `PT_290AX` | Fender Champ / Princeton / Vibro Champ / Bronco (125P1B, 022772, 66079B); 120 V 60 Hz only; 650/550 V CT @ 100 mA; 6.3 V CT @ 2.25 A; 5 V @ 3 A | HV 702.3 (the 650 V taps), half 351.2, heater 6.841, 5 V 5.416 | 3.927; 277.1; 0.108; 0.091 | 184 mA | 550 V taps (594.6 V NL) not modelled |
| `PT_290EX` | Fender Bassman AA864/AB165, Bandmaster AA763 (67233, 125P7D, 022814); 120 V 60 Hz only; 660 V CT @ 275 mA; 53 V bias; 6.4 V CT @ 4 A | 686.2, 343.1, 55.21, 6.761 | 1.291; halves 18.50 (bias side) + 17.14; bias segment 2.877; 0.038 | 700 mA | xlk, Pfe as above |
| `PT_1182N18` (`_CT`) | toroid, 2×117 V 50/60 Hz, 2×18 V @ 4.44 A, 160 VA, regulation 7.70 % (series table <https://www.hammfg.com/electronics/transformers/power/1182.pdf>) | 19.39 each | primaries 5.100 ‖ 5.100; secondaries 0.140 | **46 mA est** | Iex, Pfe 1.6 W (1 %), xlk 0.0025 |

### Where the estimates come from

**Leakage `xlk`.** Rod Elliott, *Transformers Part 2*, <https://sound-au.com/xfmr2.htm>,
measured primary-referred leakage with the secondary shorted. Converted to per unit
(assuming 230 V primaries, the author's mains):

| transformer | leakage | per unit |
|---|---|---|
| 2 VA E-I | 762 mH | 0.9 % |
| 200 VA E-I | 8 mH | 0.95 % |
| 80 VA toroid | 6.4 mH | 0.30 % |
| 160 VA toroid | 1.8 mH | 0.17 % |
| 300 VA toroid | 1.63 mH | 0.29 % |

Hence 0.01 for E-I and 0.0025 for toroids.

**Core loss `Pfe`.** The same article measured 2.88 W on a 300 VA toroid and 5.28 W on a
500 VA toroid (about 1 %), and 42 W on a 350 VA E-I "operating at the knee" (12 %).
Hammond publishes no loss figure. The E-I default of 3 % is a middle estimate; the
toroid default of 1 % follows the measurements.

**Toroid Iex.** Hammond gives no figure for the 1182N18. The same article measured
42 mA at 240 V on a 300 VA toroid, about 10 VA or 3.4 % of its rating. Scaled to
160 VA at 117 V this gives 46 mA.

**Saturation shape (`ksat`, `Lsr`, `wk`).** These are estimates, chosen so that:

- at rated voltage the no-load current stays at Iex (the bench checks 80–700 mA
  within 0.3 %);
- a zero-crossing switch-on draws an inrush a hundred or more times the no-load peak,
  limited by the primary DCR. The article measured more than 150 A for a 200 VA E-core
  against about 4 A best case; the 370FX here gives 28.5 A, 152× its no-load peak and
  below its Vpk/Rp ceiling of 72 A.

**`fmin`.** 50 Hz for the 370 and 1182 (rated 50/60 Hz). 60 Hz for the 290AX/EX, which
are rated 60 Hz only; Hammond sells 290xEX versions for 50 Hz.

**Default `reg` = 0.08.** Rod Elliott, *Transformers Part 4*,
<https://sound-au.com/articles/xfmr4.htm>, tabulates about 15 % at 20 VA, 13 % at
50 VA and 10 % at 120 VA for 230 V units. The Hammond 1182 series lists 7.3–7.7 % for
120–225 VA toroids.

**Bias tap rating `Ib` = 10 mA.** An estimate; a fixed-bias supply draws a few mA. It
only sets the leakage share of the bias segment.

## Bench results

Run `python3 bench_mains-transformer.py` with the shell sandbox off. It exits 1 on any
failure. It checks every preset against its sheet (no-load voltages, no-load current,
every DCR, the rated voltages under a resistive rated load), the series-primary
connection, the `reg` and `xlk` parametrisation, saturation (inrush, a 60 Hz part on
50 Hz, over-voltage), a full-wave CT tube rectifier and a ±rail bridge, and the demo's
pin order through `tools/ltspice/asc2net.py`.

```
-- presets: no-load voltages and no-load current vs Hammond sheet (soft start, 1 s)
PT_370AX N.L.V. HV (V)                                                                   got      519.05  want       520.1  tol 0.01r       ok
PT_370AX N.L.V. HVhalf (V)                                                               got      259.52  want       260.1  tol 0.01r       ok
PT_370AX N.L.V. BIAS (V)                                                                 got      49.959  want       50.06  tol 0.01r       ok
PT_370AX N.L.V. H (V)                                                                    got      6.9988  want       7.013  tol 0.01r       ok
PT_370AX no-load current (A)                                                             got    0.079839  want        0.08  tol 0.05r       ok
PT_370CX N.L.V. HV (V)                                                                   got      607.74  want       608.8  tol 0.01r       ok
PT_370CX N.L.V. HVhalf (V)                                                               got      303.87  want       304.4  tol 0.01r       ok
PT_370CX N.L.V. BIAS (V)                                                                 got      49.913  want          50  tol 0.01r       ok
PT_370CX N.L.V. H (V)                                                                    got      6.9649  want       6.977  tol 0.01r       ok
PT_370CX N.L.V. A (V)                                                                    got      6.9649  want       6.977  tol 0.01r       ok
PT_370CX no-load current (A)                                                             got    0.076867  want       0.077  tol 0.05r       ok
PT_370FX N.L.V. HV (V)                                                                   got      585.57  want       586.3  tol 0.01r       ok
PT_370FX N.L.V. HVhalf (V)                                                               got      292.78  want       293.2  tol 0.01r       ok
PT_370FX N.L.V. BIAS (V)                                                                 got      50.067  want       50.13  tol 0.01r       ok
PT_370FX N.L.V. H (V)                                                                    got      6.8265  want       6.835  tol 0.01r       ok
PT_370FX N.L.V. A (V)                                                                    got      5.3094  want       5.316  tol 0.01r       ok
PT_370FX no-load current (A)                                                             got     0.13184  want       0.132  tol 0.05r       ok
PT_290AX N.L.V. HV (V)                                                                   got      700.95  want       702.3  tol 0.01r       ok
PT_290AX N.L.V. HVhalf (V)                                                               got      350.47  want       351.2  tol 0.01r       ok
PT_290AX N.L.V. H (V)                                                                    got      6.8278  want       6.841  tol 0.01r       ok
PT_290AX N.L.V. A (V)                                                                    got      5.4056  want       5.416  tol 0.01r       ok
PT_290AX no-load current (A)                                                             got      0.1837  want       0.184  tol 0.05r       ok
PT_290EX N.L.V. HV (V)                                                                   got      684.46  want       686.2  tol 0.01r       ok
PT_290EX N.L.V. HVhalf (V)                                                               got      342.23  want       343.1  tol 0.01r       ok
PT_290EX N.L.V. BIAS (V)                                                                 got       55.07  want       55.21  tol 0.01r       ok
PT_290EX N.L.V. H (V)                                                                    got      6.7438  want       6.761  tol 0.01r       ok
PT_290EX no-load current (A)                                                             got      0.6984  want         0.7  tol 0.05r       ok
PT_1182N18 N.L.V. SA (V)                                                                 got      19.383  want       19.39  tol 0.01r       ok
PT_1182N18 N.L.V. SB (V)                                                                 got      19.383  want       19.39  tol 0.01r       ok
PT_1182N18 no-load current [Iex estimate 46 mA] (A)                                      got    0.045985  want         nan  tol info        
PT_370AX HV at rated 0.058 A, resistive (V)                                              got         482  want         480  tol 0.05r       ok
PT_370AX H at rated 2.5 A, resistive (V)                                                 got      6.3811  want         6.3  tol 0.05r       ok
PT_370CX HV at rated 0.075 A, resistive (V)                                              got      558.45  want         550  tol 0.05r       ok
PT_370CX H at rated 2.5 A, resistive (V)                                                 got      6.4295  want         6.3  tol 0.05r       ok
PT_370CX A at rated 0.6 A, resistive (V)                                                 got      6.4481  want         6.3  tol 0.05r       ok
PT_370FX HV at rated 0.173 A, resistive (V)                                              got      552.51  want         550  tol 0.05r       ok
PT_370FX H at rated 5 A, resistive (V)                                                   got      6.3872  want         6.3  tol 0.05r       ok
PT_370FX A at rated 3 A, resistive (V)                                                   got      4.9881  want           5  tol 0.05r       ok
PT_290AX HV at rated 0.1 A, resistive (V)                                                got       653.5  want         650  tol 0.05r       ok
PT_290AX H at rated 2.25 A, resistive (V)                                                got      6.3905  want         6.3  tol 0.05r       ok
PT_290AX A at rated 3 A, resistive (V)                                                   got      4.9825  want           5  tol 0.05r       ok
PT_290EX HV at rated 0.275 A, resistive (V)                                              got      661.35  want         660  tol 0.05r       ok
PT_290EX H at rated 4 A, resistive (V)                                                   got      6.4595  want         6.4  tol 0.05r       ok
PT_1182N18 SA at rated 4.44 A, resistive (V)                                             got      18.131  want          18  tol 0.05r       ok
PT_1182N18 SB at rated 4.44 A, resistive (V)                                             got      18.131  want          18  tol 0.05r       ok
PT_1182N18 regulation, NLV 19.39 V vs model at 4.44 A (%) [sheet table 7.7]              got      6.9437  want         7.7  tol info        
PT_1182N18 regulation within 2 points of the published 7.7 %                             got      6.9437  want         7.7  tol [5.7,9.7]   ok
-- presets: DC resistance vs sheet (.op, 10 mA through each winding)
PT_370AX Rp (primaries in parallel)                                                      got       10.18  want       10.18  tol 0.002r      ok
PT_370AX DCR HV                                                                          got       333.2  want       333.2  tol 0.002r      ok
PT_370AX DCR H                                                                           got     0.15001  want        0.15  tol 0.002r      ok
PT_370CX Rp (primaries in parallel)                                                      got      7.5336  want      7.5333  tol 0.002r      ok
PT_370CX DCR HV                                                                          got       361.3  want       361.3  tol 0.002r      ok
PT_370CX DCR H                                                                           got     0.11202  want       0.112  tol 0.002r      ok
PT_370CX DCR A                                                                           got     0.43502  want       0.435  tol 0.002r      ok
PT_370FX Rp (primaries in parallel)                                                      got      2.3575  want      2.3573  tol 0.002r      ok
PT_370FX DCR HV                                                                          got         106  want         106  tol 0.002r      ok
PT_370FX DCR H                                                                           got    0.053009  want       0.053  tol 0.002r      ok
PT_370FX DCR A                                                                           got    0.063007  want       0.063  tol 0.002r      ok
PT_290AX Rp (primaries in parallel)                                                      got      3.9271  want       3.927  tol 0.002r      ok
PT_290AX DCR HV                                                                          got       277.1  want       277.1  tol 0.002r      ok
PT_290AX DCR H                                                                           got     0.10801  want       0.108  tol 0.002r      ok
PT_290AX DCR A                                                                           got    0.091005  want       0.091  tol 0.002r      ok
PT_290EX Rp (primaries in parallel)                                                      got       1.291  want       1.291  tol 0.002r      ok
PT_290EX DCR HV                                                                          got       35.64  want       35.64  tol 0.002r      ok
PT_290EX DCR H                                                                           got    0.038002  want       0.038  tol 0.002r      ok
PT_1182N18 Rp (primaries in parallel)                                                    got      2.5501  want        2.55  tol 0.002r      ok
PT_1182N18 DCR SA                                                                        got     0.14002  want        0.14  tol 0.002r      ok
PT_1182N18 DCR SB                                                                        got     0.14002  want        0.14  tol 0.002r      ok
-- presets: dual primary in series (pri=2, 240 V): same secondary voltages
PT_370AX pri=2 at 240 V: N.L.V. HV (V)                                                   got      519.04  want       520.1  tol 0.01r       ok
PT_370AX pri=2 at 240 V: no-load current = Iex/2 (A)                                     got    0.039919  want        0.04  tol 0.05r       ok
-- generic: regulation from reg, leakage from xlk (pt_ss, 230 V 50 Hz, 2 x 18 V 4.44 A)
pt_ss reg=0.05: (V_NL - V_FL)/V_FL                                                       got    0.050258  want        0.05  tol 0.008       ok
pt_ss reg=0.1: (V_NL - V_FL)/V_FL                                                        got     0.10053  want         0.1  tol 0.013       ok
pt_ss xlk=0.01: leakage seen at the primary, one secondary shorted (mH)                  got      15.802  want      15.802  tol 0.02r       ok
-- saturation: inrush, 50 Hz on a 60 Hz part, over-voltage
PT_370FX inrush peak, switch-on at a zero crossing (A)                                   got       28.49  want         nan  tol info        
PT_370FX inrush peak / no-load peak (>> 1; < Vpk/Rp limit)                               got      152.62  want      202.82  tol [20,385.649] ok
PT_370FX soft start: peak current / no-load peak                                         got     0.99876  want        1.25  tol [0.5,2]     ok
no-load current 290EX 120 V 50 Hz (A)                                                    got      1.3597  want         nan  tol info        
no-load current 290EX 120 V 60 Hz (A)                                                    got      0.6984  want         nan  tol info        
no-load current 370FX 132 V 60 Hz (A)                                                    got     0.14502  want         nan  tol info        
no-load current 370FX 150 V 60 Hz (A)                                                    got       0.165  want         nan  tol info        
290EX no-load current 50 Hz / 60 Hz (linear core would give 1.2)                         got      1.9469  want         5.6  tol [1.2,10]    ok
370FX no-load current 150 V / 132 V (saturation: >> 150/132)                             got      11.799  want       50.75  tol [1.5,100]   ok
-- rectifier convergence (.tran)
370FX + FW CT + 47 uF + 2.2k: B+ (V)                                                     got      361.94  want         nan  tol info        
  ripple p-p (V)                                                                         got      19.543  want         nan  tol info        
370FX FW CT: B+ between 0.8 x and 1.0 x the no-load half-winding peak (V)                got      361.94  want      373.18  tol [331.718,414.647] ok
370FX FW CT: load current near the rated 173 mA (A)                                      got     0.16452  want       0.165  tol [0.13,0.2]  ok
1182N18 bridge +-rails, 2 A each: V+ (V)                                                 got      23.294  want         nan  tol info        
1182N18 bridge +-rails, 2 A each: V- (V)                                                 got     -23.294  want         nan  tol info        
1182N18 +rail between 0.8 x and 1.0 x the no-load peak (V)                               got      23.294  want      24.679  tol [21.9373,27.4216] ok
1182N18 rails symmetric (V+ + V-)                                                        got  6.6862e-12  want           0  tol 0.2         ok
-- demo_mains-transformer.asc netlisted by asc2net = hand netlist
demo mean v(bplus) = hand netlist                                                        got      361.71  want      361.71  tol 0.001r      ok
demo mean v(bias) = hand netlist                                                         got    -0.87848  want    -0.87848  tol 0.001r      ok

81/81 checks passed
```

Two notes on reading the rated-load rows:

- **Rated-load voltages.** Hammond rates the HV winding for a DC load through a
  rectifier; the bench uses a resistor of V_rated/I_rated. Agreement is +0.2 to +1.5 %
  on the HV windings, −0.4 to +2.4 % on the heater and auxiliary windings, and +0.7 %
  on the toroid.
- **60 Hz part on 50 Hz.** The 290EX's no-load current nearly doubles, from 0.70 A to
  1.36 A. That is a real warning for these parts on European mains.

## What it does not model

- **One core.** There is no leakage between individual secondaries, so cross-regulation
  between the heater and the HV winding is only through the shared primary.
- **Near-sinusoidal magnetising current at rated voltage.** Real small transformers
  already run slightly saturated: ESP measured 42 mA at 240 V against 7.3 mA at 120 V
  on a 300 VA toroid, so their no-load current is peaky. The model's rms matches Iex,
  but not the waveform.
- **No hysteresis or remanence.** Worst-case inrush, which depends on the remanent flux,
  is therefore underestimated.
- **No shield or interwinding capacitance.** The Hammond 370 series has a shield lead
  (GRY) that is not modelled.
- **DCR at 20 °C,** with no copper heating and no thermal model.
- **The 290AX's 550 V CT taps** are not brought out.

## Files and demo

- `mains-transformer.sub`: the subckts and presets.
- `make_symbols.py`: writes the `.asy` symbols and `demo_mains-transformer.asc`.
- `bench_mains-transformer.py`: the bench.

The demo is a Hammond 370FX on 120 V 60 Hz with a soft start, feeding a full-wave CT
rectifier (generic diode model `DREC`, defined in the schematic) into 47 µF and 2.2 kΩ
(about 165 mA). The heater is loaded with 5 A, and the bias tap feeds 100 kΩ.

## Sources of inspiration

- The measured-parameter mains transformer (DCR, ratio, L from resonance): Robert
  Loos, `sources/loosweb-relay/raw/downloads/xfrm1p1s.lib` and
  `sources/loosweb-relay/raw/pages/en/xfrm.html`.
- The Ampeg power transformer as coupled inductors:
  `sources/suusi-tubes/extracted/SuusiTubes_V1/PT8930077.net`.
- The Fender power-supply examples: `sources/robrobinette/raw/Fixed_Bias.asc`,
  `Universal_HT_Tap_Bias.asc`.
- Ideal windings on a core node: `Winding_LCR` in
  `sources/ltwiki/extracted/lib/lib/sub/Transformers.lib`.

No text was copied from these sources.
