# choke — power-supply filter chokes with DC-current saturation

`choke.sub` models a gapped-core filter choke (DC reactor) as used in tube amp
supplies, choke-input or CLC, and in solid-state supplies. It has:

- the DC resistance;
- an incremental inductance that falls with DC current;
- the self-capacitance, which sets the self-resonance;
- a small core loss.

The presets reproduce eight Hammond chokes from their sheets.

## Subckt and pins

| subckt | pins | parameters (defaults) |
|---|---|---|
| `choke` | A B | `L`=5 H, `Idc`=0.2 A, `S`=1.3, `Rdc`=65 Ω, `Cp`=100 pF, `Qc`=20, `fq`=120 Hz |
| `CH_159R`, `CH_159S`, `CH_159T`, `CH_159V`, `CH_159ZJ`, `CH_193H`, `CH_193J`, `CH_193M` | A B | `S`, `Qc`, `Cp` (preset defaults) |

The choke is symmetric, so the pin order doesn't matter. The symbols (`make_symbols.py`)
show a coil with core bars, with A on top at (16,16) and B at the bottom at (16,112).

| name | meaning |
|---|---|
| `L` | incremental inductance at the rated DC current. This is what makers publish: Hammond's sheets say "Inductances measured at rated D.C. current". |
| `Idc` | rated DC current |
| `S` | swing: inductance at zero current ÷ `L` |
| `Rdc` | DC resistance |
| `Cp` | self-capacitance across the terminals |
| `Qc`, `fq` | core loss, as a resistor Rc = Qc·2π·fq·L across the inductance (fq = the ripple frequency) |

## Equations

The inductance is flux-controlled: i(λ) = Ia·sinh(λ/λs), where λ = ∫v dt. This gives a
closed-form incremental inductance as a function of current:

**L(i) = L0/√(1 + (i/Ia)²)**, with L0 = S·L, Ia = Idc/√(S² − 1) and λs = Ia·L0.

So:

- L(0) = S·L;
- L(Idc) = L exactly;
- above Idc the inductance falls towards L0·Ia/|i|. The flux grows only
  logarithmically, which is a soft saturation.

The sinh argument is continued linearly beyond ±40 (C1-continuous), so it cannot
overflow. The flux integrator bleeds with τ = 10⁵ s, so `.op` is defined. The
self-resonance is ≈ 1/(2π√(L(i)·Cp)).

## Presets and provenance

The Hammond part sheets are at `https://www.hammfg.com/files/parts/pdf/<PART>.pdf`
(fetched 2026-09-14). The 193 series catalogue,
<https://www.hammfg.com/electronics/transformers/choke/193.pdf>, lists the 193 parts and
states: tolerance ±15 % on L and R; "Inductances measured at rated D.C. current";
"Units will exhibit less inductance at slightly higher currents or more at lower
currents."

| preset | L @ Idc (ds) | Idc (ds) | DCR (ds) | max V DC | Cp | notes |
|---|---|---|---|---|---|---|
| `CH_159R` | 6 H | 200 mA | 150 Ω | 500 | 100 p est | open bracket |
| `CH_159S` | 4 H (@ 30 V 60 Hz) | 225 mA | 60.60 Ω | 500 | 100 p est | |
| `CH_159T` | 2.5 H (@ 100 V 60 Hz) | 300 mA | 40.17 Ω | 500 | 100 p est | |
| `CH_159V` | 1.5 H | 500 mA | 27 Ω | 500 | 100 p est | |
| `CH_159ZJ` | 10 mH | 5 A | 0.160 Ω | – | **27.6 p** from the sheet's self-resonant frequency, 302.90 kHz: Cp = 1/((2πf)²·L) | solid-state supplies; sheet: \|Z\| 3.77/7.54 Ω at 60/120 Hz |
| `CH_193H` | 5 H (@ 30 V 60 Hz) | 200 mA | 65.0 Ω | 600 | 100 p est | enclosed |
| `CH_193J` | 10 H (@ 50 V 60 Hz) | 200 mA | 79.0 Ω | 600 | 100 p est | the 193 catalogue lists 82 Ω for 193J and 79 Ω for the potted 193JP; the part sheet's 79.0 Ω is used |
| `CH_193M` | 10 H (@ 30 V 60 Hz) | 300 mA | 63.0 Ω | 800 | 100 p est | |

### Estimates

- **Swing `S` = 1.3.** Hammond publishes only L at rated current and the qualitative
  note above. No published inductance-versus-current curve for these chokes was found:
  Aiken's "Chokes Explained" (<https://www.aikenamps.com/index.php/chokes-explained>)
  is qualitative. For a gapped core, L(0)/L(Idc) is the fraction of ampere-turns the
  steel takes at the design flux, and it rises as the design approaches the knee.
  1.3 is a middle-of-the-road guess. Set `S` from a measurement when you have one.
