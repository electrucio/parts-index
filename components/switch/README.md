# switch — toggles, footswitches, on-off-on, rotary selectors, switched jacks

Mechanical switches for pedal and amp schematics. Each pole is a separate element.
Each contact knows which positions close it, so every lug of a DPDT or 3PDT is wired
explicitly. A position can be static (`pos=`), a single timed move (`tsw`, `pos2`), or
follow a node (`_vc`). A move passes through a break-before-make gap, which is where true-bypass
pops and selector clicks come from.

Files: `switch.sub`, `make_symbols.py` (writes the 15 `.asy` and `demo_switch.asc`),
`bench_switch.py`, this README.

## Subckts and pins

Pins follow the lugs. A changeover pole is throw 1 – common – throw 2, the three lugs of
a toggle pole in a row. The 3PDT is lugs 1…9, with 2, 5 and 8 the commons.

| subckt | pins | positions |
|---|---|---|
| `sw_spst` | A B | `pos` 0 open, 1 closed (default 1) |
| `sw_spdt` | T1 COM T2 | 0 COM–T1, 1 COM–T2 |
| `sw_dpdt` | A1 AC A2 B1 BC B2 | 0 (A1, B1), 1 (A2, B2) |
| `sw_3pdt` | A1 AC A2 B1 BC B2 C1 CC C2 = lugs 1…9 | 0: 2-1 5-4 8-7; 1: 2-3 5-6 8-9 |
| `sw_spdt_ctr`, `sw_dpdt_ctr` | as spdt / dpdt | on-off-on: 0 T1, 1 centre off, 2 T2 |
| `sw_rot1p3`, `sw_rot1p4`, `sw_rot1p6`, `sw_rot1p12` | COM P1 … PN | 1…N; `npos` = end stop; `mbb` shorting |
| `jack_mono_sw` | T S TN PT PS | `plug` 0: T–TN closed; 1: PT–T, PS–S, TN open |
| `jack_trs` | T R S PT PR PS | `plug` 0 none; 1 mono plug (R–S shorted: battery on); 2 stereo plug |
| `sw_spdt_vc`, `sw_dpdt_vc`, `sw_3pdt_vc` | … + CTRL | position = V(CTRL): 0 / 1, in between = in transit |

- **Jacks.** T/R/S/TN are the jack lugs, and PT/PR/PS are the plug (cable) side, where the guitar or
  amp connects.
- **Symbols.** Every `.asy` uses the relay's pole geometry: throw 1 at (ox,16), throw 2 at
  (ox+64,16), COM at (ox+32,112), with poles every 96 units. The rotary contacts sit every 32 units
  on top, with COM at the bottom. The jacks have the plug side on the left.

## Parameters

| param | meaning | default |
|---|---|---|
| `pos` | position (rounded, clamped to the valid range) | 0 (spst 1, rotary 1) |
| `pos2` | position after the move; −1 = "the other one" | −1 |
| `tsw` | time of the move; 1e9 = never (static switch) | 1e9 |
| `tmove` | duration of the move (lever / actuator transit) | 2m (jacks 50m) |
| `Ron` | contact resistance | toggles 10m, 3PDT 30m, rotary 20m, jacks 30m |
| `Roff` | open-contact (insulation) resistance | toggles 1G, 3PDT 100Meg, rotary 1G, jacks 10G |
| `npos`, `mbb` | rotary end stop (≤ N); 1 = shorting (make-before-break) | N, 0 |

`pos2 = −1` means:
- a two-position switch toggles;
- an on-off-on switch goes to the opposite side, through the centre;
- a jack's plug goes in or out;
- a rotary switch stays where it is.

## Model

- **Position node.** p(t) = pos until `tsw`, then a linear move to `pos2` over `tmove`.
- **Contacts.** Each contact is a voltage-controlled switch (`SW`) that is closed while p is inside
  its window.
  - Throw k of a selector: |p − k| < 0.25. With `mbb=1` the window is 0.6, so neighbours overlap.
  - Between two positions nothing is closed. A stomp on the 3PDT leaves input and output open for
    tmove/2.
  - A rotary move sweeps through the positions in between, like the real knob.
