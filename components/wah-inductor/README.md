# wah-inductor — wah pedal inductors (Cry Baby / Vox type)

`wah-inductor.sub` models the ~0.5 H inductor of a wah pedal:

- the inductance and the winding resistance;
- optionally, core loss (a core Q at 1 kHz) and self-capacitance.

Ten presets reproduce published LCR-meter readings of Dunlop Fasel, Cry Baby, Halo and
Mammoth inductors. The bench also builds the whole Dunlop Cry Baby GCB-95 circuit around
the inductor. It checks the sweep against ElectroSmash's published analysis and shows how
each inductor moves the peak.

## Subckt and pins

| subckt | pins (SpiceOrder) | parameters (defaults) |
|---|---|---|
| `wah_inductor` | A B | `L`=500m, `R`=17, `Qc`=0, `Cp`=0 |
| `WAH_<part>` (10 presets) | A B | `Qc`=0, `Cp`=0 |

A and B are interchangeable: the part has no polarity and no coupling. The symbol is the
LTspice inductor drawing with a core bar, with A at (16,16) and B at (16,112), the same pin
positions as the built-in `ind`. One `.asy` per subckt and per preset.

| name | meaning |
|---|---|
| `L` | inductance (small-signal, LCR-meter value) |
| `R` | winding DC resistance |
| `Qc` | core Q at 1 kHz. It adds a core-loss resistance Rc = Qc·2π·1 kHz·L across the ideal inductance. 0 = lossless core (default). |
| `Cp` | self-capacitance across A–B; 0 = not modelled (default) |

## Equations

- Z = [ jωL ‖ Rc ] + R, all in parallel with 1/(jωCp).
- Coil Q with neither Rc nor Cp: Q = 2πfL/R. For 0.5 H and 17 Ω that is 185 at 1 kHz.
- With Rc: 1/Q = R/(ωL) + ωL/Rc.

## Presets and provenance

**Source.** PedalPCB Community Forum, "Wah Inductors. No hype. Just measurements.", thread
24076, first post by Stickman393 (Nov 9, 2024),
<https://forum.pedalpcb.com/threads/wah-inductors-no-hype-just-measurements.24076/>,
fetched 2026-09-14.

**How the readings are printed.** The post lists each part as `R ohms/L mH (R ohms/L mH)`.
The author writes that the numbers in parentheses come from his Fluke 87+ and his Honeytek
LC meter; the numbers outside come from a cheaper component tester. For three cup-core
parts the tester reads 14–25 mH, which is not credible for a 0.5 H wah inductor.

**What the presets use.** L is the Honeytek LC-meter value and R the Fluke 87+ ohmmeter
value, unless the row says otherwise.

| preset | part | L mH | R Ω | L / R from | other reading as printed |
|---|---|---|---|---|---|
| WAH_RED_FASEL | Dunlop red Fasel (toroid) | 583 | 17.0 | Honeytek / Fluke | 17.5 ohms/565.2mH |
| WAH_YELLOW_FASEL | Dunlop yellow Fasel (cup core) | 620 | 13.9 | Honeytek / Fluke | 14.7 ohms/24.26mH |
| WAH_GCB95 | Dunlop Cry Baby GCB-95, stock (modern) | 645 | 17.4 | Honeytek / Fluke | 17.8 ohms/599.4mH |
| WAH_GCB95_90S | GCB-95, late 90s–early 00s (black cylinder) | 690 | 14.6 | Honeytek / Fluke | 15.1 ohms/24.85mH |
| WAH_GCB95_80S | GCB-95, 80s (Mexico) | 343 | 11.8 | Honeytek / Fluke | 12 ohms/76.78mH |
| WAH_HENDRIX | Dunlop Hendrix Cry Baby (late 90s–early 00s) | 564 | 13.7 | Honeytek / Fluke | 14.1 ohms/14.03mH |
| WAH_535Q | Dunlop Cry Baby 535Q (metal can) | 593.3 | 18.3 | tester / tester | – (only the tester reading is given) |
| WAH_HALO | Whipple Halo | 580.7 | 27.8 | tester / Fluke | Honeytek printed as "522uH" (unit typo), so the tester's L is used |
| WAH_SOUL_HALO | Sabbadius Soul Halo | 510 | 29.5 | Honeytek / Fluke | 30.3 ohms/597.8mH |
| WAH_MAMMOTH | Mammoth / SBP ME-6 | 622 | 29.4 | Honeytek / Fluke | 30.7 ohms/730.3mH |