- **`Cp` = 100 pF** (except the 159ZJ). An estimate. It puts the self-resonance of a
  5–10 H choke at 5–7 kHz, far above the 100/120 Hz ripple, so it matters only for
  high-frequency hash.
- **`Qc` = 20 at 120 Hz.** An estimate. Core loss is minor next to the DCR (a 5 H
  choke's Rc is 75 kΩ).

## Bench results

Run `python3 bench_choke.py` with the shell sandbox off. It exits 1 on any failure.
It checks:

- **Against the sheets:** DCR, L at rated DC current (60 Hz small signal with DC
  bias), and the 159ZJ self-resonance.
- **Against the L(i) law:** at 0, Idc/2 and 2·Idc.
- **A choke-input filter against textbook formulas:** DC = 2Vpk/π − I·Rdc, and 120 Hz
  ripple = (4/3π)·Vpk through the LC divider with L(Idc).
- **Convergence:** 5× rated current, and a CLC supply with real diodes from switch-on.
- **The demo's pin order,** via `tools/ltspice/asc2net.py`.

```
-- presets: DCR (.op, 10 mA) and L at rated DC current (60 Hz small signal) vs sheet
CH_159R DCR (ohm)                                                                     got         150  want         150  tol 0.001r      ok
CH_159S DCR (ohm)                                                                     got        60.6  want        60.6  tol 0.001r      ok
CH_159T DCR (ohm)                                                                     got       40.17  want       40.17  tol 0.001r      ok
CH_159V DCR (ohm)                                                                     got          27  want          27  tol 0.001r      ok
CH_159ZJ DCR (ohm)                                                                    got        0.16  want        0.16  tol 0.001r      ok
CH_193H DCR (ohm)                                                                     got          65  want          65  tol 0.001r      ok
CH_193J DCR (ohm)                                                                     got          79  want          79  tol 0.001r      ok
CH_193M DCR (ohm)                                                                     got          63  want          63  tol 0.001r      ok
CH_159R L at rated Idc (H) [sheet]                                                    got      5.9968  want           6  tol 0.01r       ok
CH_159S L at rated Idc (H) [sheet]                                                    got      3.9977  want           4  tol 0.01r       ok
CH_159T L at rated Idc (H) [sheet]                                                    got      2.4985  want         2.5  tol 0.01r       ok
CH_159V L at rated Idc (H) [sheet]                                                    got      1.4991  want         1.5  tol 0.01r       ok
CH_159ZJ L at rated Idc (H) [sheet]                                                   got   0.0099938  want        0.01  tol 0.01r       ok
CH_193H L at rated Idc (H) [sheet]                                                    got      4.9972  want           5  tol 0.01r       ok
CH_193J L at rated Idc (H) [sheet]                                                    got      9.9952  want          10  tol 0.01r       ok
CH_193M L at rated Idc (H) [sheet]                                                    got      9.9952  want          10  tol 0.01r       ok
CH_159R L at zero DC (H) [law, S=1.3]                                                 got      7.7926  want         7.8  tol 0.01r       ok
CH_159S L at zero DC (H) [law, S=1.3]                                                 got      5.1949  want         5.2  tol 0.01r       ok
CH_159T L at zero DC (H) [law, S=1.3]                                                 got      3.2467  want        3.25  tol 0.01r       ok
CH_159V L at zero DC (H) [law, S=1.3]                                                 got       1.948  want        1.95  tol 0.01r       ok
CH_159ZJ L at zero DC (H) [law, S=1.3]                                                got    0.012986  want       0.013  tol 0.01r       ok
CH_193H L at zero DC (H) [law, S=1.3]                                                 got      6.4937  want         6.5  tol 0.01r       ok
CH_193J L at zero DC (H) [law, S=1.3]                                                 got      12.989  want          13  tol 0.01r       ok
CH_193M L at zero DC (H) [law, S=1.3]                                                 got      12.989  want          13  tol 0.01r       ok
CH_159R L at Idc/2 (H) [law, S=1.3]                                                   got      7.1977  want      7.2034  tol 0.01r       ok
CH_159S L at Idc/2 (H) [law, S=1.3]                                                   got      4.7983  want      4.8023  tol 0.01r       ok
CH_159T L at Idc/2 (H) [law, S=1.3]                                                   got      2.9988  want      3.0014  tol 0.01r       ok
CH_159V L at Idc/2 (H) [law, S=1.3]                                                   got      1.7993  want      1.8009  tol 0.01r       ok
CH_159ZJ L at Idc/2 (H) [law, S=1.3]                                                  got    0.011995  want    0.012006  tol 0.01r       ok
CH_193H L at Idc/2 (H) [law, S=1.3]                                                   got      5.9979  want      6.0028  tol 0.01r       ok
CH_193J L at Idc/2 (H) [law, S=1.3]                                                   got      11.997  want      12.006  tol 0.01r       ok
CH_193M L at Idc/2 (H) [law, S=1.3]                                                   got      11.997  want      12.006  tol 0.01r       ok
CH_159R L at 2 x Idc (H) [law, S=1.3]                                                 got      4.0216  want      4.0225  tol 0.01r       ok
CH_159S L at 2 x Idc (H) [law, S=1.3]                                                 got       2.681  want      2.6817  tol 0.01r       ok
CH_159T L at 2 x Idc (H) [law, S=1.3]                                                 got      1.6756  want      1.6761  tol 0.01r       ok
CH_159V L at 2 x Idc (H) [law, S=1.3]                                                 got      1.0054  want      1.0056  tol 0.01r       ok
CH_159ZJ L at 2 x Idc (H) [law, S=1.3]                                                got   0.0067024  want   0.0067042  tol 0.01r       ok
CH_193H L at 2 x Idc (H) [law, S=1.3]                                                 got      3.3513  want      3.3521  tol 0.01r       ok
CH_193J L at 2 x Idc (H) [law, S=1.3]                                                 got       6.703  want      6.7042  tol 0.01r       ok
CH_193M L at 2 x Idc (H) [law, S=1.3]                                                 got       6.703  want      6.7042  tol 0.01r       ok
-- 159ZJ self-resonance at rated current (sheet: 302.90 kHz)
CH_159ZJ |Z| peak frequency at 5 A (kHz)                                              got      302.67  want       302.9  tol 0.01r       ok
-- choke-input filter: 350 V rms full-wave (ideal), CH_193H, 40 uF, 1.5k
V_DC = 2 Vpk/pi - Idc*Rdc (V)                                                         got      302.52  want         302  tol 0.005r      ok
120 Hz ripple at the output (V pk)                                                    got      1.8692  want      1.8698  tol 0.05r       ok
  L(Idc) used by the formula (H)                                                      got      4.9829  want           5  tol info        
  ripple if L stayed at L(0) = 6.5 H (V pk)                                           got      1.4305  want         nan  tol info        
-- convergence: overload and capacitor-input start-up surge
CH_193H at 65 V DC: I = V/Rdc (A)                                                     got           1  want           1  tol 0.01r       ok
CLC 22u-193H-22u, 2.2k: B+ (V)                                                        got      450.54  want         nan  tol info        
CLC B+ between the choke-input level and the peak (V)                                 got      450.54  want      405.06  tol [315.127,495] ok
CLC peak choke current at switch-on (A)                                               got      1.1206  want         nan  tol info        
-- demo_choke.asc netlisted by asc2net = hand netlist
demo mean V(out) = hand netlist                                                       got      301.34  want      301.34  tol 0.001r      ok

46/46 checks passed
```

The ripple rows show why the current dependence matters. With the 193H at its 200 mA
operating point the 120 Hz ripple is 1.87 V peak. A linear choke at the zero-current
value, 6.5 H, would give 1.43 V.

## What it does not model

- **One smooth saturation law.** Real gapped chokes keep L flatter below the knee and
  lose it faster above; `S` is an estimate.
- **No hysteresis, and no dependence of L on the AC swing.** Hammond measures with
  30–100 V AC; the model's L is the small-signal value at the DC point.
- **Lumped self-capacitance, DCR at 20 °C.**
- **A swinging choke** (deliberately high S, e.g. 20→5 H) can be approximated by a large
  `S`, but its exact law differs.

## Files

- `choke.sub`: the subckt and presets.
- `make_symbols.py`: writes the `.asy` files and `demo_choke.asc`.
- `bench_choke.py`: the bench.

The demo is a choke-input supply: 350-0-350 V 60 Hz, full-wave with the generic diode
`DREC`, then CH_193H, 40 µF and 1.5 kΩ, for about 200 mA and 300 V.

## Sources of inspiration

- The flux-integrator inductor, shared with `components/output-transformer`: idea from
  `Winding_LCR`/`core` in `sources/ltwiki/extracted/lib/lib/sub/Transformers.lib`.
- LTspice nonlinear-core examples: `sources/bordodynov/extracted/lib/sub/Nonlintransformer1.sub`
  (`NLIND1`).

No text was copied from these sources.
