# vu-meter — standard volume indicator (VU meter) ballistics

A VU meter as a circuit element:
- it loads the line with the standard 7.5 kΩ;
- it rectifies the signal full-wave;
- it moves a pointer with the standard's second-order ballistics: 99 % of the reading in 300 ms,
  1–1.5 % overshoot.

The output pin is the pointer deflection, so a schematic can show what the meter reads on
programme material: mixers, tape machines, compressors with meters, meter-driver circuits.

Files:
- `vu.sub`: `vu_meter`;
- `make_symbols.py`: writes `vu_meter.asy` and `demo_vu.asc`;
- `bench_vu.py`;
- this README.

## Pins and parameters

Pins: **P N DEFL**.
- P, N: the meter input. It is floating, and presents 7.5 kΩ.
- DEFL: the deflection as a voltage to ground. V(DEFL) = 1 at 0 VU; the VU reading is
  20·log10(V(DEFL)).

Symbol: a meter box with dial and needle, P at (0,16), N at (0,112), DEFL at (128,64).

| param | meaning | default |
|---|---|---|
| `Vref` | RMS sine voltage (1 kHz) reading 0 VU | 1.228 |
| `Rin` | input impedance of the indicator (meter + attenuator) | 7.5k |
| `fn` | natural frequency of the movement, Hz | 2.1505 |
| `zeta` | damping ratio | 0.8127 |

For a bare 3.9 kΩ movement used with its external 3.6 kΩ resistor, keep `Rin` = 7.5k and put
nothing in series.

## Model

    u = |v(P,N)| / (Vref · 2√2/π)          full-wave rectified coil current, 1 for a 0 VU sine
    x'' + 2ζωn x' + ωn² x = ωn² u          pointer, V(DEFL) = x

- **ζ** comes from the overshoot: ζ = −ln(os)/√(π² + ln²(os)).
  - os = 1.25 %, the middle of the standard's 1–1.5 %, gives ζ = 0.8127.
  - The limits 1 % and 1.5 % would give 0.8261 and 0.8007.
- **ωn** comes from the rise. The step response first reaches 99 % at ωn·t = 4.0536 for this ζ,
  so t99 = 300 ms gives ωn = 13.512 rad/s (fn = 2.1505 Hz). Both computed in Python; see the
  header of `vu.sub`.
- The movement integrates the rectified current. The 2f ripple at 1 kHz is 3·10⁻⁶ of the
  reading; at 35 Hz the reading is still exact (the mean of |v| is what drives it).

**No A-devices**: B-sources and capacitors.

## Provenance

- **Reference level, rise time and overshoot.** Wikipedia "VU meter"
  (<https://en.wikipedia.org/wiki/VU_meter>), quoting ANSI C16.5-1942, BS 6840 and
  IEC 60268-17:
  - 0 VU = 1.228 V RMS across 600 Ω (+4 dBu) at 1000 Hz;
  - rise time (to 99 % of the distance to 0 VU for a step to a 0 VU signal) = 300 ms;
  - overshoot 1 to 1.5 %;
  - the meter with its attenuator presents 7500 Ω;
  - frequency response 35 Hz to 16 kHz within ±0.2 to ±0.5 dB;
  - full-wave (copper-oxide) rectifier.
- **Meter impedance.** R. Elliott, Project 55 "VU and PPM audio metering"
  (<https://sound-au.com/project55.htm>): "Nominal sensitivity for 0VU is 1.228V RMS, and the
  impedance is 3.9k". That is the movement; 3.9k + 3.6k = 7.5k.
- The standards themselves (IEC 60268-17, ANSI C16.5) were not consulted directly.

## Limits (not modelled)

- **The rectifier knee.** Copper-oxide or diode rectifiers make real meters read low below about
  −10 VU; this model is linear (ideal |v|).
- The printed dial's non-linearity; pointer friction and end stops (no clamp at +3 VU or at the
  pin).
- The movement's inductance and the attenuator's frequency response; temperature.
- Only the standard instrument: consumer "VU" meters often have other ballistics (Elliott p55:
  "very few so-called VU meters come even close to the specification"). Change `fn` and `zeta`
  for those.
- The fall back to rest mirrors the rise (a linear movement). The bench reports it as a note,
  because the fall is not what the standard defines.

## Bench results

`python3 bench_vu.py` (LTspice 17.2.4, sandbox off, about 3.5 min): **10/10 checks pass**,
exit 0.

| check | model | standard |
|---|---|---|
| steady reading at 1.228 V RMS, 1 kHz | 0.99998 (0 VU) | 1 |
| time to 99 % of the reading | 299.99 ms | 300 ms (±3 %) |
| overshoot | 1.250 % | 1–1.5 % |
| input impedance | 7500 Ω | 7500 Ω |
| −10 VU / +3 VU readings | −10.001 / 2.9999 VU | −10 / +3 |
| 35 Hz / 10 kHz relative to 1 kHz | 0.0000 / −0.0008 dB | ±0.2 dB |
| demo: reading at the end of a 1 s burst | 0.99999 | 1 |

Notes:
- The fall to 1 % takes 300.0 ms.
- The demo peaks at 1.0125 at 0.499 s, 0.4 s after the burst starts.

## Demo

`demo_vu.asc`: a 1 kHz tone burst at 0 VU from 0.1 s to 1.1 s into the meter. V(defl) rises to
99 % in 0.3 s, overshoots by 1.25 %, holds 1.000, and falls back after the burst.

Netlist it with `python3 tools/ltspice/asc2net.py components/vu-meter/demo_vu.asc`.
