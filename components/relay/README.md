# relay — electromechanical relays (monostable, latching)

Behavioural relays for channel switching, true-bypass relays, mute and power
switching. What matters in an amp or pedal schematic is modelled from physics:
- **coil:** R and an inductance that grows as the armature closes;
- **thresholds:** pick-up / drop-out with hysteresis;
- **timing:** operate and release times, and the lengthened release when a flyback diode is fitted;
- **polarity:** either DC polarity, or polarised;
- **contacts:** Ron / Roff, break-before-make.

Every preset number is traced to a datasheet page or marked as an estimate.

Files: `relay.sub` (all subckts), `make_symbols.py` (writes the 15 `.asy` and
`demo_relay.asc`), `bench_relay.py` (verification), this README.

## Subckts and pins

Coil first, then each pole as COM NC NO. NC is the contact closed with the coil off (reset).

| subckt | pins | what |
|---|---|---|
| `relay_spst` | CP CN COM NO | 1 Form A (SPST-NO) |
| `relay_spdt` | CP CN COM NC NO | 1 Form C |
| `relay_dpdt` | CP CN COM1 NC1 NO1 COM2 NC2 NO2 | 2 Form C (the usual signal relay) |
| `relay_latch_dpdt` | CP CN COM1 NC1 NO1 COM2 NC2 NO2 | single-coil latching: CP>CN sets, reversed resets |
| `relay_latch2_dpdt` | SP SN RP RN COM1 NC1 NO1 COM2 NC2 NO2 | dual-coil latching: S coil sets, R coil resets |
| presets (below) | as `relay_dpdt` / `relay_latch2_dpdt` | one-line wrappers |

In the symbols the pins are named COIL+ COIL- (SET+ SET- RST+ RST-), COM1, NC1, NO1…
Geometry is the same for all of them:
- coil on the left: COIL+ at (0,16), COIL- at (0,112);
- one pole every 128 units to the right: NC at (ox,16), NO at (ox+64,16), COM at (ox+32,112), where ox = 64 + 128·k;
- contacts are drawn de-energised.

## Parameters

Monostable relays (`relay_spst/spdt/dpdt`). The defaults are a generic small signal
relay; they are estimates within the range of the presets below.

| param | meaning | default |
|---|---|---|
| `Vnom` | rated coil voltage | 12 |
| `R` | coil resistance | 288 |
| `L` | coil inductance, armature released; 0 → 1.6 ms·R (G5V-2 L/R) | 0 |
| `Lc` | coil inductance, armature operated; 0 → 1.4·L (median G5V-2 Lc/L) | 0 |
| `pu` | pick-up (must-operate) voltage / Vnom | 0.65 |
| `do` | drop-out (must-release) voltage / Vnom | 0.2 |
| `Top` | operate time at Vnom: coil on → NO closed | 4m |
| `Trel` | release time, coil unsuppressed: coil off → NC closed | 2m |
| `Ron`, `Roff` | contact resistance, open-contact resistance | 50m, 1G |
| `pol` | 0 non-polarised (either polarity operates), 1 polarised | 0 |
| `xnc`, `xno` | fraction of armature travel where NC breaks / NO makes; xno < xnc gives make-before-break | 0.15, 0.85 |
| `Cp`, `Rp` | winding capacitance, shunt across the coil (estimates) | 20p, 1Meg |

Latching relays use the same parameters with these changes:
- `pset` / `prst` (set / reset voltage as a fraction of Vnom, default 0.6) replace pu / do.
- `Top` / `Trel` are the set / reset times.
- `state0` (0 or 1) is the position at the operating point.

## Model

- **Coil.** R in series with an inductor whose flux linkage λ is a state variable:
  dλ/dt = v_L, i = λ / L(x), with L(x) = L + (Lc − L)·x. Here x is the armature position (0 → 1).
  As the gap closes the current dips, as in a real coil. That is the dip you see on a scope.