**The generic default** of 500 mH is ElectroSmash's "500mH typ." for the Cry Baby
("between 200mH to 1H"; <https://www.electrosmash.com/crybaby-gcb-95>, read through the
mirror <https://electrosmash.mas-effects.com/crybaby-gcb-95.html>). The 17 Ω default is
the red Fasel's.

**What is not published.** None of these parts has published figures for core loss (Q vs
frequency), self-capacitance or saturation current. The same thread's later Hantek 1832C
sweeps (100 Hz–10 kHz at 648 mV) are in a linked spreadsheet that could not be read. So
`Qc` and `Cp` default to "not modelled", and no frequency dependence of L is used.

## Bench results

Run `python3 bench_wah-inductor.py` with the shell sandbox off. It exits 1 on any failure.
Rows marked "info" are shown for comparison and are not pass/fail.

It checks:

- **Presets:** R(DC) and L (Im Z/ω at 1 kHz) against the readings above.
- **Options:** the Qc and Cp options against their formulas.
- **The Cry Baby GCB-95.** The ElectroSmash part list is wired as in
  `sources/audio-effects-ltspice/raw/audio-effects-ltspice/dunlop_crybaby/dunlop_crybaby.asc`,
  with the library's preferred MPSA18 (`models/bjt/MPSA18/ltwiki-2.lib`) and MPSA13
  models. Built around the generic 500 mH inductor, it is compared with ElectroSmash's
  "sweeps up and down from 450 Hz to 1.6 kHz" and "amplified up to 18dB":
  - the heel end (VR1 wiper at the output side, Rtone = 100 k) peaks within 15 % of
    450 Hz;
  - the published 450 Hz–1.6 kHz range lies inside the circuit's reachable sweep;
  - the maximum peak gain is within ±4 dB of 18 dB (ElectroSmash states no conditions).
- **Each preset in the same circuit:** the heel peak scales as 1/√L.
- `.tran` against `.ac`.
- The demo's pin order: the demo netlisted by `tools/ltspice/asc2net.py` must match a hand
  netlist.

ElectroSmash's "750 Hz with VR1 at mid position" is shown as info. The circuit reaches
750 Hz at Rtone ≈ 24 k, not at the linear midpoint (50 k). The Dunlop pot has a special
taper whose curve is not published, so the linear midpoint is not a fair test.

Full output:

```
-- presets: R(DC) and L vs the published LCR readings (PedalPCB thread 24076)
WAH_RED_FASEL R(DC) (Fluke 87+)                                                                 got          17  want          17  tol 0.001r      ok
WAH_YELLOW_FASEL R(DC) (Fluke 87+)                                                              got        13.9  want        13.9  tol 0.001r      ok
WAH_GCB95 R(DC) (Fluke 87+)                                                                     got        17.4  want        17.4  tol 0.001r      ok
WAH_GCB95_90S R(DC) (Fluke 87+)                                                                 got        14.6  want        14.6  tol 0.001r      ok
WAH_GCB95_80S R(DC) (Fluke 87+)                                                                 got        11.8  want        11.8  tol 0.001r      ok
WAH_HENDRIX R(DC) (Fluke 87+)                                                                   got        13.7  want        13.7  tol 0.001r      ok
WAH_535Q R(DC) (tester)                                                                         got        18.3  want        18.3  tol 0.001r      ok
WAH_HALO R(DC) (Fluke 87+)                                                                      got        27.8  want        27.8  tol 0.001r      ok
WAH_SOUL_HALO R(DC) (Fluke 87+)                                                                 got        29.5  want        29.5  tol 0.001r      ok
WAH_MAMMOTH R(DC) (Fluke 87+)                                                                   got        29.4  want        29.4  tol 0.001r      ok
WAH_RED_FASEL Im(Z)/w at 1 kHz (mH) (Honeytek)                                                  got         583  want         583  tol 0.005r      ok
WAH_RED_FASEL   other meter: 17.5 ohms/565.2mH; coil Q at 1 kHz = wL/R                          got      215.48  want         nan  tol info        
WAH_YELLOW_FASEL Im(Z)/w at 1 kHz (mH) (Honeytek)                                               got         620  want         620  tol 0.005r      ok
WAH_YELLOW_FASEL   other meter: 14.7 ohms/24.26mH; coil Q at 1 kHz = wL/R                       got      280.26  want         nan  tol info        
WAH_GCB95 Im(Z)/w at 1 kHz (mH) (Honeytek)                                                      got         645  want         645  tol 0.005r      ok
WAH_GCB95   other meter: 17.8 ohms/599.4mH; coil Q at 1 kHz = wL/R                              got      232.91  want         nan  tol info        
WAH_GCB95_90S Im(Z)/w at 1 kHz (mH) (Honeytek)                                                  got         690  want         690  tol 0.005r      ok
WAH_GCB95_90S   other meter: 15.1 ohms/24.85mH; coil Q at 1 kHz = wL/R                          got      296.94  want         nan  tol info        
WAH_GCB95_80S Im(Z)/w at 1 kHz (mH) (Honeytek)                                                  got         343  want         343  tol 0.005r      ok
WAH_GCB95_80S   other meter: 12 ohms/76.78mH; coil Q at 1 kHz = wL/R                            got      182.64  want         nan  tol info        
WAH_HENDRIX Im(Z)/w at 1 kHz (mH) (Honeytek)                                                    got         564  want         564  tol 0.005r      ok
WAH_HENDRIX   other meter: 14.1 ohms/14.03mH; coil Q at 1 kHz = wL/R                            got      258.67  want         nan  tol info        
WAH_535Q Im(Z)/w at 1 kHz (mH) (tester)                                                         got       593.3  want       593.3  tol 0.005r      ok
WAH_535Q   other meter: -; coil Q at 1 kHz = wL/R                                               got      203.71  want         nan  tol info        
WAH_HALO Im(Z)/w at 1 kHz (mH) (tester)                                                         got       580.7  want       580.7  tol 0.005r      ok
WAH_HALO   other meter: Honeytek '522uH'; coil Q at 1 kHz = wL/R                                got      131.25  want         nan  tol info        
WAH_SOUL_HALO Im(Z)/w at 1 kHz (mH) (Honeytek)                                                  got         510  want         510  tol 0.005r      ok
WAH_SOUL_HALO   other meter: 30.3 ohms/597.8mH; coil Q at 1 kHz = wL/R                          got      108.62  want         nan  tol info        
WAH_MAMMOTH Im(Z)/w at 1 kHz (mH) (Honeytek)                                                    got         622  want         622  tol 0.005r      ok
WAH_MAMMOTH   other meter: 30.7 ohms/730.3mH; coil Q at 1 kHz = wL/R                            got      132.93  want         nan  tol info        
-- options: core loss Qc and self-capacitance Cp (generic wah_inductor, 500 mH)
Qc=0: coil Q at 1 kHz = wL/R                                                                    got       184.8  want       184.8  tol 0.001r      ok
Qc=50: coil Q at 1 kHz = 1/(R/wL + 1/Qc)                                                        got      39.349  want      39.353  tol 0.01r       ok
Cp=100p: impedance phase at 1/(2 pi sqrt(L Cp)) ~ 0 (deg)                                       got     0.15355  want           0  tol 2           ok
-- Cry Baby GCB-95 circuit, generic 500 mH / 17 ohm (ElectroSmash: '500mH typ.')
Rtone 0.1k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                 got      2191.3  want         nan  tol info        
    gain (dB)                                                                                   got      19.099  want         nan  tol info        
    Q                                                                                           got      2.7455  want         nan  tol info        
Rtone 1k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                   got      1908.2  want         nan  tol info        
    gain (dB)                                                                                   got      19.086  want         nan  tol info        
    Q                                                                                           got      3.1483  want         nan  tol info        
Rtone 3k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                   got      1542.5  want         nan  tol info        
    gain (dB)                                                                                   got       19.12  want         nan  tol info        
    Q                                                                                           got      3.8542  want         nan  tol info        
Rtone 5k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                   got        1332  want         nan  tol info        
    gain (dB)                                                                                   got      19.183  want         nan  tol info        
    Q                                                                                           got      4.5681  want         nan  tol info        
Rtone 10k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                  got      1046.7  want         nan  tol info        
    gain (dB)                                                                                   got      19.367  want         nan  tol info        
    Q                                                                                           got       5.795  want         nan  tol info        
Rtone 25k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                  got      726.81  want         nan  tol info        
    gain (dB)                                                                                   got      19.882  want         nan  tol info        
    Q                                                                                           got      7.8901  want         nan  tol info        
Rtone 50k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                  got      544.81  want         nan  tol info        
    gain (dB)                                                                                   got      20.568  want         nan  tol info        
    Q                                                                                           got      10.848  want         nan  tol info        
Rtone 75k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                  got       459.2  want         nan  tol info        
    gain (dB)                                                                                   got       21.17  want         nan  tol info        
    Q                                                                                           got      13.338  want         nan  tol info        
Rtone 90k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                  got      424.24  want         nan  tol info        
    gain (dB)                                                                                   got      21.544  want         nan  tol info        
    Q                                                                                           got      14.512  want         nan  tol info        
Rtone 100k: peak Hz / dB / Q(-3 dB):  peak (Hz)                                                 got      404.65  want         nan  tol info        
    gain (dB)                                                                                   got      21.818  want         nan  tol info        
    Q                                                                                           got      15.766  want         nan  tol info        
heel (pot end, Rtone 100k): peak (Hz) vs ElectroSmash 450 Hz                                    got      404.65  want         450  tol 0.15r       ok
lowest peak <= 450 Hz: the published sweep bottom is reachable (Hz)                             got      404.65  want         225  tol [0,450]     ok
highest peak >= 1.6 kHz: the published sweep top is reachable (Hz)                              got      2191.3  want       5e+08  tol [1600,1e+09] ok
peak gain, max over the sweep (dB) vs ElectroSmash 'up to 18dB' (+-4 dB)                        got      21.818  want          18  tol [14,22]     ok
pot setting for 750 Hz (ElectroSmash, 'VR1 at mid position'): Rtone (k), interpolated           got      23.708  want         nan  tol info        
-- Cry Baby with each preset, Rtone 100k (heel) and 3k (near toe): the peak moves as 1/sqrt(L)
WAH_RED_FASEL heel: peak (Hz)                                                                   got       374.5  want         nan  tol info        
WAH_RED_FASEL heel: gain (dB) / Q                                                               got      21.738  want      15.817  tol info        
WAH_RED_FASEL toe:  peak (Hz)                                                                   got      1427.4  want         nan  tol info        
WAH_YELLOW_FASEL heel: peak (Hz)                                                                got      363.03  want         nan  tol info        
WAH_YELLOW_FASEL heel: gain (dB) / Q                                                            got      22.011  want       15.78  tol info        
WAH_YELLOW_FASEL toe:  peak (Hz)                                                                got      1383.6  want         nan  tol info        
WAH_YELLOW_FASEL heel peak / WAH_RED_FASEL = sqrt(L ratio)                                      got     0.96937  want      0.9697  tol 0.03r       ok
WAH_GCB95 heel: peak (Hz)                                                                       got      355.88  want         nan  tol info        
WAH_GCB95 heel: gain (dB) / Q                                                                   got       21.64  want      14.468  tol info        
WAH_GCB95 toe:  peak (Hz)                                                                       got      1356.3  want         nan  tol info        
WAH_GCB95 heel peak / WAH_RED_FASEL = sqrt(L ratio)                                             got     0.95028  want     0.95072  tol 0.03r       ok
WAH_GCB95_90S heel: peak (Hz)                                                                   got      343.96  want         nan  tol info        
WAH_GCB95_90S heel: gain (dB) / Q                                                               got      21.858  want      14.475  tol info        
WAH_GCB95_90S toe:  peak (Hz)                                                                   got      1310.8  want         nan  tol info        
WAH_GCB95_90S heel peak / WAH_RED_FASEL = sqrt(L ratio)                                         got     0.91844  want      0.9192  tol 0.03r       ok
WAH_GCB95_80S heel: peak (Hz)                                                                   got      489.24  want         nan  tol info        
WAH_GCB95_80S heel: gain (dB) / Q                                                               got      22.726  want      17.391  tol info        
WAH_GCB95_80S toe:  peak (Hz)                                                                   got      1864.9  want         nan  tol info        
WAH_GCB95_80S heel peak / WAH_RED_FASEL = sqrt(L ratio)                                         got      1.3064  want      1.3037  tol 0.03r       ok
WAH_HENDRIX heel: peak (Hz)                                                                     got       380.8  want         nan  tol info        
WAH_HENDRIX heel: gain (dB) / Q                                                                 got      22.108  want      15.807  tol info        
WAH_HENDRIX toe:  peak (Hz)                                                                     got      1451.4  want         nan  tol info        
WAH_HENDRIX heel peak / WAH_RED_FASEL = sqrt(L ratio)                                           got      1.0168  want      1.0167  tol 0.03r       ok
WAH_535Q heel: peak (Hz)                                                                        got       371.2  want         nan  tol info        
WAH_535Q heel: gain (dB) / Q                                                                    got      21.597  want      14.495  tol info        
WAH_535Q toe:  peak (Hz)                                                                        got      1414.9  want         nan  tol info        
WAH_535Q heel peak / WAH_RED_FASEL = sqrt(L ratio)                                              got     0.99118  want     0.99128  tol 0.03r       ok
WAH_HALO heel: peak (Hz)                                                                        got      375.27  want         nan  tol info        
WAH_HALO heel: gain (dB) / Q                                                                    got      20.703  want      13.333  tol info        
WAH_HALO toe:  peak (Hz)                                                                        got      1430.6  want         nan  tol info        
WAH_HALO heel peak / WAH_RED_FASEL = sqrt(L ratio)                                              got      1.0021  want       1.002  tol 0.03r       ok
WAH_SOUL_HALO heel: peak (Hz)                                                                   got      400.67  want         nan  tol info        
WAH_SOUL_HALO heel: gain (dB) / Q                                                               got      20.522  want      13.362  tol info        
WAH_SOUL_HALO toe:  peak (Hz)                                                                   got      1527.6  want         nan  tol info        
WAH_SOUL_HALO heel peak / WAH_RED_FASEL = sqrt(L ratio)                                         got      1.0699  want      1.0692  tol 0.03r       ok
WAH_MAMMOTH heel: peak (Hz)                                                                     got       362.5  want         nan  tol info        
WAH_MAMMOTH heel: gain (dB) / Q                                                                 got      20.568  want      13.332  tol info        
WAH_MAMMOTH toe:  peak (Hz)                                                                     got      1381.9  want         nan  tol info        
WAH_MAMMOTH heel peak / WAH_RED_FASEL = sqrt(L ratio)                                           got     0.96794  want     0.96814  tol 0.03r       ok
-- .tran vs .ac: 1 V 2 kHz into 100 k + WAH_RED_FASEL || 10 nF
amplitude .tran = |V| .ac (V)                                                                   got     0.66852  want      0.6685  tol 0.01r       ok
-- demo_wah-inductor.asc netlisted by asc2net = hand netlist
demo |V(tank)| @500 Hz = hand netlist                                                           got    0.019479  want    0.019479  tol 0.0001r     ok
demo |V(tank)| @2000 Hz = hand netlist                                                          got     0.64867  want     0.64867  tol 0.0001r     ok
demo |V(tank)| @8000 Hz = hand netlist                                                          got    0.021231  want    0.021231  tol 0.0001r     ok

40/40 checks passed
```

## What it does not model

- **Constant L.** L does not depend on frequency, level or DC current, and there is no
  saturation. In the Cry Baby the inductor carries only the base bias current of the gain
  stage (microamps) and signal currents well below 1 mA, so saturation is not expected in
  normal use.
- **No core loss and no self-capacitance by default** (no data; see above). Core loss
  would lower the peak gain and Q, mostly at the heel, where the tank Q is highest (about
  16 in the bench).
- **No hysteresis distortion,** no stray magnetic coupling and no hum pickup. The last
  matters for the unshielded toroids.
- **The Cry Baby fixture** is the circuit in the bench, not a subckt of this library. Its
  pot is linear (VR1 = Rtone + (100 k − Rtone)).

## How to use it in LTspice

1. Put `wah-inductor.sub` and the `.asy` files next to your schematic (or in your LTspice
   `lib/sub` and `lib/sym` folders).
2. Place e.g. `WAH_RED_FASEL` in place of the inductor. Its `ModelFile` attribute points at
   `wah-inductor.sub`; if LTspice does not find it, add `.lib wah-inductor.sub`.
3. Optionally set `Qc` (core Q at 1 kHz) or `Cp` if you have a measurement.

For a netlist: `XL1 hi lo WAH_HALO` or `XL1 hi lo wah_inductor L=500m R=17`.

The demo (`demo_wah-inductor.asc`) is a red Fasel in parallel with 10 nF, fed through
100 k. V(tank) peaks near 2.1 kHz.

## Files

- `wah-inductor.sub`: the subckt and the generated presets.
- `wi_presets.py`: the readings and their sources.
- `make_symbols.py`: writes the presets, the `.asy` files and `demo_wah-inductor.asc`.
- `bench_wah-inductor.py`: the bench, including the Cry Baby circuit.

## Sources of inspiration

- ElectroSmash's Cry Baby analysis (as above).
- The Cry Baby schematics in `sources/audio-effects-ltspice/` and
  `sources/ltspice-guitar-pedals/`, and J. Shaw's "Simulating the Dunlop Crybaby Wah
  Pedal in LTSpice" (<https://cushychicken.github.io/ltspice-dunlop-crybaby/>). His
  simulation gives about 430 Hz and 2.1 kHz at the pot ends; this bench gives 405 Hz and
  2.19 kHz.

No text was copied from these sources.