- **Jacks.** Insertion is modelled as a move along p:
  - the plug sleeve makes at 0.25;
  - the tip spring lifts off TN at 0.6;
  - the tip makes at 0.75.

  A mono plug in a TRS jack bridges the ring spring to the sleeve (R–PS–S, 2·Ron). That is the
  pedal battery switch.
- **No A-devices, no `if()` at run time.** Positions are resolved at `.param` level; transits use
  `limit()`.

## Provenance

- **Toggles (Ron = 10 mΩ, Roff = 1 GΩ).** C&K "7000 Series Miniature Toggle Switches"
  (rev. Oct 2003), PDF p.1:
  <https://media.digikey.com/pdf/Data%20Sheets/C&K/7000_Series_Mini_Toggle_Rev_Oct_2003.pdf>.
  - "Contact resistance: below 10 mΩ typ. initial @ 2-4 V DC, 100 mA".
  - "Insulation resistance: 10⁹ Ω min."
- **3PDT footswitch (Ron = 30 mΩ, Roff = 100 MΩ, lug map).** Aion FX "3PDT Stomp Switch"
  datasheet, p.1: <https://aionfx.com/app/files/datasheets/aionfx-3pdt-stomp-switch.pdf>.
  - Terminal connections "2-1, 5-4, 8-7 ON / 2-3, 5-6, 8-9 ON".
  - "Insulation resistance (minimum) 100MΩ 500VDC".
  - Contact resistance is printed "30MΩ" maximum. This is taken as 30 mΩ: a 30 MΩ closed contact
    could not pass a guitar signal, and would be smaller than the 100 MΩ open-contact insulation on
    the same sheet.
- **Rotary (Ron = 20 mΩ, Roff = 1 GΩ, npos, mbb).** Lorlin "CK Rotary Switch" electrical and
  mechanical specification:
  <https://www.hificollective.co.uk/sites/default/files/2022-06/lorlin-selector-switches-datasheet.pdf>.
  - p.1: "Contact Resistance <20 mΩ (Initial)", "Insulation Resistance >999 MΩ at 500V dc".
  - p.1: "Shorting (make before break …) or non-shorting (break before make)" and "Moulded stop or
    adjustable stops to restrict number of positions", which is what `mbb` and `npos` model.
  - p.3: CK1049 is the 1-pole 12-position, PCB, silver, non-shorting version; `sw_rot1p12` with the
    defaults is that part.
