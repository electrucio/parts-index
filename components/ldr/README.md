# ldr — CdS light-dependent resistor (photocell)

A CdS photoresistor with a light input node (`V(L)` = illuminance in lux). The model
covers:
- the datasheet power law R = R10·(E/10 lux)^−γ and the dark limit;
- a fast attack and a slower, level-dependent decay;
- light-history memory (dark adapted vs light adapted).

Use it in LDR/lamp optos, photo tremolos and compressors, or as the cell of a vactrol:
`components/vactrol/` carries the same core.

Files:
- `ldr.sub`: the `ldr_cell` core, the bare `ldr`, and the GL55 presets;
- `make_symbols.py`: writes 5 `.asy` and `demo_ldr.asc`;
- `bench_ldr.py`;
- this README.

## Pins

| subckt | pins |
|---|---|
| `ldr`, `GL5516`, `GL5528`, `GL5537_1`, `GL5539` | A B L — cell, cell, light (V(L) in lux) |
| `ldr_cell` (core) | A B L — light in units of `Eref` |

Drive L from any voltage: a PWL "lamp", a behavioural source computing light from a
lamp's power, or the LED of a vactrol. Symbol: A on top (16,16), B at the bottom (16,112),
L on the left (−32,64).

## Parameters (`ldr`)

| param | meaning | default |
|---|---|---|
| `R10` | resistance at 10 lux, light adapted (the GL55 test condition) | 14.14k |
| `gamma` | lg(R10/R100) | 0.6 |
| `Rdark` | ultimate dark resistance (thermal-generation floor) | 10Meg |
| `tau` | recombination time scale | 21.09m |
| `ka` | attack factor: conductance rises at ka × the natural rate | 0.8336 |
| `kLH` | light-history ratio R(light adapted)/R(dark adapted) | 1.2 |
| `hist` | adaptation at t = 0 (0 dark, 1 light) | 1 |
| `thist` | adaptation time constant, s | 3600 |
| `Eadapt` | lux of half light adaptation | 300 |
| `Cc`, `Rs` | cell capacitance, series resistance | 0, 1m |

The defaults are the `GL5528` preset.

## Model

The model is a carrier balance in the CdS film. n is the photo-carrier density normalised to the
reference light, and e = E/Eref:

    dn/dt = [ (e + eth) − n^(1/γ) ] / τ        generation − recombination
    at rest  n = (e + eth)^γ,   R = Rs + Rref / n

- **Static law.** At rest this is the power law with the datasheet's γ.
- **Dark floor.** The thermal generation `eth` sets it: Rdark = Rs + Rref·eth^−γ.
- **Level-dependent speed.** Recombination of order 1/γ > 1 makes the cell faster when bright. At
  100 lux the GL5528 rises in 8 ms, against 20 ms at 10 lux.
- **Decay.** After switch-off R grows as a power of time and keeps slowing, which is the shape of
  every datasheet decay curve, rather than an exponential.
- **State variable.** It is u = ln n, so n can never go negative:
  du/dt = k/τ · e^((1/γ−1)u) · [(e + eth)·e^(−u/γ) − 1].
- **Attack/decay asymmetry.** k = `ka` while the conductance rises and 1 while it falls.
- **Memory.** A slow state h (0 dark adapted, 1 light adapted, time constant `thist`) scales R by
  (1 + (kLH−1)h)/(1 + (kLH−1)href). `href` is the adaptation of the condition R10 refers to: 1 here
  (GL55: 2 h at 400–600 lux, then measured), 0 in the vactrols (their tables are dark adapted).

**No A-devices.** Everything is B-sources and capacitors, using `limit()`/`max()`, which are
LTspice functions (use min/max in ngspice).

## Presets and provenance

All GL55 numbers come from the "GL55 Series CdS Photoresistor Manual", 5 pp.
- Source used: the copy at
  <https://passionelectronique.fr/wp-content/uploads/datasheet-photoresistance-LDR-GL5528-CdS.pdf>.
- The document does not name its maker; the GL55 series is commonly attributed to Senba
  Optoelectronic.
- **p.1 "Types and Specifications"** lists GL5516, GL5528, GL5537-1, GL5537-2, GL5539 and GL5549,
  all with 150 V maximum and 90–100 mW.
- **p.2** gives six rows in the same order, with no type column, so the mapping by order is my
  inference. GL5528 = 10–20 kΩ agrees with how GL5528 is sold, e.g. the Handsontec GL55 guide
  gives 8–20 kΩ and 1 MΩ minimum.
- **p.2 test conditions:**
  - dark resistance is measured 10 s after the 10 lux light is shut off;
  - light resistance at 10 lux, after 2 h at 400–600 lux (light adapted);
  - γ = lg(R10/R100).

| preset | R10 (p.2 range) | γ (p.2) | dark 10 s min (p.2) | rise / decay ms (p.2) | fitted τ, ka |
|---|---|---|---|---|---|
| `GL5516` | 7.07k (5–10k) | 0.5 | 0.5 MΩ | 30 / 30 | 17.45 ms, 0.433 |
| `GL5528` | 14.14k (10–20k) | 0.6 | 1 MΩ | 20 / 30 | 21.09 ms, 0.834 |
| `GL5537_1` | 24.49k (20–30k) | 0.6 | 2 MΩ | 20 / 30 | 21.09 ms, 0.833 |
| `GL5539` | 70.71k (50–100k) | 0.8 | 5 MΩ | 20 / 30 | 26.38 ms, 1.176 |