- **Pull.** The pull follows the flux:
  - the relay operates when λ > L·pu·Inom (open gap);
  - it releases when λ < Lc·do·Inom (closed gap), with Inom = Vnom/R.

  At rest these are exactly the datasheet pick-up and drop-out currents. During travel the flux keeps
  the snap action; a pure current threshold stalls the armature half way, which the bench caught at
  80 %V.
- **Memory / hysteresis.** A smooth bistable state m (B-source + 1 µF, double-well hold term) is
  driven to 1 or 0 by tanh sigmoids. It holds its value between the two thresholds. A latching relay
  holds it with no current at all.
- **Armature.** x moves at constant speed to the flipped state: 0 → 1 in Tmon, 1 → 0 in Tmoff.
  - The time for the current to reach pick-up at Vnom is ti = (L/R)·ln(1/(1 − pu)).
  - So Tmon = (Top − ti)/xno and Tmoff = Trel/(1 − xnc).
  - The operate time therefore depends on the coil voltage the way the datasheet graph does.
- **Release with a flyback diode.** After switch-off the diode keeps the current flowing, and it
  decays with τ ≈ Lc/R. The armature only leaves once λ reaches the drop-out level, so the release
  time comes out of the circuit, not from a table. With no suppression the coil kick rings on Cp‖Rp
  until something clamps it.
- **Contacts.** Voltage-controlled switches (`SW`) on x: NC is on for x < xnc, NO for x > xno
  (0.01 hysteresis), which gives break-before-make on both edges.

**No A-devices.** Everything is B-sources, capacitors and SW switches. Loos's relay uses digital
A-devices for the timing; here the timing comes from continuous states, so the model can be exported
to ngspice/QSpice (replace `limit()` by min/max there).

## Presets

The two "typical" columns are read off the makers' distribution graphs (±2–3 % reading accuracy).
Where the maker publishes only limits, the limit is used; see Provenance.

| subckt | part | Vnom | R Ω | L / Lc H | pu / do | Top / Trel ms | Ron mΩ | pol |
|---|---|---|---|---|---|---|---|---|
| `TQ2_5V` | Panasonic TQ2-5V | 5 | 178 | 0.25 / 0.35 | 0.64 / 0.22 | 2.2 / 1.0 | 30 | 1 |
| `TQ2_12V` | Panasonic TQ2-12V | 12 | 1028 | 1.44 / 2.0 | 0.64 / 0.22 | 2.2 / 1.0 | 30 | 1 |
| `TQ2_L2_5V` | Panasonic TQ2-L2-5V, 2-coil latching | 5 | 125 per coil | 0.175 / 0.245 | set/reset 0.57 | 2 / 2 | 30 | — |
| `G5V_2_DC5` | Omron G5V-2 5 VDC | 5 | 50 | 0.09 / 0.11 | 0.6 / 0.2 | 3.5 / 0.6 | 30 | 0 |
| `G5V_2_DC12` | Omron G5V-2 12 VDC | 12 | 288 | 0.47 / 0.74 | 0.6 / 0.2 | 3.5 / 0.6 | 30 | 0 |
| `G5V_2_DC24` | Omron G5V-2 24 VDC | 24 | 1152 | 1.98 / 2.68 | 0.6 / 0.2 | 3.5 / 0.6 | 30 | 0 |
| `G6K_2_DC5` | Omron G6K-2 5 VDC | 5 | 237 | 0.2 / 0.28 | 0.68 / 0.22 | 1.5 / 1.5 | 50 | 1 |
| `G6K_2_DC12` | Omron G6K-2 12 VDC | 12 | 1315 | 1.12 / 1.57 | 0.68 / 0.22 | 1.5 / 1.5 | 50 | 1 |
| `F40_52_12V` | Finder 40.52.x.012 (0.65 W) | 12 | 220 | 0.7 / 0.98 | 0.73 / 0.1 | 7 / 3 | 20 | 0 |
| `F40_52_24V` | Finder 40.52.x.024 (0.65 W) | 24 | 900 | 2.9 / 4.0 | 0.73 / 0.1 | 7 / 3 | 20 | 0 |

