# electrolytic-cap — aluminium electrolytic capacitors

An aluminium electrolytic capacitor with its datasheet imperfections:
- an ESR that falls with frequency, from the 120 Hz value (tan δ) to the electrolyte resistance
  at high frequency;
- ESL and self-resonance;
- leakage current;
- dielectric absorption;
- ESR rising at low temperature.

Uses: the reservoir and decoupling capacitors of valve-amp HT supplies (supply sag and ripple),
and the filter, coupling and bypass capacitors of pedals and solid-state amps.

Files:
- `ecap.sub`: `ecap` and 5 presets;
- `make_symbols.py`: writes 6 `.asy` and `demo_ecap.asc`;
- `bench_ecap.py`;
- this README.

## Pins and parameters

Pins: **P N**, positive and negative (polarised). Symbol: a straight + plate and a curved −
plate, P at (16,16), N at (16,112).

| param | meaning | default (UVR 47 µF 450 V) |
|---|---|---|
| `C` | capacitance at 120 Hz (series-equivalent, as an LCR meter reads it) | 47u |
| `Vr` | rated voltage | 450 |
| `tand` | loss tangent at 120 Hz, 20 °C (datasheet maximum) | 0.25 |
| `Rs` | electrolyte/contact resistance = ESR at high frequency | 2.47 |
| `ESL` | series inductance | 20n |
| `Ilk` | DC leakage at Vr | 946u |
| `kDA` | dielectric-absorption capacitance, fraction of C | 0.03 |
| `Temp` | temperature, °C (scales Rs) | 20 |
| `kT` | activation temperature of Rs, K | 1926 |

| preset | part | C, Vr | tan δ (120 Hz) | Rs | Ilk |
|---|---|---|---|---|---|
| `UPW1V102MHD` | Nichicon UPW 12.5×25, low-Z 105 °C | 1000 µF 35 V | 0.12 | 27.9 mΩ | 1050 µA |
| `UPW1H471MHD` | Nichicon UPW 12.5×20 | 470 µF 50 V | 0.10 | 59.3 mΩ | 705 µA |
| `UVR2W470MHD` | Nichicon UVR 18×40, general 85 °C | 47 µF 450 V | 0.25 | 2.47 Ω | 946 µA |
| `381LX101M450H022` | CDE 381LX snap-in 22×30 | 100 µF 450 V | 0.150 | 0.702 Ω | 636 µA |
| `381LX471M450A052` | CDE 381LX snap-in 35×50 | 470 µF 450 V | 0.1251 | 0.1215 Ω | 1379 µA |

Every preset takes `Temp`.

## Model

    P — ESL — Rs(Temp) — e — [ C0 ∥ oxide-loss ladder ∥ DA ladder ∥ leakage ] — N

- **Loss split.** tan δ at 120 Hz = ωC·ESR (the Nichicon/CDE definition). It is divided between
  Rs, the frequency-independent electrolyte resistance, and a dielectric loss
  D0 = tan δ − ω₁₂₀·C·Rs.
- **Constant-loss ladder.** D0 is realised as four series R–C branches with time constants
  10 µs, 100 µs, 1 ms and 10 ms, each Ck = (D0/0.682)·C. A ladder with one branch per decade
  has a loss tangent of 0.682·Ck/C.
  - The ESR therefore falls from tan δ/(ωC) at 120 Hz towards Rs above about 20 kHz, and rises
    below 120 Hz as 1/f.
- **C0.** It is set so that the series-equivalent capacitance at 120 Hz is C.
- **Dielectric absorption.** Three more branches, 1 s, 10 s and 100 s, each kDA·C/3.
- **Leakage.** I = Ilk·(e^(4.6 V/Vr) − 1)/(e^4.6 − 1) for V ≥ 0; 10 % of Ilk at Vr/2.
- **Temperature.** Rs(T) = Rs·exp(kT·(1/T − 1/293.15 K)).

**No A-devices**: R, L, C and one B-source.

## Provenance

