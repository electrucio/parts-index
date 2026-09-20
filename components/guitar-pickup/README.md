# guitar-pickup — magnetic guitar and bass pickups as a signal source

`guitar-pickup.sub` models a magnetic pickup as the source it is for the guitar's controls,
the cable and the amplifier input:

- the coil **inductance**, with a simple **eddy-current loss**;
- the **DC resistance** of the winding;
- the **winding capacitance**;
- a behavioural input for the string signal: whatever voltage you put on the `EMF` pin is
  the voltage induced by the string.

Seven presets reproduce pickups measured by Helmuth Lemme (inductance, winding capacitance,
resonance with seven load capacitors, peak height). The cable is **not** part of the model:
add it yourself (see "Cable, pots and amp input").

## Subckt and pins

| subckt | pins (SpiceOrder) | parameters (defaults) |
|---|---|---|
| `pickup` | OUT GND EMF | `L`=2.5, `R`=6k, `C`=110p, `Rx`=500k, `kx`=0.5 |
| `PU_<type>` (7 presets) | OUT GND EMF | `kx` (default 0.5) |

- **OUT**: the hot lead (to the volume pot, the tone control, the jack).
- **GND**: the ground lead.
- **EMF**: the string signal, applied between EMF and GND by a voltage source (a sine, a
  PWL of a plucked string, a `.wav` file). The pin draws no current (1 GΩ to GND); an
  internal E-source copies the voltage in series with the coil.
- **Polarity**: below resonance, V(OUT,GND) follows V(EMF,GND) (bench: 0° at 100 Hz).

The symbol (`make_symbols.py`) is a bobbin with six pole pieces. OUT is at (96,32), GND at
(96,96) and EMF on the left at (0,64). One `.asy` per subckt and per preset.

| name | meaning |
|---|---|
| `L` | coil inductance at low frequency (whole pickup; both coils in series for a humbucker) |
| `R` | DC resistance |
| `C` | winding (self) capacitance, across OUT–GND |
| `Rx` | eddy-current resistance across the damped part of the coil; 0 = no eddy loss |
| `kx` | fraction of L that the eddy currents damp (0…0.99) |

## Equations

The circuit is Lemme's equivalent circuit for a pickup with eddy currents ("The Secrets of
Electric Guitar Pickups", <https://buildyourguitar.com/resources/lemme/>, Fig. 6): the coil
is split in two, and only one part has a resistor across it.

    EMF ── L·(1−kx) ── [ L·kx ‖ Rx ] ── R ── OUT
                                             │
                                             C
                                             │
    GND ─────────────────────────────────────┘

- Low frequency: inductance L, resistance R.
- High frequency: the damped part L·kx turns into Rx, so the inductance falls towards
  L·(1−kx).
- Unloaded resonance f0 = 1/(2π√(L·C)). With a load capacitance Cx (cable, tone cap),
  f0 ≈ 1/(2π√(L·(C+Cx))).
- The peak height is set by R, Rx and the resistive load (pots ‖ amp input).

Lemme notes that a resistor across the whole coil, or across the terminals, lowers the peak
but misses the other eddy-current effects; the split coil is his remedy. The bench shows how
far the split coil goes with the fitted values (see "What it does not model").

## Presets and provenance

All sources were fetched on 2026-09-14. `pu_presets.py` holds every number and its source;
`make_symbols.py` writes the preset block into the `.sub`.

**Lemme table.** H. Lemme, "Resonant frequencies of some well-know pickups for various
parallel capacitors", <https://buildyourguitar.com/resources/lemme/table.htm>, the companion
table of the article above. All values were measured by Lemme. He states that the "figures
may show sample variations by ±10 % or more", and the resonances are rounded to 0.1 kHz.
The site's TLS certificate had expired, so the page was read with `curl -k`. The HTML
fetched has sha256 `b71ce20fbfe169b03525cd5c4fcb52d978750859c43685f039593f6ad7d945df`
(article page: `a828805b5692d4745092c7aa1aa618bf62f6ef844acf13716180dac9b5fe0f81`).

**DC resistance.** Lemme's table has no DC resistance, so R comes from Seymour Duncan for
the same model family (not the same specimen):

- SD: Seymour Duncan, "What is the dc resistance of popular pickups?", last updated
  2019-10-17, <https://www.seymourduncan.com/blog/swd/what-is-the-dc-resistance-of-popular-pickups>.
- SD59: the Seymour Duncan '59 Model product page, <https://www.seymourduncan.com/single-product/59-model>.