## Provenance

Datasheets read on 2026-09-14. "p." is the PDF page.

**Panasonic TQ relays**, catalogue ASCTB14E 201911,
<https://mediap.industry.panasonic.eu/assets/download-files/import/ds_61020_en_tq.pdf>
- **Coil R and current.** p.3, "1) Single side stable": 5 V → 28.1 mA / 178 Ω; 12 V → 11.7 mA / 1,028 Ω.
  Pick-up ≤ 75 %V, drop-out ≥ 10 %V. The 2-coil latching table on p.4: 5 V → 40 mA / 125 Ω per
  coil; set and reset ≤ 75 %V.
- **Limits.** p.4 "Specifications": initial contact resistance max 50 mΩ. Operate [set] time max 3 ms;
  release [reset] time max 3 ms without diode.
- **pu = 0.64, do = 0.22.** Midpoints of p.9 fig. 3/4 (TQ2SA-12V, initial): pick-up 60–67 %,
  drop-out 17–30 %.
- **Top = 2.2 ms, Trel = 1.0 ms.** p.9 fig. 6 "Operate/release time" at 100 %V: operate band about
  2.1–2.45 ms, release about 0.9–1.15 ms.
- **L = 0.25 H (5 V) / 1.44 H (12 V): fitted.** The same fig. 6 gives the operate time about 2.95 ms at
  80 %V and about 1.78 ms at 120 %V. In this model the difference is (ln 5 − ln 2.14)·τ = 0.85·τ, so
  τ = L/R ≈ 1.4 ms, and L = τ·R. The bench reproduces the graph at 80/100/120 %V.
- **Lc = 1.4·L: estimate.** The G5V-2 median Lc/L; Panasonic publishes no inductance.

**Panasonic TQ relays, older edition** ("MOST ADVANCED POLARIZED RELAY"),
<https://media.digikey.com/pdf/Data%20Sheets/Panasonic%20Electric%20Works%20PDFs/TQ%20Series.pdf>
- **Typical times.** p.1: operate [set] approx. 2 ms, release approx. 1 ms, reset approx. 2 ms.
  Used for the TQ2-L2 Top = Trel = 2 ms.
- **pset = prst = 0.57.** p.5 fig. 8, set/reset voltage distribution (TQ2-L2-12V, 35 pcs): 40–70 %,
  peak 55–60 %.
- **Ron = 30 mΩ.** p.5 fig. 10, contact resistance distribution (TQ2-12V, 120 contacts): 27–34 mΩ,
  peak ≈ 30 mΩ.
- **TQ2-L2 L = 0.175 H, Lc = 0.245 H.** τ = 1.4 ms as fitted above, times 125 Ω; the coils are the
  same construction.

**Omron G5V-2**, <https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5v_2.pdf>
- **Limits.** p.1 "Characteristics": contact resistance 50 mΩ max, operate 7 ms max, release 3 ms max.
- **Coil ratings.** p.2: 5 V → 100 mA / 50 Ω; 12 V → 41.7 mA / 288 Ω; 24 V → 20.8 mA / 1,152 Ω.
  Must operate 75 % max, must release 5 % min.
- **pu = 0.6, do = 0.2.** p.3 "Dial pulse test", initial values: must operate ≈ 60 %, must release
  ≈ 20 % of rated voltage.
- **Ron = 30 mΩ.** p.3 dial pulse test, initial contact resistance ≈ 30 mΩ.
- **Top = 3.5 ms, Trel = 0.6 ms.** p.3, must operate/release time distribution (G5V-2 12 VDC,
  50 pcs): operate 3.3–3.8 ms, release 0.5–0.7 ms.
- **pol = 0.** p.4: "No coil polarity".

**Omron G5V-2, 1997 catalogue** (Cat. No. GC RLY6 9/97),
<https://datasheet.octopart.com/G5V-2-DC12-Omron-datasheet-111017.pdf>
- **L / Lc.** p.2, "Coil inductance (ref. value)", armature OFF / ON: 5 V 0.09 / 0.11 H,
  12 V 0.47 / 0.74 H, 24 V 1.98 / 2.68 H.
