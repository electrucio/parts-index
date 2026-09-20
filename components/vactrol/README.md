# vactrol — LED/LDR analog optocouplers

A vactrol is an LED shining on a CdS cell in a sealed package. It is used in optical tremolos,
compressors, channel switching and synth VCAs. The model chain is:

    LED diode → light e = (I_LED / 1 mA)^m → CdS cell (ldr_cell)

The cell uses the carrier-balance model of `components/ldr/`:
- **static:** the power law with a series part, and the dark floor;
- **dynamics:** fast attack, a power-law decay that slows as R rises, and faster response at high
  drive;
- **memory:** light history.

Presets: PerkinElmer VTL5C1/3/4, Xvive VTL5C6 and Silonex NSL-32SR2, fitted to their datasheet
tables and curves.

Files:
- `vactrol.sub`
- `make_symbols.py`: writes 6 `.asy` and `demo_vactrol.asc`, and copies the `ldr_cell` core from
  `../ldr/ldr.sub`
- `bench_vactrol.py`
- this README

## Pins and parameters

Pins, in the physical order (LED end, cell end): **A K C1 C2** = LED anode, LED cathode, cell,
cell. Symbol: LED on the left (A at (0,16), K at (0,112)), cell on the right (C1 at (96,16),
C2 at (96,112)).

| param | meaning | default (VTL5C1) |
|---|---|---|
| `Rref` | cell R − Rs at 1 mA, dark adapted | 19.85k |
| `m` | light ∝ I^m; statically R − Rs ∝ I^−(m·γ) | 1.987 |
| `gamma` | CdS recombination exponent (decay shape) | 0.8299 |
| `Rs` | series part of the cell (flattens the curve at high current) | 154.7 |
| `Rdark` | ultimate dark resistance | 500Meg |
| `tau`, `ka` | recombination time scale, attack factor | 3.896m, 0.1394 |
| `kLH`, `hist`, `thist`, `Iadapt` | light-history ratio, state at t = 0 (0 = dark adapted = datasheet), time constant, half-adaptation current | 1.5, 0, 3600, 4m |
| `Cc` | cell capacitance | 5p |
| `Is N RsLED Cj BV` | LED diode | PerkinElmer fit |

The equations are in `components/ldr/README.md`. The vactrol calls `ldr_cell` with Eref = 1, so
its "light" is (I_LED/1 mA)^m.

Why m > 1? Every vactrol datasheet has a slope R(0.5 mA)/R(5 mA) above 10, which is steeper than a
CdS γ ≤ 1 alone. The LED's efficiency rising at low current supplies the rest. Statics fix only
m·γ; the decay shape fixes γ, so m follows.

**No A-devices.** Everything is B-sources, capacitors and one diode.

## Presets

| preset | Rref | m | γ | Rs | Rdark | τ | ka | kLH | LED |
|---|---|---|---|---|---|---|---|---|---|
| `VTL5C1` | 19.85k | 1.987 | 0.8299 | 154.7 | 500 MΩ | 3.896 ms | 0.1394 | 1.5 | PerkinElmer |
| `VTL5C3` | 30.58k | 1.249 | 0.6476 | 1m | 32.09 MΩ | 7.635 ms | 0.4896 | 1.2 | PerkinElmer |
| `VTL5C4` | 1.135k | 1.700 | 0.7499 | 64.7 | 22.67 GΩ | 46.48 ms | 0.3236 | 1.7 | PerkinElmer |
| `VTL5C6` | 30k | 1.902 | 0.5259 | 1m | 100 MΩ | 1.917 ms | 0.034 | 1.2 | Xvive |
| `NSL32SR2` | 236.0 | 1.9385 | 0.4477 | 23.3 | 50 MΩ | 56.73 µs | 2.046e-4 | 1.2 | Xvive (estimate) |

## Provenance

All datasheets are in `datasheets/opto/`. "p." is the PDF page; the printed page number is given
where there is one.

**Fitting procedure** (the equations of `ldr.sub`, integrated in Python with a Nelder–Mead fit):
1. **Statics.** Rs, Rref and m·γ are least-squares fits in log R to the on-resistance points.
2. **Decay shape.** γ and τ are fitted to the turn-off crossing times. Where there are three or
   more crossings, Rdark is fitted too. The fit is constrained so that R 10 s after switch-off is
   at least the datasheet minimum.