**Nichicon UPW catalogue**, CAT.8100N
(<https://www.nichicon.co.jp/english/series_items/catalog_pdf/e-upw.pdf>):
- p.1:
  - tan δ max at 120 Hz: 0.12 at 35 V, 0.10 at 50 V;
  - leakage ≤ 0.03CV µA after 1 min;
  - Z(−55 °C)/Z(+20 °C) at 120 Hz ≤ 0.65–0.85 of the stated ratios;
- p.2 rows:

  | part | case | Z at 100 kHz, 20 °C / −10 °C | leakage |
  |---|---|---|---|
  | UPW1V102MHD, 1000 µF 35 V | 12.5×25 | 0.030 / 0.060 Ω | 1050 µA |
  | UPW1H471MHD, 470 µF 50 V | 12.5×20 | 0.060 / 0.12 Ω | 705 µA |

- Rs is derived from Z(100 kHz) = |Rs + j(ωL − 1/ωC)| with ESL = 20 nH.
- **kT = 1926 K is fitted** so that UPW1V102MHD reads 0.060 Ω at −10 °C. UPW1H471MHD at −10 °C is
  then a prediction (checked).

**Nichicon UVR catalogue** (<https://www.nichicon.co.jp/english/series_items/catalog_pdf/e-uvr.pdf>):
- tan δ 0.25 at 350–450 V;
- leakage for 160–450 V, CV > 1000: 0.04CV + 100 µA (1 min), so 946 µA for 47 µF 450 V (the row
  UVR2W470MHD, 18×40);
- Z(−25 °C)/Z(+20 °C) ≤ 15 at 450 V.
- **UVR gives no high-frequency impedance.** Rs = 0.35 × ESR(120 Hz) is an **estimate**, from the
  ESR(20 kHz)/ESR(120 Hz) ratio of the CDE 381LX 450 V parts below (0.35–0.36 for 56, 100 and
  470 µF).

**Cornell Dubilier Type 381LX/383LX catalogue** (<https://www.cde.com/resources/catalogs/381-383.pdf>):
- p.1: leakage ≤ 3√(CV) µA (5 min); Z(−20 °C)/Z(+25 °C) at 120 Hz ≤ 3 for 150–450 V;
- p.10, 450 V rows:
  - 381LX101M450H022 (100 µF, 22×30): max ESR 1.99 Ω at 120 Hz, 0.71 Ω at 20 kHz;
  - 381LX471M450A052 (470 µF, 35×50): 0.353 Ω / 0.123 Ω.
- tan δ = ω·C·ESR120. Rs is solved so that the model's ESR at 20 kHz is the table value.

**Cornell Dubilier "Aluminum Electrolytic Capacitor Application Guide"** (copy at
<https://www.ielogical.com/assets/M-125/ElectroAppGUIDE_CDE.pdf>):
- p.5: capacitance drops at high frequency (the distributed RC of the etch tunnels);
- p.6: ESR "decreases monotonically with increasing frequency" (checked); Rs is dominated by
  electrolyte viscosity, so it rises in the cold;
- p.6: ESL is typically 10–30 nH for radial types, 20–50 nH for screw-terminal, up to 200 nH for
  axial. **20 nH is used for all presets** (radial and two-pin snap-in; estimate).
- p.10: dielectric absorption allows "up to 10% recovery". **kDA = 0.03 is an estimate**; the
  bench's standard rebound test gives 1.2 %.

**Leakage–voltage law.** The exponent (10 % of the leakage at half voltage) is an **assumption**:
the guide's "Typical Initial DCL Versus Voltage" figure was not digitised. Ilk is set to the
datasheet limit, so the model is a worst-case part; typical parts leak far less.

## Limits (not modelled)

- **Datasheet maxima.** tan δ, Z and ESR are maxima, so the model is a worst-case-ESR part.
  Typical parts have less ESR and leakage.
- **Capacitance versus frequency.** A constant loss D0 from 16 Hz to 16 kHz implies, by
  Kramers–Kronig, that the capacitance falls with frequency: the model reads about 0.7·C at
  20 kHz when tan δ is set to the datasheet maximum.
  - The direction is right (CDE guide p.5); the amount is probably too large for low-voltage
    parts.
  - It hardly matters in audio power supplies, where Xc at 20 kHz is negligible.
  - Self-resonance moves up accordingly: 193 kHz instead of 113 kHz for 100 µF/20 nH.
- **Reverse bias.** The model is not valid below 0 V; no reverse conduction is modelled.
- Capacitance change with temperature; ripple self-heating; ageing (ESR rises, capacitance
  falls).
- The time dependence of leakage: reforming, and lower leakage after long polarisation.
- Surge voltage.
- Only Rs depends on temperature.

## Bench results

`python3 bench_ecap.py` (LTspice 17.2.4, sandbox off): **32/32 checks pass**, exit 0.

| check | model | datasheet |
|---|---|---|
| C (series-equivalent) at 120 Hz, 5 presets | 1000.5 / 470.1 / 47.11 / 100.05 / 470.2 µF | 1000 / 470 / 47 / 100 / 470 (±2 %) |
| ESR at 120 Hz, 5 presets | 0.1626 / 0.2874 / 7.245 / 2.023 / 0.3585 Ω | 0.1592 / 0.2822 / 7.055 / 1.99 / 0.353 (±3 %) |
| \|Z\| at 100 kHz: UPW 1000/35, 470/50 | 0.02973 / 0.05993 Ω | 0.030 / 0.060 |
| ESR at 20 kHz: 381LX 100 µF, 470 µF | 0.7163 / 0.1237 Ω | 0.71 / 0.123 |
| UPW1H471MHD \|Z\| at 100 kHz, −10 °C (prediction) | 0.1258 Ω | 0.12 (±6 %) |
| ESR falls monotonically from 20 Hz to 1 MHz, 5 presets | yes | CDE guide p.6 |
| Z(−25)/Z(20) at 120 Hz, UVR 450 V | 1.065 | ≤ 15 |
| Z(−20)/Z(25) at 120 Hz, 381LX | 1.020 | ≤ 3 |
| \|Z\| minimum at self-resonance (381LX 100 µF) | 0.7024 Ω | Rs = 0.702 |
| leakage at Vr, 5 presets | 1050 / 705 / 946 / 636 / 1379 µA | ≤ 1050 / 705 / 946 / 636 / 1379 |
| DA rebound (60 s at 450 V, 1 s short, 60 s open) | 1.19 % | > 0 and ≤ 10 % (CDE guide) |
| demo HT ripple (100 µF, 100 mA, 60 Hz full wave) | 6.74 V p-p | ≤ I/(2fC) = 8.33 and ≥ 0.7 of it |

Notes:
- UPW1V102MHD at −10 °C reads 0.0599 Ω, the point kT is fitted to.
- The demo HT is 391.7 V mean, with charging pulses of 0.61 A peak.

## Demo

`demo_ecap.asc` is a valve-amp HT supply:
- 300-0-300 V RMS, 60 Hz, 50 Ω per half, two diodes (full wave, as with a valve rectifier);
- a 381LX 100 µF 450 V reservoir and a 100 mA load;
- it settles at 392 V with 6.7 V p-p ripple. The ESR adds the 0.6 A charging pulses × about
  2 Ω to the ripple.

The sources are ground-referenced: a floating source into a bridge made LTspice crawl.

Netlist it with `python3 tools/ltspice/asc2net.py components/electrolytic-cap/demo_ecap.asc`.