- **Generic defaults.** L/R = 1.6 ms and Lc/L = 1.4 come from this table.

**Omron G6K**, <https://omronfs.omron.com/en_US/ecb/products/pdf/en-g6k.pdf>
- **Coil ratings and limits.** p.3: 5 V → 21.1 mA / 237 Ω; 12 V → 9.1 mA / 1,315 Ω. Must operate
  80 % max, must release 10 % min. Contact resistance 100 mΩ max; operate and release 3 ms max.
- **pu = 0.68, do = 0.22.** p.4 "Ambient temperature vs. must operate or must release voltage" at
  23 °C and "Electrical durability" initial: must operate ≈ 65–70 %, must release ≈ 20–23 %.
- **Ron = 50 mΩ.** p.4 contact resistance, initial ≈ 50 mΩ.
- **Top = Trel = 1.5 ms.** p.5, must operate/release time distribution (G6K-2G, 50 pcs):
  1.3–1.7 ms, peak 1.5 ms.
- **pol = 1.** p.6: coil marked +/−, "Check carefully the coil polarity of the Relay".
- **L = 0.2 H (5 V) / 1.12 H (12 V): estimate.** In the two relays whose L is known, the current rise
  takes 43 % (G5V-2) to 65 % (TQ2) of the operate time. Taking 60 % gives ti ≈ 0.9 ms, so
  τ = 0.9 ms / ln(1/0.32) ≈ 0.8 ms and L = τ·R. Lc = 1.4·L.

**Finder 40 series**, catalogue S40EN (VIII-2026), <https://cdn.findernet.com/app/uploads/S40EN.pdf>
- **Type 40.52 data.** p.3: DC operating range (0.73…1.5)·UN, must drop-out 0.1·UN,
  operate/release time 7/3 ms, rated DC power 0.65 W.
- **DC coil data (0.65 W).** p.9: 12 V (code 9.012) → Umin 8.8 V, 220 Ω, 55 mA;
  24 V (9.024) → 17.5 V, 900 Ω, 27 mA.
- **pu = 0.73, do = 0.1 are the guaranteed limits.** Finder publishes no typical values, so a real
  part picks up earlier and drops out later than this preset.
- **Ron = 20 mΩ: estimate.** The catalogue gives no contact resistance. Chosen for AgNi power
  contacts, between the signal relays above and a milliohm-class contact.
- **L = 0.7 H (12 V) / 2.9 H (24 V): estimate,** by the same 60 % rule: τ = 0.6·7 ms / ln(1/0.27)
  ≈ 3.2 ms. Lc = 1.4·L.

**Definitions.**
- Operate time is taken as coil on → NO makes.
- Release time is taken as coil off → NC makes, for an unsuppressed coil, with the datasheets'
  "without diode".
- If a maker measures release to NO-break instead, the model's NO breaks
  (xno − 0.02 − xnc)·Tmoff ≈ 0.68·Trel earlier than that.

**Inspiration**, no text copied:
- R. Loos, `Relay_2A2B` (`sources/loosweb-relay/raw/downloads/Relay_2A2B.sub`): Von/Voff
  hysteresis, break-before-make from a fly time; his timing uses A-devices.
- H. Sennewald, `RLY_SPDT0` (`sources/ltwiki/extracted/lib/lib/sub/relay.lib`): current-sensing coil
  driving SW contacts.
- Owner's guide `docs/user/guia_componentes_audio_spice.pdf` p.7:
  - a latching relay needs memory and command pulses, and is a different block from a monostable one;
  - a coil diode changes the release;
  - TQ2-5V is the documented signal-relay example.
- The flux-linkage coil, the flux-based thresholds and the smooth bistable are new here.

## Limits (not modelled)

- Contact bounce, arcing, contact capacitance and crosstalk.
- Coil heating: R rises about +0.4 %/K (TQ p.13), and pick-up and release voltage shift with ambient
  temperature.
