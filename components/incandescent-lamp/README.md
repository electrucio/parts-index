# incandescent-lamp — small tungsten-filament lamps

A small incandescent lamp as an electro-thermal resistor. Uses in amps and pedals:
- the amplitude stabiliser of Wien-bridge oscillators (#327, 28 V/40 mA, run barely warm);
- lamp/LDR optos and tremolos;
- pilot lamps (#47).

The filament temperature is a circuit node. The resistance follows the published resistivity of
tungsten, so the model gives:
- cold/hot resistance ratio about 10;
- current ∝ V^0.55–0.6 (the lamp-catalogue law);
- 10–30 ms thermal response at rated power, and seconds when barely warm (the "amplitude bounce"
  of lamp oscillators);
- inrush current of about 10× the rated current.

Files:
- `lamp.sub`: the `lamp` subckt and 4 presets;
- `make_symbols.py`: writes 5 `.asy` and `demo_lamp.asc`;
- `fit_lamp.py`: the same equations in Python, fits `fc` and derives the estimated cold
  resistances; run it to see the numbers;
- `bench_lamp.py`;
- this README.

## Pins and parameters

Pins: **A B**, the filament (non-polar). Symbol: a circle with a cross, A at (16,16), B at
(16,112), the same footprint as the LDR.

| param | meaning | default (#327) |
|---|---|---|
| `Vr`, `Ir` | rated (design) voltage and current | 28, 40m |
| `Rc` | cold resistance at `Ta`, measured | 65 |
| `fc` | fraction of the rated power lost by conduction to the leads (the rest is radiated) | 0.0166 |
| `Ta` | ambient temperature, °C | 25 |
| `kC` | heat-capacity multiplier (1 = straight-wire estimate) | 1 |
| `T0` | filament temperature forced at t = 0, K (0 = normal operating point) | 0 |

Presets (every preset also takes `T0`):

| preset | Vr, Ir | Rc | fc | status |
|---|---|---|---|---|
| `LAMP_327` | 28 V, 40 mA | 65 Ω | 0.0166 | Rc measured, fc fitted to a measured point |
| `LAMP_47` | 6.3 V, 150 mA | 3.9 Ω | 0.0166 | Rc and fc estimated |
| `LAMP_12V40` | 12 V, 40 mA (grain-of-wheat) | 27.86 Ω | 0.0166 | Rc and fc estimated |
| `LAMP_6V60` | 6 V, 60 mA | 10 Ω | 0.0621 | Rc published ("about 10 Ω"), fc fitted to a measured point |

## Model

T is the filament temperature in kelvin (internal node `t`):

    Cth(T) dT/dt = V²/R(T) − Gc (T − Ta) − A σ (ε(T) T⁴ − ε(Ta) Ta⁴)
    R(T) = Rc · ρ(T)/ρ(Ta)

- **ρ(T)** is the resistivity of tungsten (White & Minges polynomial). Its ratio to room
  temperature is what matters: 4.4 at 1000 K, 10 at 2000 K and 16 at 3000 K, which is close to
  R ∝ T^1.2.
- **Calibration** comes from the rating and the cold resistance, computed in `.param` inside the
  subckt:
  - the hot temperature Th solves ρ(Th)/ρ(Ta) = (Vr/Ir)/Rc (Newton);
  - the conduction conductance is Gc = fc·Vr·Ir/(Th − Ta);
  - the radiating area A carries the rest of the rated power at Th.
- **Heat capacity.** A straight round wire with resistance Vr/Ir at Th and area A has diameter
  d = (4ρ(Th)A/(π²Vr/Ir))^(1/3). Its volume is A·d/4, so
  Cth = kC · A·d/4 · 19250 kg/m³ · cp(T)/0.18384 kg/mol.
  - For the #327 this gives d = 12.4 µm, L = 146 mm (coiled in the real lamp), 59 µJ/K at Th.
- **ε(T)**, the total hemispherical emissivity, is taken ∝ T.

Everything else is a consequence and is checked by the bench:
- the I–V law;
- the response time;
- the inrush current;
- the low-frequency small-signal impedance (the slope dV/dI) versus the high-frequency one (V/I).

**No A-devices.** The model is B-sources, a capacitor, and `.func` definitions inside the subckt
(LTspice evaluates them in `.param`; tested with `.lib`).

## Provenance

**Tungsten properties**, from P. Tolias, "Analytical expressions for thermophysical properties
of solid and liquid tungsten…", *Nucl. Mater. Energy* 13 (2017),
[arXiv:1703.06302](https://arxiv.org/pdf/1703.06302):
- resistivity: the White–Minges 1997 fit of Desai's 1984 recommended values, 100–3600 K, 0.2 % rms
  (PDF p.3);
- heat capacity cp: the White–Minges fit, 300–3400 K (PDF p.5);
- density 19.25 g/cm³ at room temperature (PDF p.11); thermal expansion is neglected;
- molar mass 183.84 g/mol.

**Emissivity.** ε = 0.0992 at 1000 K, measured on electropolished tungsten: D. P. Verret and
K. G. Ramanathan, *JOSA* 68, 1167 (1978), abstract
(<https://opg.optica.org/josa/abstract.cfm?uri=josa-68-9-1167>).
- The proportionality to T is an **assumption**. It is the free-electron (Hagen–Rubens) trend for
  ρ ∝ T.
- It gives ε ≈ 0.20 at 2000 K. Commonly quoted values are around 0.25 there, and ε flattens above
  about 2500 K.
- ε matters through the filament area, and so through the heat capacity: see Limits.

**#327**
- Rating 28 V, 0.04 A, 0.34 MSCP, 4.27 lm, 4000 h: JKL Lamps #327 page
  (<https://www.jkllamps.com/327>).
- Rc = 65 Ω: R. Elliott, "Sine Wave Oscillators" §4.2
  (<https://sound-au.com/articles/sinewave.htm>): cold resistance "65 ohms (estimated)", "69 ohms"
  with the ohmmeter's current, 700 Ω at full temperature.
- **fc = 0.0166** is fitted (`fit_lamp.py`) to his operating point: 0.5 V at 4.5 mA (111 Ω).
- **Independent points** from the same section, used as checks:
  - 1.39 V at 7.4 mA (188 Ω) with RF = 375 Ω, and 4.16 V RMS out;
  - "dull red glow appearing above 13mA".

**#47**
- Rating 6.3 V, 0.15 A, T-3¼ BA9s, 0.5 MSCP, C-2R filament, 3000 h:
  <https://www.miniaturebulb.com/47n.html>.
- No cold resistance is published. **Estimate:** Rc is set so the filament runs at the #327's
  temperature (Rh/Rc = 10.77).
- Its efficacy (4π·0.5 = 6.3 lm from 0.945 W, i.e. 6.7 lm/W, against 3.8 lm/W for the #327) says
  its filament is hotter. So the true Rc is probably lower and the true ratio higher.
- fc is taken from the #327 (**estimate**).

**12 V 40 mA grain-of-wheat**
- Rating only (the generic grain-of-wheat lamp of opto builds).
- Rc and fc as for the #47 (**estimates**).

**6 V 60 mA** (R. Elliott, Project 179, <https://sound-au.com/project179.htm>)
- Rc = 10 Ω: "about 10 ohms or one tenth of the hot value"; 100 Ω hot at 6 V/60 mA.
- fc = 0.0621 is fitted to his operating point, 0.5 V → 30 Ω, 17 mA.
- With the #327's fc it would read 35.3 Ω. That 18 % is the error to expect when fc is carried from
  one lamp type to another, as it is for `LAMP_47` and `LAMP_12V40`.

**Lamp-catalogue law** (independent check): current ≈ Ir·(V/Vr)^0.55 and candlepower ∝ V^3.5.
Source: J. Dunn, "Incandescent lamps and service life", EDN, 2016-10-10
(<https://www.edn.com/incandescent-lamps-and-service-life/>).

**Visible glow**: the Draper point, 798 K (<https://en.wikipedia.org/wiki/Draper_point>).

**Response time** (qualitative): "the lamp takes a few (to tens of) milliseconds to respond"
(sound-au Project 179).

## Limits (not modelled)

- **Heat capacity: uncertain to about ±30 %.** It rests on the ε(T) assumption and on a
  straight-wire geometry. Coil self-shadowing makes the real radiating area smaller than the wire
  surface, so the real mass is larger for the same power. `kC` scales it.
  - The response time is checked only against "a few to tens of ms".
- **Vacuum lamps only.** Gas-filled lamps (larger, halogen) lose heat by convection; fc then means
  something else.
- **Light output is not an output of the subckt.** For a lamp/LDR opto, drive the LDR's light
  node with a B-source computing lux ∝ (V/Vr)^3.4 from the lamp voltage. The EDN law is 3.5 for
  candlepower. The lamp's own time constant then shapes the attack.
- Resistance of the leads and supports; coil inductance; ageing (the filament thins and R rises);
  the tungsten-halogen cycle; burnout.
- `LAMP_47` and `LAMP_12V40` are estimates (see Provenance).

## Bench results

`python3 bench_lamp.py` (LTspice 17.2.4, sandbox off, about 3 min): **25/25 checks pass**, exit 0.

| check | model | reference |
|---|---|---|
| cold R at 1 mV: #327 / #47 / 12V40 / 6V60 | 65.0 / 3.90 / 27.86 / 10.0 Ω | 65 (Elliott) / est. / est. / 10 (p179) |
| current at rated V: #327 / #47 / 12V40 / 6V60 | 40.0 / 150.0 / 40.0 / 60.0 mA | ratings |
| current at Vr/2: #327 / #47 / 12V40 / 6V60 | 26.38 / 98.92 / 26.38 / 40.08 mA | Ir·0.5^0.55 = 27.32 / 102.5 / 27.32 / 40.98 (±5 %, EDN) |
| exponent of I ∝ V^n between Vr/2 and Vr | 0.601 (0.582 for 6V60) | 0.55 "approximately" |
| #327 hot/cold ratio | 10.77 | 8–14 ("about 10": 700/65, "one tenth") |
| #327 R at 7.4 mA | 196.3 Ω | 187.8 Ω (1.39 V, Elliott; ±8 %) |
| #327 filament at 13 mA | 1075 K | ≥ 798 K (glow seen above 13 mA) |
| #327 at 10 mA | 906 K | (Elliott: dark in room light; 798 K is the faint glow seen in darkness) |
| #327 response to a −10 % current step at rated current (63 %) | 32.3 ms | 2–50 ms ("a few to tens of ms") |
| #327 switch-on peak current / after 0.3 s | 430.6 / 40.0 mA | 28/65 = 430.8 / 40 |
| .ac \|Z\| at 10 kHz and at 1 mHz (14 V bias) | 530.7 / 889.5 Ω | V/I = 530.7; dV/dI = 889.5 |
| demo (Wien bridge, RF = 375): frequency / output / lamp | 211.5 Hz / 3.96 V / 1.32 V RMS | 211.6 / 4.16 / 1.39 (Elliott; ±10 %) |

Fit points shown as notes, not counted as checks:
- #327 at 4.5 mA: 111.2 Ω;
- 6V60 at 0.5 V: 30.0 Ω.

## Demo

`demo_lamp.asc` is a lamp-stabilised Wien-bridge oscillator at 212 Hz: RF = 375 Ω, a `LAMP_327`,
1.6 kΩ/470 nF, and a behavioural op-amp (gain 10⁵, 10 Hz pole, soft ±13 V rails).
- It starts with a warm lamp (`T0=700`) and 2 V on the Wien network, and settles at 3.96 V RMS
  within the 6 s run.
- **Why the warm start.** From a cold lamp (65 Ω, loop gain 6.8) the output hits the rails. The
  lamp overheats, the oscillation dies, the lamp cools for about a second, and it bursts again.
  - That is the "amplitude bounce" of lamp oscillators (Elliott reports "considerable amplitude
    bounce" with low feedback resistances).
  - The model's own AGC loop at this operating point is lightly damped: about 5 Hz, ζ ≈ 0.02.
    That damping comes from the lamp's slow cooling when barely warm (τ ≈ 0.9 s at 720 K).
- Netlist it with `python3 tools/ltspice/asc2net.py components/incandescent-lamp/demo_lamp.asc`.
  The `.save` keeps the raw file small.