Zollner shows that R changes the resonance emphasis very little (PotEG §5.5.4, Fig. 5.5.9:
+50 % R, almost the same peak).

| preset | Lemme row | L H | C pF | resonance kHz with 470p / 680p / 1n / 1.5n / 2.2n / 3.3n / 4.7n | peak Q | R (source) | Rx (fit) |
|---|---|---|---|---|---|---|---|
| PU_STRAT72 | Fender US-Strat. (1972) | 2.2 | 110 | 4.4 / 3.8 / 3.2 / 2.7 / 2.2 / 1.8 / 1.5 | 6.3 | 6.05k (SD: 5.8–6.3k, midpoint) | 276.7k |
| PU_STRAT_MEX | Fender Mexico Strat. | 2.8 | 60 | 4.2 / 3.3 / 2.9 / 2.3 / 1.9 / 1.6 / 1.3 | 3.1 | 6.05k (SD, Fender Strat) | 66.25k |
| PU_TELE_BRIDGE | Fender Telecaster Bridge | 2.9 | 160 | 3.7 / 3.2 / 2.7 / 2.3 / 1.9 / 1.6 / 1.3 | 3.7 | 6.4k (SD: Tele lead 6.2–6.6k) | 91.39k |
| PU_P90 | Gibson P90 | 6.6 | 95 | 2.6 / 2.2 / 1.9 / 1.5 / 1.3 / 1.1 / 0.9 | 2.9 | 8.6k (SD) | 86.28k |
| PU_SD59 | Seymour Duncan 59 | 5.0 | 120 | 2.9 / 2.6 / 2.2 / 1.8 / 1.5 / 1.3 / 1.0 | 2.6 | 7.6k (SD59, neck; bridge 8.2k) | 58k |
| PU_JAZZBASS | Fender Jazz Bass | 3.6 | 150 | 3.4 / 2.9 / 2.5 / 2.1 / 1.7 / 1.4 / 1.2 | 3.9 | 8.5k (SD) | 129.2k |
| PU_PBASS | Fender Precision Bass | 6.0 | 15 | 2.9 / 2.5 / 2.1 / 1.7 / 1.4 / 1.1 / 0.9 | 5.4 | 10.6k (SD) | 341.6k |

### How the derived numbers were obtained

- **Rx is fitted, kx is Lemme's starting point.** kx = 0.5 is Lemme's suggestion
  ("identical sizes can be used as a point of departure"). Rx is fitted by `fit_rx()` in
  `pu_presets.py` (bisection, numpy model of the same circuit). The target is Lemme's "Max.
  peak height Q" with 470 pF and a **10 MΩ resistive load**.
