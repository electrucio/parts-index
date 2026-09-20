# neon-lamp — NE-2 type neon glow lamps

A two-electrode neon glow lamp. It is used in:
- relaxation oscillators: the LFO of old neon/LDR tremolos, sawtooth generators;
- mains indicators;
- simple voltage references.

The model has:
- a breakdown (striking) voltage;
- GE's glow equivalent circuit, a counter-EMF plus a dynamic resistance;
- extinction below a minimum glow current;
- the hysteresis between them;
- finite ionization and de-ionization times.

Files:
- `neon.sub`: `neon` and 3 presets;
- `make_symbols.py`: writes 4 `.asy` and `demo_neon.asc`;
- `bench_neon.py`;
- this README.

## Pins and parameters

Pins: **A K**, the two electrodes. The NE-2 is symmetric and the model conducts in both
directions. Symbol: a circle with two plates and a gas dot, A at (16,16), K at (16,112).

| param | meaning | default (NE-2) |
|---|---|---|
| `Vb` | breakdown (striking) voltage, DC | 75 |
| `Ve` | counter-EMF of the glow: maintaining voltage extrapolated to zero current | 55 |
| `Ri` | dynamic internal resistance in the normal glow | 5.5k |
| `Imin` | minimum glow current: below it the lamp goes out; extinguishing voltage Vx = Ve + Ri·Imin | 100u |
| `tion`, `toff` | ionization and extinction time constants | 5u, 20u |
| `Cp` | shunt capacitance | 0.5p |
| `Roff` | dark leakage | 100G |

| preset | lamp (CML part / old ref.) | Vb | Ve | Ri |
|---|---|---|---|---|
| `NE2` | A1A / NE-2 | 75 | 55 | 5.5k |
| `NE2E` | A9A / NE-2E | 75 | 55.5 | 4k |
| `NE2H` | C2A / NE-2H, high brightness | 110 | 60 | 2.5k |

## Model

Glowing, the lamp is GE's equivalent circuit: I = (|V| − Ve)/Ri, in the direction of V.
Dark, only `Roff` and `Cp` remain. Two internal states decide which applies.

- **Mode m (bistable).**
  - It is set when |V| > Vb, and it latches as soon as it passes 0.05, before any current
    flows. The current then cannot pull the voltage back under Vb and stall the strike: once
    started it completes, like the avalanche in a real lamp.
  - It is reset when the lamp is lit (s > 0.5) but carries less than Imin. A lamp starved
    below its minimum current goes out instead of dimming.
- **Glow s (0 to 1).** It follows the latched mode, rising with `tion` and falling with
  `toff`. The current is s·(|V| − Ve)/Ri.
- **Hysteresis.** Between Vx and Vb the mode keeps its value: a dark lamp stays dark up to Vb,
  and a lit lamp stays lit down to Vx.
- **Negative-resistance region.** The real curve's negative-resistance part, between the
  Townsend region and the normal glow, is not a static branch here. The lamp crosses it during
  the strike, in about `tion`, as the voltage collapses from Vb towards the glow line.

**No A-devices.** Everything is B-sources and capacitors.

**Start supplies from 0 V** (PWL), as real supplies do. A DC source present at t = 0 makes the
`.op` solve for a lamp already lit, or part-lit if the supply can barely sustain it.

## Provenance