- AC coils.
- Magnetic coupling between the two coils of `relay_latch2_dpdt`: each coil is its own inductor.
  The pull is the difference of the fluxes.
- Force versus pulse energy. The minimum set pulse simply follows from ti plus travel. A pulse that
  ends before the flip leaves the relay where it was.
- Tolerance spread: ±10 % coil R, and the pick-up distribution. Use `.step` on `pu`, `R`…

## Bench results

`python3 bench_relay.py` (LTspice 17, sandbox off): **47/47 checks pass**, exit 0.

| check | got | want | tol |
|---|---|---|---|
| pick-up voltage, slow ramp (NO makes), V | 7.806 | 7.8 | 0.03 |
| drop-out voltage, slow ramp (NC makes), V | 2.393 | 2.4 | 0.03 |
| non-polarised at −12 V: NO closed (V on 1k) | 0.99995 | 0.99995 | 1e-3 |
| pol=1 at −12 V / TQ2_5V at −5 V: NO open | 1e-6 / 1e-6 | 0 | 1e-3 |
| operate time at Vnom, ms | 4.018 | 4.0 | 0.08 |
| break-before-make gap on operate / release, ms | 1.856 / 1.599 | 1.856 / 1.600 | 0.05 |
| release, 60 V clamp ("no diode"), ms | 2.395 | 2.391 (current decay + Trel) | 0.08 |
| flyback peak, 60 V clamp, V | 60.10 | 60 | 1.5 |
| release with 1N4148 across the coil, ms | 5.173 | 5.148 (RK4 of L di/dt = −(Ri + Vd(i)) + Trel) | 0.12 |
| flyback peak with diode, V | 12.78 | 12.75 | 0.3 |
| **diode lengthens the release** | **2.16×** | | |
| Ron / Roff | 0.050 Ω / 0.999 GΩ | 0.05 / 1 | |
| latch: set / reset time, ms | 3.020 / 3.021 | 3 / 3 | 0.08 |
| latch: holds with no current; 50 % pulse ignored; state0=1 at .op | ok | | |
| TQ2-L2-5V: coil current, mA | 39.53 | 40 (p.4) | 0.5 |
| TQ2-L2-5V: set / reset time, ms | 2.017 / 2.072 | 2 / 2 | 0.1 |
| coil current at Vnom, mA: TQ2_5V / TQ2_12V | 28.10 / 11.69 | 28.1 / 11.7 | 1.5 % |
| … G5V_2 DC5 / DC12 / DC24 | 100.0 / 41.68 / 20.86 | 100 / 41.7 / 20.8 | 1.5 % |
| … G6K_2 DC5 / DC12 | 21.10 / 9.14 | 21.1 / 9.1 | 1.5 % |
| … F40_52 12V / 24V | 54.54 / 26.68 | 55 / 27 | 1.5 % |
| operate time, ms: TQ2 / G5V_2 / G6K_2 / F40_52 | 2.218 / 3.518 / 1.514 / 7.027 | 2.2 / 3.5 / 1.5 / 7 | 4 % |
| TQ2-12V operate time at 80 / 100 / 120 %V, ms | 3.049 / 2.218 / 1.850 | graph 2.8–3.1 / 2.1–2.45 / 1.7–1.85 | band |
| .ac through NC, max gain error | 2.5e-7 | 0 | 1e-6 |
| demo: OUT = CLEAN before, = LEAD after the footswitch, max err V | 1.5e-7 / 1.5e-7 | 0 | 1e-3 |

## Demo

`demo_relay.asc` is an amp channel switch:
- A footswitch pulse (V2) drives a 2N3904 that energises a `G5V_2_DC12`, with a 1N4148 across the coil.
- Pole 1 moves OUT from CLEAN (1 kHz) to LEAD (3 kHz).
- The relay operates about 3.5 ms after the press. On release the diode delays the NC by the coil
  decay.
- Netlist it with `python3 tools/ltspice/asc2net.py components/relay/demo_relay.asc`
  (`LTspice -netlist` hangs on this machine).