- **Jacks (Ron = 30 mΩ, Roff = 10 GΩ).** Switchcraft 12A (switched mono, "tip is shunt"). The
  "Tech Specs" listed on AV-iQ
  (<https://www.av-iq.com/avcat/ctl1642/index.cfm?manufacturer=switchcraft&product=12a>) give:
  - "Commercial Jacks - .030 ohms maximum" (initial);
  - insulation 10,000 MΩ;
  - 1 A at 25 V DC.

  This is a reseller page reproducing Switchcraft's figures. Switchcraft's own catalogue (EDG41.pdf)
  was too large to fetch here.
- **tmove = 2 ms: estimate.** No maker publishes a transfer time. A snap-action lever or stomp moves
  its contact in a few milliseconds. 2 ms makes the break-before-make gap (1 ms) visible in a `.tran`
  without slowing it down. Change it if you have a measurement.
- **Jack tmove = 50 ms and the insertion order: estimate.** A plug pushed by hand at about 0.2 m/s
  travels about 10 mm from sleeve contact to seated. The sleeve spring is at the panel and the tip
  spring at the far end, hence sleeve → TN break → tip.

**Inspiration**, no text copied:
- H. Sennewald's parameter-selected switches in `sources/ltwiki/extracted/lib/lib/sub/Pote.lib`
  (`sw_3_to_1`, `1P3T`, `sw_5_to_1`, `spdt`, `dpdt`);
- Bordodynov's switch symbols in `sources/bordodynov/extracted/lib/sym/ZZZ/switch/`;
- the owner's guide `docs/user/guia_componentes_audio_spice.pdf` p.7: separate poles and contact
  sequence for DPDT/3PDT, switched jacks and selectors.

## Limits (not modelled)

- Contact bounce: a real stomp chatters for about a millisecond after the gap.
- Contact capacitance and crosstalk between poles.
- Wiper noise and wear.
- The plug tip scraping the sleeve spring on its way in, the hum and pop of plugging live.
- Momentary footswitches: use `sw_3pdt_vc`, or `pos2` with a second instance.

## Bench results

`python3 bench_switch.py` (LTspice 17, sandbox off): **67/67 checks pass**, exit 0.

| check | got | want |
|---|---|---|
| every position of spst, spdt, dpdt, spdt_ctr, dpdt_ctr, 3pdt (14 cases): only the listed lugs closed (1 V into 1k: 1000/(1000+Ron)), all others at the Roff leakage | ok | Aion p.1 lug table for the 3PDT |
| sw_rot1p12, positions 1…12: only Pk closed | 12/12 ok | |
| rounding / end stops: pos=2.4 → P2, pos=0 → P1, pos=15 → P12, pos=8 npos=5 → P5 | 2 / 1 / 12 / 5 | 2 / 1 / 12 / 5 |
| sw_rot1p3/4/6 at pos=N | N | N |
| Ron: spst / spdt / 3pdt / rot | 10 / 10 / 30 / 20 mΩ | defaults |
| Roff: spst / spdt / 3pdt / rot | 0.999 / 0.999 GΩ / 99.99 MΩ / 0.999 GΩ | 1 G / 1 G / 100 M / 1 G |
| 3PDT stomp at 10 ms, tmove 2 ms: lug 1 opens / lug 3 makes | 10.499 / 11.499 ms | 10.5 / 11.5 |
| 3PDT all-open gap (break-before-make); poles B, C in step with A | 1.000 ms; 0 | 1.0; 0 |
| rotary 1→2: non-shorting gap / shorting overlap / P3 untouched | 1.000 / 0.400 ms / 1e-6 V | 1.0 / 0.4 / 0 |
| on-off-on flip 0→2: centre-off interval | 1.500 ms | 1.5 |
| sw_3pdt_vc with two stomps (PWL on CTRL) | engaged, then bypass again | |
| jack_mono_sw: no plug T–TN closed, plug tip open; plugged TN open, tip on T | ok (0.99997 V / 1e-7 V) | |
| jack_trs battery current (9 V, 10k): no plug / mono plug / stereo plug | 1.7e-6 / 0.89999 / 1e-5 mA | 0 / 9/(10k+2·Ron) / 0 |
| `.step param` on a rotary position (2, 5) | P2, P5 closed | |
| .ac through a closed contact, gain error | 2.5e-7 | 0 |
| demo bypassed: OUT = IN (max err) | 1.2e-8 V | 0 |
| demo bypassed: effect input sees only insulation leakage | 1.980 mV | 0.2 V·1M/101M = 1.980 mV |
| demo engaged: OUT = effect output; gain | 1.2e-8 V; 2.0005 | 0; 2·H(440 Hz) = 1.9999 |
| demo LED current bypassed / engaged | 7.7e-5 / 1.532 mA | 0 / ≈(9 − Vf)/4.7k |

## Demo

`demo_switch.asc` is a 3PDT true bypass with an LED, in the usual pedal wiring:
- **Lug 2** is IN and **lug 5** is OUT.
- **Lugs 1 and 4** are linked for the bypass.
- **Lugs 3 and 6** go to the effect's input and output.
- **Lug 8** is the LED cathode, and **lug 9** is ground.

The effect is a gain-of-2 stage biased at 4.5 V, with a 100 nF output cap and a 1 MΩ pull-down, so
engaging it does not pop. `XFS` has `pos=0 tsw=20m`: bypassed, then stomped at 20 ms. Netlist it with
`python3 tools/ltspice/asc2net.py components/switch/demo_switch.asc`.
