# ntc-thermistor — NTC thermistors with self-heating

An NTC thermistor with its own temperature as a circuit node. It covers:
- **inrush-current limiters** in the mains input of valve and solid-state amps: cold at
  switch-on, a fraction of an ohm once hot;
- **small NTCs** for bias compensation and sensing.

The model is a B/β (+ curvature) R/T law with a first-order thermal circuit, using the
datasheet's dissipation constant and heat capacity.

Files:
- `ntc.sub`: `ntc` and 3 presets;
- `make_symbols.py`: writes 4 `.asy` and `demo_ntc.asc`;
- `bench_ntc.py`;
- this README.

## Pins and parameters

Pins: **A B** (non-polar). Symbol: a resistor box crossed by a bent line and marked "−t", A at
(16,16), B at (16,112).

| param | meaning | default (SL10 10003) |
|---|---|---|
| `R25` | zero-power resistance at 25 °C | 10 |
| `B` | B25/100 (β), K | 3058 |
| `D` | curvature of ln R vs 1/T, K² (0 = pure β) | 0 |
| `dth` | dissipation constant in still air, W/K | 11m |
| `Cth` | heat capacity, J/K (cooling time constant = Cth/dth) | 0.33 |
| `Ta` | ambient temperature, °C | 25 |
| `Rs` | lead resistance | 1m |

| preset | part | R25 | B | D | dth | Cth (τ) |
|---|---|---|---|---|---|---|
| `SL10_10003` | Ametherm SL10 10003, 10 Ω 3 A inrush limiter | 10 | 3058 | 0 | 11 mW/K | 0.33 J/K (30 s) |
| `B57236S0100` | TDK/EPCOS S236, 10 Ω 3.5 A inrush limiter | 10 | 2817 | 0 | 10 mW/K | 0.7 J/K (70 s) |
| `B57164K0103` | TDK/EPCOS K164, 10 kΩ disc (R/T 2904) | 10k | 4300 | −1.939e5 | 7.5 mW/K | 0.15 J/K (20 s) |

Every preset takes `Ta`.

## Model

    Cth dT/dt = V²/R(T) − dth (T − Ta)        (T in kelvin, internal node t)
    R(T) = Rs + R25 exp(B x + D x (x − x100)),  x = 1/T − 1/298.15,  x100 = 1/373.15 − 1/298.15

- **The curvature term.** It vanishes at 25 °C and 100 °C, so `B` stays the datasheet's B25/100.
  It bends ln R versus 1/T the way real material curves bend. A pure β law is 13 % off the K164
  table at −20 °C; with D fitted it is 2.2 % off.
- **Conduction.** The thermistor is `V/R(T)`; the power heats the thermal node.
- **.op solves the self-heated state** at DC current. For inrush, start the source from 0 (a
  PWL, or a behavioural source that switches on); a DC source makes the `.op` pre-charge the
  load capacitor.

**No A-devices.**

## Provenance

**Ametherm SL10 10003**, datasheet page <https://www.ametherm.com/datasheets/sl1010003.html>
(rev. a, 11/11/2008):
- R25 = 10 Ω ± 20 %; Imax = 3 A (to 25 °C);
- R at 100 % Imax = 0.26 Ω; at 50 % = 0.57 Ω;
- body temperature at Imax = 151 °C;
- dissipation constant 11 mW/°C;
- material type C; max energy 17 J.
- **Thermal time constant is printed "30 mw/s"**, an obvious typo. It is read as **30 s**
  (assumption), giving Cth = 0.33 J/K.