**Estimates and interpretations:**
- **R10** is the geometric middle of the table range. The spread is the range; `.step R10` to
  explore it.
- **Rdark (ultimate)** is 10 × the 10-second value. The PerkinElmer catalogue p.41 note says the
  ultimate dark resistance is "many times greater than the value at 10 seconds". The 10-second
  values still pass the table minimum in the bench.
- **Response times.** The manual prints "Response time (ms) Increase / Decrease" without
  definitions. They are read as:
  - increase = the conductance rising from dark to 63 % of its final value at 10 lux;
  - decay = the conductance falling to 37 % after the 10 lux light is removed (R reaching R10·e).

  τ and ka are fitted to those two times; the fitter is in the scratch notes, and the equations are
  those above.
- **kLH = 1.2** is the PerkinElmer figure for type 3 / Ø materials at 1 fc ≈ 10 lux
  ("Variation of Resistance with Light History", *Analog Optical Isolators* catalogue p.29 = PDF
  p.3, `datasheets/opto/VACTROL_catalog_perkinelmer.pdf`). The GL55 manual gives nothing on light
  history.
- **thist = 1 h and Eadapt = 300 lux.** The same catalogue page says most dark adaptation occurs in
  the first eight hours, and that 24 h at about 30 fc (≈ 320 lux) reaches the light-adapted state.
  With the model's single time constant, 1 h is an estimate.

**Inspiration**, no text copied:
- the diode/RC "light state" of Bordodynov's `Vtl5c2.sub` and `NSL-32SR3.sub`
  (`sources/bordodynov/extracted/lib/sub/`);
- Sennewald's `Led_Ldr.lib` (`sources/ltwiki/extracted/lib/lib/sub/`);
- J.C. Maillet's measured static NSL-32SR3 (`sources/viva-analog/`).

This model replaces their empirical networks with a carrier balance, so one parameter set gives the
static law, the dark floor, and the level-dependent attack and decay.

## Limits (not modelled)

- Temperature coefficient: about 0.7–1 %/°C in opto datasheets.
- Spectral response: E is "lux of the lamp the cell was specified with", 2856 K standard light
  source A for the GL55.
- Voltage and power ratings (150 V, 100 mW for the GL55); resistance drift with age; noise.
- kLH's dependence on the illumination level (the catalogue table: larger at low light) is reduced
  to one ratio.

## Bench results

`python3 bench_ldr.py` (LTspice 17, sandbox off): **36/36 checks pass**, exit 0.

| check | got | want |
|---|---|---|
| static R of `ldr` at 0 / 0.1 / 1 / 10 / 100 / 1000 lux | 10.00M / 223.9k / 56.29k / 14.14k / 3.552k / 892.2 Ω | R10·(E/10 + eth)^−γ, error < 1e-3 |
| R at 10 lux: GL5516 / 5528 / 5537-1 / 5539 | 7.07 / 14.14 / 24.49 / 70.69 kΩ | inside 5–10 / 10–20 / 20–30 / 50–100 kΩ |
| γ = lg(R10/R100) | 0.500 / 0.600 / 0.600 / 0.800 | 0.5 / 0.6 / 0.6 / 0.8 |
| rise time (63 % conductance at 10 lux) | 30.00 / 20.01 / 20.01 / 20.01 ms | 30 / 20 / 20 / 20 |
| decay time (to R10·e) | 30.00 / 29.99 / 30.00 / 30.00 ms | 30 |
| R 10 s after 10 lux off | 3.35 / 9.99 / 20.0 / 50.0 MΩ | ≥ 0.5 / 1 / 2 / 5 MΩ |
| GL5528 rise at 100 lux | 7.96 ms | < 20 ms (faster when bright) |
| light history: R(hist=1)/R(hist=0) | 1.2000 | kLH = 1.2 |
| adapting cell (hist=0, thist=1 s, 5 s at 1000 lux) | 857.09 Ω | 857.09 |
| .ac \|Z\| at 10 lux, max error | 0.15 Ω | 0 |
| .step E = 10, 100 lux | 14.14k, 3.552k | |
| demo attenuator: dark / 100 lux amplitude | 0.988 / 0.261 V | 0.989 / 0.261 |
| demo: recovery at 305 ms < at 795 ms (slow decay) | 0.449 < 0.978 V | |

## Change notes

- **2026-09-14, carrier-balance source `Bu` rewritten (no change to the equation).** The rate
  used to be written exp((1/γ−1)u) · limit(imb, −1e6, 1e6), with imb = (e + eth)·e^(−u/γ) − 1.
  It is now the algebraically identical (e + eth)·e^(−u) − e^((1/γ−1)u). The old clamp on imb
  capped the attack rate of a cell that was deep in the dark (u ≪ 0, so imb ≫ 1e6) when light
  arrived: that response was slower than the equation says. imb is now used only for its sign,
  which picks the attack factor. Bench after the change: 36/36. The GL5528/5537/5539 rise times
  moved by at most 0.01 ms. The same core is copied into `components/vactrol/vactrol.sub`, whose
  bench also passes (51/51).

## Demo

`demo_ldr.asc` is a light-controlled attenuator:
- 1 kHz, 1 V into 10 kΩ, with a GL5528 to ground.
- A "lamp" (`VLUX`) gives 100 lux from 50 to 300 ms.
- The output drops within a few milliseconds when the light comes on. It recovers over hundreds of
  milliseconds after the light goes off.

Netlist it with `python3 tools/ltspice/asc2net.py components/ldr/demo_ldr.asc`.