3. **Attack.** ka is fitted so that the turn-on to 63 % of final conductance matches the datasheet.

Readings off log plots are good to roughly ±20–30 %. The bench therefore allows a factor of 1.6
on curve-read times, and applies datasheet maximums and minimums strictly.

**VTL5C1**
- Sources:
  - `VTL5C1_perkinelmer.pdf` (PerkinElmer "Low Cost Axial Vactrols VTL5C1, 5C2", printed pp. 43–44);
  - `VTL5C1_xvive.pdf` (Xvive5C1-R specification, 2019, fetched from electricdruid.net).
- **On resistance (p.1, typical, dark adapted).** 20 kΩ at 1 mA, 600 Ω at 10 mA, 200 Ω at 40 mA.
- **Other p.1 figures.**
  - off resistance at 10 s: 50 MΩ min;
  - turn-on to 63 % of final RON: 2.5 ms typ;
  - turn-off to 100 kΩ: 35 ms max;
  - LED forward voltage: 1.65 V typ at 20 mA;
  - cell capacitance: 5 pF.
- **Turn-off curve (p.2, 40 mA).** 10 kΩ at about 11 ms, 100 kΩ at about 21 ms.
- **Xvive's clone sheet disagrees with itself.** Its table says 35 ms to 100 kΩ, but its curve takes
  about 700 ms. Its on-resistance is also different (25 kΩ at 0.5 mA). The preset follows the
  PerkinElmer original.

**VTL5C3 and VTL5C4**
- Sources:
  - `VTL5C3_perkinelmer.pdf` (printed pp. 45–46, from the qsl.net mirror; PDF pp. 1–2 of the
    compilation);
  - `VTL5C3_xvive.pdf` (the Xvive VTL5C3/C4 clone sheet).
- **VTL5C3 on-resistance units typo.** Both tables print "30 kΩ, 5 Ω, 1.5 Ω" at 1/10/40 mA. The
  curve on p.2 reads 30 kΩ, ≈ 5 kΩ and ≈ 1.5 kΩ, and the quoted slope of 20 needs kΩ, so kΩ is used.
- **VTL5C3, other p.1 figures.** Off resistance at 10 s: 10 MΩ min. Turn-on 2.5 ms typ. Turn-off to
  100 kΩ: 35 ms max.
- **VTL5C3 turn-off curve (p.2, 40 mA).** 10 kΩ at about 6 ms, 100 kΩ at about 16 ms, 1 MΩ at about
  110 ms.
- **VTL5C4, p.1.** 1.2 kΩ / 125 Ω / 75 Ω at 1/10/40 mA. Off resistance at 10 s: 400 MΩ min.
  Turn-on 6.0 ms. Turn-off to 100 kΩ: 1.5 s max.
- **VTL5C4 turn-off curve (p.2, 40 mA, read on a 400-dpi zoom).** 1 kΩ at about 68 ms, 10 kΩ at
  about 340 ms, 100 kΩ at about 760 ms.
- **LED fit.** Is = 4.463e-20, N = 1.539, Rs = 1.62 Ω, fitted to the "Input characteristics" curve
  (p.2): 1.50 V at 1 mA, 1.65 V at 20 mA, 1.71 V at 40 mA. The same curve is printed for C1–C4.

**VTL5C6**
- Source: `VTL5C6_xvive.pdf` (Xvive 5C6 specification, 2021, from the Aion FX mirror).
- **On resistance (p.1).** 40–80 kΩ at 0.5 mA (60 kΩ used). 6.0 kΩ at 5 mA; that is the only
  figure given, so it is used as typical.
- **Times (p.1).** TR 3.5 ms at 16 mA. TF 50 ms typ to 1 MΩ at 16 mA.
- **LED fit.** N = 3.923, Is = 5.097e-11, fitted to Xvive's LED curve (p.2): 1.70 / 1.95 / 2.07 V at
  1 / 10 / 40 mA. The model gives 1.985 V at 16 mA, against 2.0 V max.