**Ametherm "Resistance Temperature Curve"** (<https://www.ametherm.com/inrush-current/resistance-temperature-curve/>):
- material C β = 3058 K;
- multipliers R(T)/R25 = 2.500 / 0.454 / 0.1258 / 0.0463 at 0 / 50 / 100 / 150 °C (checked).
- **The SL10 numbers are not mutually consistent.** With 11 mW/K and β = 3058 K the body at 3 A
  comes out at about 200 °C and R = 0.217 Ω, against the printed 151 °C and 0.26 Ω. A body
  temperature measured on the coating is probably lower than the ceramic's, and the dissipation
  constant rises with temperature. The model keeps the datasheet's constants: R at 3 A is 16 %
  low, R at 1.5 A is 0.5 % off.

**TDK (EPCOS) S236, B57236S0\*\*\*M0\*\*** (datasheet 2021-04-22, v. a,
<https://www.tdk-electronics.tdk.com/inf/50/db/icl_16/S236.pdf>):
- p.2: dth ≈ 10 mW/K, τth ≈ 70 s, Cth ≈ 700 mJ/K, Pmax 2.1 W;
- p.4 Table 1: R25 = 10 Ω, Imax1 = 3.5 A, Rmin = 0.180 Ω (at Imax, 25 °C);
- p.7: R/T graph; p.9: R versus current graph.
- **The datasheet has no B value.** B = 2817 K is **fitted** so that the self-heated R at 3.5 A
  with 10 mW/K is Rmin = 0.180 Ω.
- **Independent check:** the p.9 curve read at 1.2 / 1.5 / 2.0 / 2.5 / 3.0 A gives 0.749 / 0.556
  / 0.379 / 0.281 / 0.220 Ω. The reading is by pixel position on a 300-dpi rendering, with the
  log axis calibrated on the "1,0" and "0,1" labels; good to about ±5 %.

**TDK (EPCOS) K164, B57164K** (datasheet March 2013,
<https://hades.mech.northwestern.edu/images/2/27/B57164K.pdf>, the TDK original at
tdk-electronics.tdk.com/inf/50/db/ntc/NTC_Leaded_disks_K164.pdf):
- p.2: P25 = 450 mW, dth ≈ 7.5 mW/K, τc ≈ 20 s, Cth ≈ 150 mJ/K;
- p.3: 10 kΩ = B57164K0103, R/T characteristic 2904, B25/100 = 4300 K ± 3 %;
- p.9: the 2904 table from −55 to 155 °C.
- D = −1.939e5 K² is a least-squares fit to that table with B held at 4300 K. The residual is
  within 2.3 % from −40 to 155 °C, and 3.6 % at −55 °C.

## Limits (not modelled)

- Tolerance spread: R25 ± 5–20 %, B ± 3 %. Use `.step` on `R25`.
- **The dissipation constant is a still-air, small-ΔT value**, constant in the model. Real ones
  rise with temperature (radiation) and depend on mounting and air flow, which is why the SL10's
  hot resistance comes out low.
- Maximum energy and capacitance ratings are not enforced; the demo reports the energy absorbed.
- Ageing; the device's own capacitance and inductance.

## Bench results

`python3 bench_ntc.py` (LTspice 17.2.4, sandbox off): **26/26 checks pass**, exit 0.

| check | model | datasheet |
|---|---|---|
| K164 R(T)/R25 at −40 / −20 / 0 / 50 °C | 41.64 / 11.21 / 3.531 / 0.3346 | 41.94 / 11.47 / 3.556 / 0.3336 (±2.5 %) |
| K164 R(T)/R25 at 85 / 100 / 125 / 150 °C | 0.09037 / 0.05509 / 0.02600 / 0.01328 | 0.08993 / 0.05494 / 0.02601 / 0.01332 |
| K164 B25/100 | 4300 K | 4300 K |
| SL10 R(T)/R25 at 0 / 50 / 100 / 150 °C | 2.557 / 0.4523 / 0.1274 / 0.04842 | 2.500 / 0.454 / 0.1258 / 0.0463 (±5 %) |
| SL10 R at 3 A / 1.5 A (self-heated) | 0.217 / 0.567 Ω | 0.26 / 0.57 Ω (±20 %) |
| S236 R at 1.2 / 1.5 / 2.0 / 2.5 / 3.0 A | 0.775 / 0.577 / 0.391 / 0.288 / 0.224 Ω | graph 0.749 / 0.556 / 0.379 / 0.281 / 0.220 (±10 %) |
| S236 R at 3.5 A (fit point) | 0.181 Ω | 0.180 |
| K164 dissipation constant (2 mA) | 7.50 mW/K | 7.5 |
| cooling time constant: K164 / S236 / SL10 | 20.07 / 70.31 / 30.17 s | 20 / 70 / 30 (assumed) |
| .ac \|Z\| at 1 kHz = static V/I (K164 at 2 mA) | 8171.6 Ω | 8171.6 |
| demo: first inrush peak | 17.02 A | (169.7 − Vd)/10 = 16.82 A |

Demo notes:
- The NTC absorbs 5.93 J in the first 0.3 s, against 17 J maximum recommended.
- The line current at 0.3 s is 2.01 A peak.

## Demo

`demo_ntc.asc` shows inrush limiting in a capacitor-input rectifier:
- a behavioural 120 V RMS source switches on at the crest (1 ms);
- an SL10 in the line feeds a half-wave rectifier, 470 µF and a 1 kΩ load;
- the first current peak is held to about 170 V/10 Ω, then the NTC warms and its resistance
  falls.

**The circuit is ground-referenced on purpose.** A floating source feeding a diode bridge made
LTspice take hundreds of thousands of steps per 20 ms.

Netlist it with `python3 tools/ltspice/asc2net.py components/ntc-thermistor/demo_ntc.asc`.