- **The 10 MΩ load is an assumption.** Lemme's table does not state the resistive load of
  the peak-height column. 10 MΩ is the ohmic load of his high-impedance reference curves
  (article, Fig. 15), and "max." suggests the least-damped condition. With a 1 MΩ load
  instead, the eddy-free 1972 Strat already has a peak of 6.3 (consistent with Zollner's
  remark that the Strat has little eddy loss), but the Precision Bass could not then be
  fitted (its eddy-free peak would be below Lemme's 5.4). So 10 MΩ was kept for all.
- **The SD59 row.** Lemme does not say neck or bridge, so the neck DCR is used.
- **PU_PBASS winding capacitance.** Lemme's 15 pF is unusually low but is used as
  published; his seven resonances fit it (bench).
- **Which pickups were left out.** The DiMarzio, EMG, Gibson 490, P100, Iommi, EB,
  Rickenbacker, Joe Barden, Shadow and Fender-humbucker rows have no DCR source of
  comparable quality. To add one, append a row to `pu_presets.py` and run
  `make_symbols.py`.

## Cable, pots and amp input (not in the model)

The cable capacitance dominates the resonance. Lemme gives 300–1000 pF for guitar cables,
against 80–200 pF of winding capacitance. Zollner (PotEG §9.4, "Guitar cables",
<https://gitec-forum-eng.de/wp-content/uploads/2019/03/poteg-9-4-guitar-cables.pdf>) gives
about 100 pF/m (±30 %): 300–600 pF for usual lengths, up to about 1.5 nF for very long
cables, and 70 pF/m for low-capacitance cables.

Add these parts to the OUT node yourself:

- the cable, as a capacitor from OUT to GND (a 3 m cable is about 330 pF);
- the volume and tone pots (250 k for single coils, 500 k for humbuckers, typically) and
  the tone capacitor;
- the amplifier input resistance (typically 1 MΩ).

A buffer or the amp input capacitance can be added the same way. The peak height depends
strongly on the resistive load: with 470 pF and 47 kΩ the 1972 Strat has no peak at all,
exactly as Lemme measured (article, Fig. 14; bench).

## Bench results

Run `python3 bench_guitar-pickup.py` with the shell sandbox off. It exits 1 on any failure.
Rows marked "info" are shown for comparison and are not pass/fail.

It checks:

- **Presets:** R(DC) against the DCR source, and the low-frequency inductance against
  Lemme's L.
- **Lemme resonances:** the resonance with each of Lemme's seven load capacitors (49
  published measurements), each within Lemme's ±10 %, and an rms deviation within 5 %.
  Also the peak height at 470 pF, which is fitted.
- **Lemme, Fig. 14:** the 1972 Strat's peak vanishes with 47 kΩ.
- **Zollner, PotEG Fig. 5.9.26:** the measured |Z| maximum of an iron-free Gibson
  screw-coil (R 4420 Ω, L 1125 mH, C 43 pF,
  <https://gitec-forum-eng.de/wp-content/uploads/2019/03/poteg-5-9-equivalent-circuits.pdf>)
  with 330, 700 and 1030 pF loads.
- `.tran` against `.ac`, and the polarity.
- The demo's pin order: the demo netlisted by `tools/ltspice/asc2net.py` must match a hand
  netlist.

Full output:

```
-- presets: R(DC) vs source, low-frequency inductance vs Lemme (EMF grounded)
PU_STRAT72 R(DC) (SD 5.8k-6.3k (midpoint))                                                                        got        6050  want        6050  tol 0.001r      ok
PU_STRAT_MEX R(DC) (SD 5.8k-6.3k (midpoint, Fender Strat))                                                        got        6050  want        6050  tol 0.001r      ok
PU_TELE_BRIDGE R(DC) (SD Telecaster lead 6.2k-6.6k (midpoint))                                                    got        6400  want        6400  tol 0.001r      ok
PU_P90 R(DC) (SD Gibson P-90 8.6k)                                                                                got        8600  want        8600  tol 0.001r      ok
PU_SD59 R(DC) (SD59 neck 7.60k (bridge 8.2k))                                                                     got        7600  want        7600  tol 0.001r      ok
PU_JAZZBASS R(DC) (SD Fender Jazz Bass 8.5k)                                                                      got        8500  want        8500  tol 0.001r      ok
PU_PBASS R(DC) (SD Fender Precision Bass 10.6k)                                                                   got       10600  want       10600  tol 0.001r      ok
PU_STRAT72 Im(Z)/w at 100 Hz = Lemme L (H)                                                                        got      2.1962  want         2.2  tol 0.02r       ok
PU_STRAT_MEX Im(Z)/w at 100 Hz = Lemme L (H)                                                                      got      2.7977  want         2.8  tol 0.02r       ok
PU_TELE_BRIDGE Im(Z)/w at 100 Hz = Lemme L (H)                                                                    got      2.8938  want         2.9  tol 0.02r       ok
PU_P90 Im(Z)/w at 100 Hz = Lemme L (H)                                                                            got      6.5926  want         6.6  tol 0.02r       ok
PU_SD59 Im(Z)/w at 100 Hz = Lemme L (H)                                                                           got      4.9923  want           5  tol 0.02r       ok
PU_JAZZBASS Im(Z)/w at 100 Hz = Lemme L (H)                                                                       got      3.5898  want         3.6  tol 0.02r       ok
PU_PBASS Im(Z)/w at 100 Hz = Lemme L (H)                                                                          got      5.9984  want           6  tol 0.02r       ok
-- presets: resonance with Lemme's load capacitors (|| 10 Meg), kHz; tol = Lemme's +-10 % sample spread
PU_STRAT72 + 470p: peak (kHz)                                                                                     got      4.4232  want         4.4  tol 0.1r        ok
PU_STRAT72 + 470p: peak height (Rx fitted to Lemme Q)                                                             got      6.3001  want         6.3  tol 0.02r       ok
PU_STRAT72 + 680p: peak (kHz)                                                                                     got       3.786  want         3.8  tol 0.1r        ok
PU_STRAT72 + 1000p: peak (kHz)                                                                                    got      3.1893  want         3.2  tol 0.1r        ok
PU_STRAT72 + 1500p: peak (kHz)                                                                                    got      2.6423  want         2.7  tol 0.1r        ok
PU_STRAT72 + 2200p: peak (kHz)                                                                                    got      2.1993  want         2.2  tol 0.1r        ok
PU_STRAT72 + 3300p: peak (kHz)                                                                                    got      1.8016  want         1.8  tol 0.1r        ok
PU_STRAT72 + 4700p: peak (kHz)                                                                                    got      1.5077  want         1.5  tol 0.1r        ok
PU_STRAT_MEX + 470p: peak (kHz)                                                                                   got      4.1312  want         4.2  tol 0.1r        ok
PU_STRAT_MEX + 470p: peak height (Rx fitted to Lemme Q)                                                           got      3.1001  want         3.1  tol 0.02r       ok
PU_STRAT_MEX + 680p: peak (kHz)                                                                                   got      3.4664  want         3.3  tol 0.1r        ok
PU_STRAT_MEX + 1000p: peak (kHz)                                                                                  got      2.8771  want         2.9  tol 0.1r        ok
PU_STRAT_MEX + 1500p: peak (kHz)                                                                                  got      2.3586  want         2.3  tol 0.1r        ok
PU_STRAT_MEX + 2200p: peak (kHz)                                                                                  got      1.9504  want         1.9  tol 0.1r        ok
PU_STRAT_MEX + 3300p: peak (kHz)                                                                                  got      1.5911  want         1.6  tol 0.1r        ok
PU_STRAT_MEX + 4700p: peak (kHz)                                                                                  got      1.3292  want         1.3  tol 0.1r        ok
PU_TELE_BRIDGE + 470p: peak (kHz)                                                                                 got      3.6865  want         3.7  tol 0.1r        ok
PU_TELE_BRIDGE + 470p: peak height (Rx fitted to Lemme Q)                                                         got         3.7  want         3.7  tol 0.02r       ok
PU_TELE_BRIDGE + 680p: peak (kHz)                                                                                 got      3.1817  want         3.2  tol 0.1r        ok
PU_TELE_BRIDGE + 1000p: peak (kHz)                                                                                got      2.6987  want         2.7  tol 0.1r        ok
PU_TELE_BRIDGE + 1500p: peak (kHz)                                                                                got      2.2484  want         2.3  tol 0.1r        ok
PU_TELE_BRIDGE + 2200p: peak (kHz)                                                                                got       1.879  want         1.9  tol 0.1r        ok
PU_TELE_BRIDGE + 3300p: peak (kHz)                                                                                got      1.5445  want         1.6  tol 0.1r        ok
PU_TELE_BRIDGE + 4700p: peak (kHz)                                                                                got      1.2959  want         1.3  tol 0.1r        ok
PU_P90 + 470p: peak (kHz)                                                                                         got      2.6241  want         2.6  tol 0.1r        ok
PU_P90 + 470p: peak height (Rx fitted to Lemme Q)                                                                 got      2.8999  want         2.9  tol 0.02r       ok
PU_P90 + 680p: peak (kHz)                                                                                         got      2.2161  want         2.2  tol 0.1r        ok
PU_P90 + 1000p: peak (kHz)                                                                                        got      1.8486  want         1.9  tol 0.1r        ok
PU_P90 + 1500p: peak (kHz)                                                                                        got      1.5214  want         1.5  tol 0.1r        ok
PU_P90 + 2200p: peak (kHz)                                                                                        got      1.2616  want         1.3  tol 0.1r        ok
PU_P90 + 3300p: peak (kHz)                                                                                        got      1.0316  want         1.1  tol 0.1r        ok
PU_P90 + 4700p: peak (kHz)                                                                                        got     0.86342  want         0.9  tol 0.1r        ok
PU_SD59 + 470p: peak (kHz)                                                                                        got      3.0053  want         2.9  tol 0.1r        ok
PU_SD59 + 470p: peak height (Rx fitted to Lemme Q)                                                                got         2.6  want         2.6  tol 0.02r       ok
PU_SD59 + 680p: peak (kHz)                                                                                        got      2.5331  want         2.6  tol 0.1r        ok
PU_SD59 + 1000p: peak (kHz)                                                                                       got      2.1098  want         2.2  tol 0.1r        ok
PU_SD59 + 1500p: peak (kHz)                                                                                       got      1.7347  want         1.8  tol 0.1r        ok
PU_SD59 + 2200p: peak (kHz)                                                                                       got      1.4378  want         1.5  tol 0.1r        ok
PU_SD59 + 3300p: peak (kHz)                                                                                       got      1.1753  want         1.3  tol 0.1r        ok
PU_SD59 + 4700p: peak (kHz)                                                                                       got     0.98353  want           1  tol 0.1r        ok
PU_JAZZBASS + 470p: peak (kHz)                                                                                    got      3.3223  want         3.4  tol 0.1r        ok
PU_JAZZBASS + 470p: peak height (Rx fitted to Lemme Q)                                                            got      3.9007  want         3.9  tol 0.02r       ok
PU_JAZZBASS + 680p: peak (kHz)                                                                                    got       2.864  want         2.9  tol 0.1r        ok
PU_JAZZBASS + 1000p: peak (kHz)                                                                                   got      2.4262  want         2.5  tol 0.1r        ok
PU_JAZZBASS + 1500p: peak (kHz)                                                                                   got      2.0185  want         2.1  tol 0.1r        ok
PU_JAZZBASS + 2200p: peak (kHz)                                                                                   got      1.6842  want         1.7  tol 0.1r        ok
PU_JAZZBASS + 3300p: peak (kHz)                                                                                   got      1.3815  want         1.4  tol 0.1r        ok
PU_JAZZBASS + 4700p: peak (kHz)                                                                                   got      1.1564  want         1.2  tol 0.1r        ok
PU_PBASS + 470p: peak (kHz)                                                                                       got      2.9246  want         2.9  tol 0.1r        ok
PU_PBASS + 470p: peak height (Rx fitted to Lemme Q)                                                               got      5.4002  want         5.4  tol 0.02r       ok
PU_PBASS + 680p: peak (kHz)                                                                                       got      2.4397  want         2.5  tol 0.1r        ok
PU_PBASS + 1000p: peak (kHz)                                                                                      got      2.0152  want         2.1  tol 0.1r        ok
PU_PBASS + 1500p: peak (kHz)                                                                                      got      1.6453  want         1.7  tol 0.1r        ok
PU_PBASS + 2200p: peak (kHz)                                                                                      got       1.356  want         1.4  tol 0.1r        ok
PU_PBASS + 3300p: peak (kHz)                                                                                      got      1.1025  want         1.1  tol 0.1r        ok
PU_PBASS + 4700p: peak (kHz)                                                                                      got     0.91808  want         0.9  tol 0.1r        ok
all 49 Lemme resonances: rms deviation (fraction)                                                                 got    0.028631  want       0.025  tol [0,0.05]    ok
  worst single deviation (fraction)                                                                               got   -0.095889  want         nan  tol info        
-- Lemme, article Fig. 14: 1972 Strat with 470 pF, 'with 47 kOhms or less the peak vanishes'
PU_STRAT72, 470p || 47k: max |H| / |H(100 Hz)|                                                                    got      1.0011  want       0.525  tol [0,1.05]    ok
PU_STRAT72, 470p || 10000k: max |H| / |H(100 Hz)|                                                                 got      6.2968  want         6.5  tol [5.5,7.5]   ok
-- Zollner PotEG Fig. 5.9.26: Gibson screw-coil without iron (R 4420, L 1125 mH, C 43 pF), |Z| maximum vs load
screw-coil + 330p: |Z| max (kHz, measured)                                                                        got      7.7694  want         7.7  tol 0.03r       ok
screw-coil + 700p: |Z| max (kHz, measured)                                                                        got      5.5047  want         5.5  tol 0.03r       ok
screw-coil + 1030p: |Z| max (kHz, measured)                                                                       got      4.5804  want         4.6  tol 0.03r       ok
screw-coil unloaded: |Z| max (kHz); Zollner: 21 (Fig. 5.9.26) and 23 (Fig. 5.9.18)                                got      22.883  want          21  tol info        
-- eddy loss (info): Lemme's split coil vs a plain resistor across the terminals, same peak height (P-90 + 470p)
PU_P90 split coil: level at f0/2 re 20 Hz (dB) (Lemme: eddy currents lower it)                                    got      2.2986  want         nan  tol info        
PU_P90 split coil: slope 2 f0 -> 4 f0 (dB/oct)                                                                    got     -12.267  want         nan  tol info        
PU_P90 split coil: slope 4 f0 -> 8 f0 (dB/oct) (Lemme: up to -18)                                                 got     -11.597  want         nan  tol info        
PU_P90 Rp 394k: level at f0/2 re 20 Hz (dB) (Lemme: eddy currents lower it)                                       got      2.2022  want         nan  tol info        
PU_P90 Rp 394k: slope 2 f0 -> 4 f0 (dB/oct)                                                                       got      -13.84  want         nan  tol info        
PU_P90 Rp 394k: slope 4 f0 -> 8 f0 (dB/oct) (Lemme: up to -18)                                                    got     -12.447  want         nan  tol info        
-- .tran vs .ac: PU_STRAT72, 100 mV 3 kHz EMF, 470p || 1 Meg
amplitude .tran = |V| .ac at 3 kHz (V)                                                                            got     0.17567  want     0.17567  tol 0.01r       ok
polarity: phase V(OUT)/V(EMF) at 100 Hz (deg)                                                                     got    -0.20442  want           0  tol 1           ok
-- demo_guitar-pickup.asc netlisted by asc2net = hand netlist
demo |V(out)| @100 Hz = hand netlist                                                                              got    0.097096  want    0.097096  tol 0.0001r     ok
demo |V(out)| @3000 Hz = hand netlist                                                                             got     0.13498  want     0.13498  tol 0.0001r     ok
demo |V(out)| @10000 Hz = hand netlist                                                                            got    0.034287  want    0.034287  tol 0.0001r     ok

81/81 checks passed
```

## What it does not model

- **Eddy currents are one resistor.** With Rx fitted to the peak height, the split coil
  (kx = 0.5) lowers the peak but does not give the steeper roll-off above resonance or
  the dip below it that Lemme describes for strong eddy currents. The bench's info rows
  for the P-90 show about −12 dB/octave, like a plain resistor across the terminals. For
  those details use a higher-order network (Zollner, PotEG §5.9) or raise kx and refit
  Rx.
- **Lumped L and C.** There is no second, distributed resonance (Zollner's iron-free coil
  resonates at 21–23 kHz unloaded; the model gives 22.9 kHz).
- **The string is outside the model.** The pickup's sensitivity (volts per m/s of string
  velocity) and the aperture or comb filtering of the string position are not modelled.
  For a humbucker, Lemme gives notches at about 3 kHz (low E) and 4 kHz (A).
- **No non-linear distortion.** The flux vs pole-to-string distance is hyperbolic
  (Lemme), which adds even harmonics; there is no magnetic string pull, no hum pickup and
  no coupling between pickups.
- **Sample variation.** Lemme's figures vary by ±10 % or more between samples, and the DCR
  values come from the model family, not from Lemme's specimens.

## How to use it in LTspice

1. Put `guitar-pickup.sub` and the `.asy` files in the same folder as your schematic (or
   in your LTspice `lib/sub` and `lib/sym` folders).
2. Place a symbol, e.g. `PU_STRAT72`. Its `ModelFile` attribute points at
   `guitar-pickup.sub`; if LTspice does not find it, add `.lib guitar-pickup.sub` to the
   schematic.
3. Drive EMF from a voltage source to GND, e.g. `SINE(0 0.1 440)` or `AC 0.1`. Real
   pickups give 100 mV to 1 V rms (Lemme).
4. Load OUT with the cable, pots and amp input (see above).

For a netlist: `X1 out 0 emf PU_P90` or `X1 out 0 emf pickup L=4.5 R=8k C=120p Rx=80k`.

The demo (`demo_guitar-pickup.asc`) is a 1972 Strat pickup into a 250 k volume pot, a 3 m
cable (330 pF) and a 1 MΩ amp input.

## Files

- `guitar-pickup.sub`: the subckt and the generated presets.
- `pu_presets.py`: Lemme's table rows, the DCR sources and the Rx fit.
- `make_symbols.py`: writes the presets, the `.asy` files and `demo_guitar-pickup.asc`.
- `bench_guitar-pickup.py`: the bench.

## Sources of inspiration

- Lemme's split-coil eddy-current circuit, as above.
- The same resistor-across-one-coil idea in Distorque Audio's humbucker model,
  `sources/distorque-audio/raw/humbucker-model.txt`.
- M. Zollner, *Physics of the Electric Guitar* (PotEG), chapters 5.5, 5.9, 5.10 and 9.4,
  <https://gitec-forum-eng.de/the-book/>.

No text was copied from these sources.

## Local copies of the cited documents

The PDFs cited above are archived in `datasheets/components/` with URL, date and sha256
(`datasheets/components/SOURCES.md`).