- **Problems with the Xvive sheet.** Its p.2 resistance curve is a copy of the VTL5C3 drawing, so it
  is not used. Its "ROFF 400 kΩ" at 10 s cannot coexist with "TF to 1 MΩ in 50 ms". The dark value
  is therefore PerkinElmer's comparison chart: VTL5C6 dark resistance 100 MΩ, slope 16.7, 88 dB
  (*Analog Optical Isolators* catalogue p.41 = PDF p.15, `VACTROL_catalog_perkinelmer.pdf`).

**NSL-32SR2**
- Source: `NSL-32SR2_silonex.pdf` (Silonex QF-84, 104057 REV 3; PDF p.4 of the qsl.net
  compilation).
- **"Photocell Resistance vs. LED Current" curve, read on a 400-dpi zoom:**

  | LED current | 0.1 mA | 1 mA | 10 mA | 20 mA | 40 mA |
  |---|---|---|---|---|---|
  | resistance | 1800 Ω | 247 Ω | 58.3 Ω | 41.1 Ω | 31.9 Ω |

- **Table.** RON 40 Ω max at 20 mA and 140 Ω at 1 mA. ROFF 1 MΩ min, 5 MΩ typ at 10 s. TR 5 ms
  typ, TF 80 ms typ to 100 kΩ, both at 20 mA. VF 2.5 V max.
- **The table disagrees with its own curve** at 1 mA (140 vs 247 Ω) and slightly at 20 mA
  (41.1 Ω, above the 40 Ω max). The fit follows the curve, and the bench reports the table values
  as notes.
- **Estimates.** The Silonex LED is not characterised, so the Xvive LED fit is used (VF = 2.0 V at
  20 mA ≤ 2.5 V max). kLH = 1.2 (material not stated). Rdark = 10 × the 10-second typical value.

**Estimates common to all presets:**
- **kLH** is PerkinElmer's RLH/RDH at 1 fc for the material type (catalogue p.29 = PDF p.3): type 1
  → 1.5, type 3 and Ø → 1.2, type 4 → 1.7. The ratio really depends on the light level (1.05–5.5);
  one value is used.
- **thist = 1 h and Iadapt = 4 mA.** Adaptation takes hours (catalogue p.29). The light-adapt
  condition of the curves is 24 h at 40 mA, and half adaptation is put at a tenth of that.
- **Rdark for VTL5C1 and NSL-32SR2** is 10 × the 10-second value. The catalogue p.41 notes say the
  ultimate value is "many times greater". For VTL5C3 and VTL5C4 it is fitted to the decay curve.

**Inspiration**, no text copied:
- Bordodynov's `Vtl5c2.sub` and `NSL-32SR3.sub`, with a diode-steered RC "light" node
  (`sources/bordodynov/extracted/lib/sub/`);
- Sennewald's `Led_Ldr.lib` (`sources/ltwiki/extracted/lib/lib/sub/`);
- J.C. Maillet's measured static NSL-32SR3 (`sources/viva-analog/`);
- the owner's guide p.7: a VTL5C3 is a light-dependent resistance with dynamics and memory, not a
  PC817 phototransistor; fit light/dark resistance and times to the part.

## Limits (not modelled)

- Temperature coefficient: 1 %/°C Xvive, 0.7 %/°C Silonex.
- The LED-to-cell coupling capacitance (0.5 pF).
- Unit-to-unit spread: PerkinElmer quotes 25 % matching.
- Cell voltage and power ratings.
- The level dependence of the light-history ratio.
- Below 1 mA the PerkinElmer notes warn that units "may have substantially higher resistance than
  shown".

## Bench results

`python3 bench_vactrol.py` (LTspice 17, sandbox off): **51/51 checks pass**, exit 0.