**Chicago Miniature Lighting (CML), "Neon Indicator Lamps"** (1 p.,
<http://www.wjoe.com/dial_lamp_specs/ne2.pdf>):

| part (old ref.) | design current | max. breakdown |
|---|---|---|
| A1A (NE-2) | 0.6 mA | 65 VAC / 90 VDC |
| A9A (NE-2E) | 0.7 mA | 65 VAC / 90 VDC |
| C2A (NE-2H) | 1.9 mA | 95 VAC / 135 VDC |

**GE Glow Lamp Manual, 2nd ed., 1965** (text at
<https://archive.org/stream/GE_Neon_Lamps_1965/GE%20Neon%20Lamps%201965_djvu.txt>):
- **Ch. 1, Fig. 1.5**, "Average DC characteristic values for glow lamp equivalent circuit at
  rated current": A1A (with 8AB, K2A, 5AB) V0 = 55 V, Ri = 5500 Ω; A9A (with 3AD, 3AG)
  55.5 V, 4000 Ω. The lamp is "a counter E.M.F. in series with a dynamic internal resistance".
  → `Ve`, `Ri` of `NE2`, `NE2E`.
- **Ch. 1 definitions.** The extinguishing voltage lies between the minimum maintaining voltage
  and the breakdown voltage. Ionization takes microseconds; de-ionization up to 50 ms.
- **Ch. 2, Fig. 2.4.** Relaxation-oscillator period T = RC ln((V − Ve)/(V − Vf)), with Ve the
  extinguishing and Vf the firing voltage.

**W. G. Miller, *Using and Understanding Miniature Neon Lamps*, Sams 1969**
(<https://www.tiffe.de/roehren/neon.pdf>; "p." is the PDF page):
- p.7: ionization time "may be well under 50 µsec if the applied voltage is 30 percent greater
  than the breakdown voltage";
- p.8: indicator types lose about 50 mV of maintaining voltage per °C (not modelled);
- p.21: the relaxation oscillator; R must be high enough that the lamp cannot stay on;
- p.26: NE-2-class maintaining voltage 50–60 V.

**Estimates:**
- **Vb = 75 V** (NE-2, NE-2E). CML gives only maxima. 75 V sits inside the DC ranges of Miller's
  lamp tables (p.54: 66–83, 70–90 V) and under 90 V. Real lamps spread widely: use `.step`.
- **Imin = 100 µA**, `tion` = 5 µs, `toff` = 20 µs, `Cp` = 0.5 pF.
  - `tion` sits inside GE's "microseconds" and Miller's < 50 µs.
  - `toff` models only how fast the glow collapses. The slow recovery of Vb (de-ionization, up
    to 50 ms) is not modelled.
- **NE-2H: Vb = 110 V, Ve = 60 V, Ri = 2.5 kΩ.** GE's table has no C2A. These give about 65 V at
  the 1.9 mA design current, the typical value quoted in an electronics-lab.com forum thread
  (<https://www.electronics-lab.com/forums/threads/ne-2h-neon-lamp-specifications.124223/>).
  That source is weak; treat the preset as indicative.

## Limits (not modelled)

- The recovery of the breakdown voltage after extinction (de-ionization, up to 50 ms): matters
  above about 1 kHz.
- The dark effect: breakdown is higher in darkness, and radioactive-doped lamps reduce it.
- The −50 mV/°C temperature coefficient.
- The abnormal glow above the rated current.
- Ageing: Vb rises and the light falls.
- Noise and "voltage jumps" of high-brightness lamps (Miller p.10).
- Light output: to drive an LDR, use a B-source proportional to the lamp current.

## Bench results

`python3 bench_neon.py` (LTspice 17.2.4, sandbox off): **29/29 checks pass**, exit 0.

| check | model | reference |
|---|---|---|
| DC breakdown (slow ramp through 100k): NE2 / NE2E / NE2H | 74.87 / 74.85 / 109.87 V | ≤ 90 / 90 / 135 VDC (CML max) |
| glow voltage at 0.5×, 1×, 1.5× design current: NE2 | 56.65 / 58.30 / 59.95 V | 55 + 5.5k·I (GE Fig. 1.5) |
| same, NE2E | 56.90 / 58.30 / 59.70 V | 55.5 + 4k·I (GE Fig. 1.5) |
| same, NE2H (estimates) | 62.38 / 64.75 / 67.13 V | 60 + 2.5k·I |
| strikes on every half-cycle at the CML max AC breakdown (65 / 65 / 95 V RMS) | 1 / 1 / 1 per half-cycle, both polarities | 1 |
| NE2 maintaining voltage at 0.5 mA | 57.75 V | 50–60 V (Miller p.26) |
| hysteresis at 65 V via 10k: never struck / after a 100 V pulse | 0.0007 µA / 0.6452 mA | dark / (65 − 55)/15.5k |
| extinction: lit at 1.08 mA, then the supply can give only 48 µA | 0.0006 µA | out (< Imin) |
| ionization time at 1.3·Vb (to 90 % current) | 8.2 µs | < 50 µs (Miller p.7) |
| relaxation osc. 150 V, 2.2 MΩ, 0.47 µF: period | 247.95 ms | 249.11 ms (±2 %) |
| relaxation osc. 150 V, 1 MΩ, 0.1 µF: period | 26.49 ms | 26.59 ms (±2 %) |
| .ac of a dark lamp at 1 kHz | 3.1416 nS | 0.5 pF ∥ 100 GΩ |
| demo LFO period | 247.98 ms (4.03 Hz, 55.5–74.9 V) | 249.11 ms |

The reference period is GE's charge time plus the discharge of C through the glowing lamp while
the supply still feeds it: (R∥Ri)·C·ln((Vb − V∞)/(Vx − V∞)), with V∞ = (Vs·Ri + Ve·R)/(R + Ri).
GE's charge time alone is 238.4 ms and 23.1 ms: it neglects the discharge.

## Demo

`demo_neon.asc` is the neon LFO of old tremolos:
- 150 V (ramped up in 10 ms) through 2.2 MΩ charges 0.47 µF;
- the NE-2 fires at 75 V and dumps the capacitor to the extinguishing voltage;
- the result is a 4 Hz sawtooth on `SAW`, 55.5–74.9 V.

To use it as an opto, drive an LDR's light node (`components/ldr`) from the lamp current.

Netlist it with `python3 tools/ltspice/asc2net.py components/neon-lamp/demo_neon.asc`.