| check | model | datasheet |
|---|---|---|
| core identical to `components/ldr/ldr.sub` | yes | |
| VTL5C1 R at 1 / 10 / 40 mA | 20.01k / 600.1 / 200.0 Ω | 20k / 600 / 200 |
| VTL5C3 R at 1 / 10 / 40 mA | 30.58k / 4.749k / 1.547k Ω | 30k / 5k / 1.5k (±6 %) |
| VTL5C4 R at 1 / 10 / 40 mA | 1.200k / 125.0 / 75.0 Ω | 1.2k / 125 / 75 |
| VTL5C6 R at 0.5 / 5 mA | 60.0k / 5.998k Ω | 60k (40–80k) / 6.0k |
| NSL-32SR2 R at 0.1 / 1 / 10 / 20 / 40 mA | 1764 / 259.3 / 55.3 / 40.8 / 32.9 Ω | 1800 / 247 / 58.3 / 41.1 / 31.9 (±6 %) |
| LED VF: PerkinElmer at 20 mA / VTL5C6 at 16 mA / NSL at 20 mA | 1.650 / 1.985 / 2.008 V | 1.65 typ / 1.99 (curve, ≤ 2.0) / ≤ 2.5 |
| turn-on to 63 % conductance: C1 / C3 / C4 / C6 / NSL | 2.51 / 2.51 / 5.97 / 3.50 / 5.00 ms | 2.5 / 2.5 / 6.0 / 3.5 / 5 |
| VTL5C1 turn-off to 10k / 100k | 11.0 / 21.0 ms | 11 / 21 (curve); 100k ≤ 35 max |
| VTL5C3 turn-off to 10k / 100k / 1M | 4.9 / 24.0 / 90.9 ms | 6 / 16 / 110 (curve); 100k ≤ 35 max |
| VTL5C4 turn-off to 1k / 10k / 100k | 101.5 / 258.1 / 591.3 ms | 68 / 340 / 760 (curve); 100k ≤ 1.5 s max |
| VTL5C6 turn-off to 1 MΩ / NSL to 100 kΩ | 50.0 / 80.1 ms | 50 / 80 typ |
| R 10 s after off: C1 / C3 / C4 / C6 / NSL | 500 / 32.1 / 419 / 99.6 / 5.0 MΩ | ≥ 50 / 10 / 400 / 1 / 1 MΩ |
| light history: R(hist=1)/R(hist=0) − Rs | 1.500 | kLH (type 1) |
| reversed LED: cell stays dark | 32.1 MΩ | ≥ 30 |
| .ac \|Z\| at 10 mA vs static | 1e-3 Ω error | |
| demo: LED peak current / envelope min / max | 15.31 mA / 66.3 mV / 0.476 V | 15.27 / 66.4 (static R at the peak) / ≥ 0.3; depth 17.1 dB |

## Change notes

- **2026-09-14, second pass.**
  - **`ldr_cell` core.** The core copied from `components/ldr/ldr.sub` has its carrier-balance
    source rewritten without the ±1e6 clamp on the imbalance; the equation is unchanged (see the
    LDR README change note).
  - **VTL5C4 refit.** Refitted to its turn-off curve re-read on a 400-dpi zoom: 68 / 340 / 760 ms
    to 1k / 10k / 100k, previously 40 / 250 / 650 ms. New γ 0.7499, m 1.700, Rdark 22.67 GΩ,
    τ 46.48 ms, ka 0.3236.
  - **NSL-32SR2 refit.** Refitted to its curve re-read on a 400-dpi zoom: 247 / 58.3 / 41.1 /
    31.9 Ω at 1 / 10 / 20 / 40 mA, previously 260 / 60 / 45 / 33. New Rref 236.0, m 1.9385,
    Rs 23.3, τ 56.73 µs, ka 2.046e-4. The table's 40 Ω maximum at 20 mA is below its own typical
    curve (41.1 Ω), so the bench reports it as a note.
  - **Bench fixes.**
    - The kLH check now uses the sign of the sensed current correctly.
    - Turn-off crossing times are measured from the instant the LED current reaches zero.
  - Bench: 51/51.

## Demo

`demo_vactrol.asc` is an optical tremolo:
- A 5 Hz LFO (0–5 V) drives the LED of a `VTL5C3` through 220 Ω.
- The cell shunts a 440 Hz signal after 22 kΩ.
- On each LFO peak the output falls to the static-resistance level. Between peaks it recovers along
  the slow decay: the characteristic "choppy" shape of an LDR tremolo.

Netlist it with `python3 tools/ltspice/asc2net.py components/vactrol/demo_vactrol.asc`.
