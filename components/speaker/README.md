# speaker — loudspeaker impedance from Thiele-Small parameters

`speaker.sub` gives the electrical impedance a loudspeaker presents to an amplifier:

- the voice-coil DC resistance;
- a lossy ("semi-") inductance for the voice coil;
- the motional impedance of the cone resonance, from the Thiele-Small parameters;
- optionally, a closed box.

Presets cover Jensen and Eminence guitar speakers from the makers' T/S data. The
Celestion presets take Re and Fs from Celestion, with Qms and Qes from a published
third-party measurement of the same speakers. The mix is explained below.

## Subckt and pins

| subckt | pins | parameters (defaults) |
|---|---|---|
| `speaker` | P N | `Re`=6.4, `Fs`=80, `Qms`=5, `Qes`=1, `Le`=0.7m, `n`=0.7, `Vb`=0, `Vas`=30m |
| `SPK_<model>_<ohms>` (17 presets) | P N | `Vb`=0 (closed box, m³), `n` (voice-coil exponent) |

P is the terminal that pushes the cone out with a positive voltage.

The symbol (`make_symbols.py`) is the usual magnet-and-cone drawing facing right. P (+)
is at (0,32) and N at (0,96).

| name | meaning |
|---|---|
| `Re` | voice-coil DC resistance |
| `Fs` | free-air resonance |
| `Qms`, `Qes` | mechanical and electrical Q |
| `Le` | voice-coil inductance at 1 kHz. It is defined as Im{Zcoil}/ω at 1 kHz, which is how makers quote "Le @ 1 kHz". |
| `n` | semi-inductor exponent: Zcoil ∝ (jω)ⁿ. n = 1 is a pure inductor; eddy losses make n < 1. |
| `Vb`, `Vas` | closed-box volume (0 = free air or infinite baffle), and compliance-equivalent volume |

## Equations

Z = Re + Zcoil + Zmot.

**Motional part.** A parallel RLC: Res = Re·Qms/Qes, Lces = Re/(2π·Fs·Qes),
Cmes = Qes/(2π·Fs·Re). It resonates at Fs with a peak of **Re·(1+Qms/Qes)**, plus the
small voice-coil term at Fs.

**Closed box.** The air spring stiffens the suspension, so Lces becomes
Lces/(1+Vas/Vb). The resonance moves to Fc = Fs·√(1+Vas/Vb).

**Voice coil.** Zcoil = K·(jω)ⁿ, following W. M. Leach Jr., "Loudspeaker voice-coil
inductance losses", JAES 50(6), 2002. It is scaled so that Im{Zcoil(1 kHz)} = 2π·1 kHz·Le
exactly. It is built from series R‖L cells whose time constants are spaced two per
decade from 0.2 Hz to 2 MHz, with R_k ∝ τ_k⁻ⁿ; the infinite tails beyond are summed
exactly, as one series L and one extra cell. Every cell is a short at DC, so R(DC) = Re.
From 20 Hz to 20 kHz the phase stays within 0.03° of n·90° and the magnitude slope
within 0.001 of n (bench).

## Presets and provenance

T/S data were fetched on 2026-09-14. `spk_presets.py` holds every number and its
source; `make_symbols.py` writes the preset block into the `.sub`.

| preset | maker data (URL) | Re Ω | Fs Hz | Qms | Qes | Le mH | Vas l | source of Qms/Qes/Le |
|---|---|---|---|---|---|---|---|---|
| SPK_P10R_4 / _8 / _16 | Jensen P10R <https://www.jensentone.com/specification-sheet/36> | 3.6 / 6.68 / 12.3 | 99 / 97 / 99 | 23.8 / 14.83 / 23.4 | 1.45 / 1.82 / 1.94 | 0.35 / 0.54 / 0.75 | 29 / 27.4 / 29.5 | maker |
| SPK_P12Q_8 / _16 / _32 | Jensen P12Q <https://www.jensentone.com/specification-sheet/40> | 5.6 / 12.45 / 25.2 | 90.5 / 90 / 85.6 | 11.57 / 12.68 / 10.94 | 2.46 / 2.81 / 3.33 | 0.67 / 0.60 / 1.59 | 39.5 / 41.2 / 46.6 | maker (see note 1) |
| SPK_C12N_8 / _16 | Jensen C12N <https://www.jensentone.com/specification-sheet/16> | 6.05 / 12.5 | 113 / 110 | 7.52 / 6.84 | 1.18 / 1.25 | 0.90 / 1.55 | 22.6 / 28 | maker (see note 2) |
| SPK_LEGEND1258_8 | Eminence Legend 1258 <https://eminence.com/products/legend_1258> | 7.44 | 94 | 6.15 | 1.18 | 0.7 | 32.5 | maker |
| SPK_V30_8 / _16 | Celestion Vintage 30 <https://celestion.com/productpdf.php?id=888> | 7.3 / 12.9 | 75 | 1.398 | 0.838 | 0.7 / 1.24 | – | Munro VINT30; Le est |
| SPK_G12M_8 / _16 | Celestion G12M Greenback <https://celestion.com/productpdf.php?id=899> | 6.7 / 13.1 | 75 | 1.273 | 0.796 | 0.7 / 1.37 | – | Munro G12M; Le est |
| SPK_G12H_8 / _16 | Celestion G12H Anniversary <https://celestion.com/productpdf.php?id=900> | 6.7 / 13.1 | 85 | 1.267 | 0.634 | 0.7 / 1.37 | – | Munro G12H100 (see note 3); Le est |
| SPK_G12T75_8 / _16 | Celestion G12T-75 <https://celestion.com/productpdf.php?id=898> | 6.77 / 12.9 | 85 | 1.462 | 0.731 | 0.7 / 1.33 | – | Munro G12T75; Le est |

### Notes and estimates

1. **P12Q Qes.** The spec sheet lists Qes 2.46, which is consistent with its
   Qts 2.03 = Qms·Qes/(Qms+Qes). The P12Q product page lists 3.33, which is not
   consistent. The spec sheet value is used.
2. **C12N 4 Ω.** The C12N sheet's 4 Ω column gives Re 6.5 Ω, impossible for a 4 Ω
   speaker, so that version is left out.
3. **Celestion Qms/Qes.** Celestion publishes only Re and Fs for its guitar speakers
   (the datasheets above). Its blog explains that the parameters "are measured at very
   small signal levels" and have little relevance to guitar speakers
   (<https://celestion.com/blog/thinking-of-using-thiele-small-parameters-to-design-a-guitar-speaker-cab-think/>).
   No independent free-air measurement was found.

   The Q values here are therefore derived from Duncan Munro's 1997 impedance networks
   of the same speakers, `sources/ltwiki/extracted/lib/lib/sub/speaker.lib` (subckts
   VINT30, G12M, G12T75, G12H100). Munro describes them as reflecting "the change of
   impedance as presented to the amplifier". Each has a parallel R-L-C (RD1, LD1, CD1)
   behind RL, which converts as Qms = RD1·√(CD1/LD1) and Qes = RL·√(CD1/LD1).

   Munro's networks resonate at 71.2 / 75.0 / 81.6 / 81.6 Hz, close to Celestion's Fs.
   Their Qms of about 1.3–1.5 are far below the small-signal Qms of the Jensen and
   Eminence data (6–24): the impedance peaks are 2.6–3.0× Re instead of 5–15×. That
   fits measurement at playing level, or loaded, which is what the amplifier sees. For
   small-signal free-air behaviour, raise Qms.

   The G12H presets use Munro's G12H-100 network, the closest measured G12H, with
   Celestion's G12H Anniversary Re and Fs.
4. **Celestion Le.** Estimated at 0.7 mH for 8 Ω: the median of the maker-published 8 Ω
   Le of comparable 12″ guitar drivers above (Eminence 0.7, Jensen P12Q 0.67, C12N
   0.9 mH). The 16 Ω versions are scaled by the Re ratio, since for the same winding
   space L ∝ N² ∝ Re.
5. **`n` = 0.7 for every preset.** An estimate: a typical value for voice coils without
   shorting rings in Leach's model. No maker publishes it. Raise it towards 1 for a
   more inductive top end.
6. **Celestion Vas** is not published. The presets use a placeholder of 30 l, which is
   used only if you set `Vb` > 0.

## Bench results

Run `python3 bench_speaker.py` with the shell sandbox off. It exits 1 on any failure.
It checks, for every preset:

- R(DC) = Re;
- with the T/S part alone, the peak lies exactly at Fs with height Re·(1+Qms/Qes)
  (±0.2 %);
- with the voice coil added, the peak is still within 2 % in frequency and 3 % in
  height.

It also checks:

- the voice coil alone (Le at 1 kHz; constant phase and slope for n = 0.5, 0.7, 0.85);
- the closed-box shift;
- `.tran` against `.ac` at Fs;
- a push-pull 6V6 amp driving `OT_1760H` from `components/output-transformer` into two
  of the speakers, clean and clipped;
- the demo's pin order, via `tools/ltspice/asc2net.py`.

```
-- presets: DC resistance, resonance and peak height (.op, .ac, 1 A AC)
SPK_P10R_4 R(DC) = Re                                                                      got         3.6  want         3.6  tol 0.001r      ok
SPK_P10R_8 R(DC) = Re                                                                      got        6.68  want        6.68  tol 0.001r      ok
SPK_P10R_16 R(DC) = Re                                                                     got        12.3  want        12.3  tol 0.001r      ok
SPK_P12Q_8 R(DC) = Re                                                                      got         5.6  want         5.6  tol 0.001r      ok
SPK_P12Q_16 R(DC) = Re                                                                     got       12.45  want       12.45  tol 0.001r      ok
SPK_P12Q_32 R(DC) = Re                                                                     got        25.2  want        25.2  tol 0.001r      ok
SPK_C12N_8 R(DC) = Re                                                                      got        6.05  want        6.05  tol 0.001r      ok
SPK_C12N_16 R(DC) = Re                                                                     got        12.5  want        12.5  tol 0.001r      ok
SPK_LEGEND1258_8 R(DC) = Re                                                                got        7.44  want        7.44  tol 0.001r      ok
SPK_V30_8 R(DC) = Re                                                                       got         7.3  want         7.3  tol 0.001r      ok
SPK_V30_16 R(DC) = Re                                                                      got        12.9  want        12.9  tol 0.001r      ok
SPK_G12M_8 R(DC) = Re                                                                      got         6.7  want         6.7  tol 0.001r      ok
SPK_G12M_16 R(DC) = Re                                                                     got        13.1  want        13.1  tol 0.001r      ok
SPK_G12H_8 R(DC) = Re                                                                      got         6.7  want         6.7  tol 0.001r      ok
SPK_G12H_16 R(DC) = Re                                                                     got        13.1  want        13.1  tol 0.001r      ok
SPK_G12T75_8 R(DC) = Re                                                                    got        6.77  want        6.77  tol 0.001r      ok
SPK_G12T75_16 R(DC) = Re                                                                   got        12.9  want        12.9  tol 0.001r      ok
SPK_P10R_4 with voice coil: peak |Z| (ohm)                                                 got      62.914  want       62.69  tol 0.03r       ok
SPK_P10R_4 with voice coil: peak frequency (Hz)                                            got      98.986  want          99  tol 0.02r       ok
SPK_P10R_8 with voice coil: peak |Z| (ohm)                                                 got      61.455  want      61.111  tol 0.03r       ok
SPK_P10R_8 with voice coil: peak frequency (Hz)                                            got      96.969  want          97  tol 0.02r       ok
SPK_P10R_16 with voice coil: peak |Z| (ohm)                                                got      161.14  want      160.66  tol 0.03r       ok
SPK_P10R_16 with voice coil: peak frequency (Hz)                                           got      98.989  want          99  tol 0.02r       ok
SPK_P12Q_8 with voice coil: peak |Z| (ohm)                                                 got      32.353  want      31.938  tol 0.03r       ok
SPK_P12Q_8 with voice coil: peak frequency (Hz)                                            got      90.422  want        90.5  tol 0.02r       ok
SPK_P12Q_16 with voice coil: peak |Z| (ohm)                                                got      68.992  want       68.63  tol 0.03r       ok
SPK_P12Q_16 with voice coil: peak frequency (Hz)                                           got       89.97  want          90  tol 0.02r       ok
SPK_P12Q_32 with voice coil: peak |Z| (ohm)                                                got      108.92  want      107.99  tol 0.03r       ok
SPK_P12Q_32 with voice coil: peak frequency (Hz)                                           got      85.549  want        85.6  tol 0.02r       ok
SPK_C12N_8 with voice coil: peak |Z| (ohm)                                                 got       45.26  want      44.606  tol 0.03r       ok
SPK_C12N_8 with voice coil: peak frequency (Hz)                                            got      112.83  want         113  tol 0.02r       ok
SPK_C12N_16 with voice coil: peak |Z| (ohm)                                                got      82.002  want        80.9  tol 0.03r       ok
SPK_C12N_16 with voice coil: peak frequency (Hz)                                           got      109.83  want         110  tol 0.02r       ok
SPK_LEGEND1258_8 with voice coil: peak |Z| (ohm)                                           got      46.657  want      46.216  tol 0.03r       ok
SPK_LEGEND1258_8 with voice coil: peak frequency (Hz)                                      got      93.887  want          94  tol 0.02r       ok
SPK_V30_8 with voice coil: peak |Z| (ohm)                                                  got      19.853  want      19.467  tol 0.03r       ok
SPK_V30_8 with voice coil: peak frequency (Hz)                                             got      74.464  want          75  tol 0.02r       ok
SPK_V30_16 with voice coil: peak |Z| (ohm)                                                 got      35.083  want        34.4  tol 0.03r       ok
SPK_V30_16 with voice coil: peak frequency (Hz)                                            got      74.464  want          75  tol 0.02r       ok
SPK_G12M_8 with voice coil: peak |Z| (ohm)                                                 got      17.806  want       17.42  tol 0.03r       ok
SPK_G12M_8 with voice coil: peak frequency (Hz)                                            got      74.374  want          75  tol 0.02r       ok
SPK_G12M_16 with voice coil: peak |Z| (ohm)                                                got      34.814  want       34.06  tol 0.03r       ok
SPK_G12M_16 with voice coil: peak frequency (Hz)                                           got      74.374  want          75  tol 0.02r       ok
SPK_G12H_8 with voice coil: peak |Z| (ohm)                                                 got      20.518  want        20.1  tol 0.03r       ok
SPK_G12H_8 with voice coil: peak frequency (Hz)                                            got      84.281  want          85  tol 0.02r       ok
SPK_G12H_16 with voice coil: peak |Z| (ohm)                                                got      40.118  want        39.3  tol 0.03r       ok
SPK_G12H_16 with voice coil: peak frequency (Hz)                                           got      84.281  want          85  tol 0.02r       ok
SPK_G12T75_8 with voice coil: peak |Z| (ohm)                                               got      20.729  want       20.31  tol 0.03r       ok
SPK_G12T75_8 with voice coil: peak frequency (Hz)                                          got      84.357  want          85  tol 0.02r       ok
SPK_G12T75_16 with voice coil: peak |Z| (ohm)                                              got      39.498  want        38.7  tol 0.03r       ok
SPK_G12T75_16 with voice coil: peak frequency (Hz)                                         got      84.357  want          85  tol 0.02r       ok
SPK_P10R_4 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got       62.69  want       62.69  tol 0.002r      ok
SPK_P10R_4 T/S only: peak at Fs (Hz)                                                       got          99  want          99  tol 0.002r      ok
SPK_P10R_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got      61.111  want      61.111  tol 0.002r      ok
SPK_P10R_8 T/S only: peak at Fs (Hz)                                                       got          97  want          97  tol 0.002r      ok
SPK_P10R_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                       got      160.66  want      160.66  tol 0.002r      ok
SPK_P10R_16 T/S only: peak at Fs (Hz)                                                      got          99  want          99  tol 0.002r      ok
SPK_P12Q_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got      31.938  want      31.938  tol 0.002r      ok
SPK_P12Q_8 T/S only: peak at Fs (Hz)                                                       got        90.5  want        90.5  tol 0.002r      ok
SPK_P12Q_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                       got       68.63  want       68.63  tol 0.002r      ok
SPK_P12Q_16 T/S only: peak at Fs (Hz)                                                      got          90  want          90  tol 0.002r      ok
SPK_P12Q_32 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                       got      107.99  want      107.99  tol 0.002r      ok
SPK_P12Q_32 T/S only: peak at Fs (Hz)                                                      got        85.6  want        85.6  tol 0.002r      ok
SPK_C12N_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got      44.606  want      44.606  tol 0.002r      ok
SPK_C12N_8 T/S only: peak at Fs (Hz)                                                       got         113  want         113  tol 0.002r      ok
SPK_C12N_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                       got        80.9  want        80.9  tol 0.002r      ok
SPK_C12N_16 T/S only: peak at Fs (Hz)                                                      got         110  want         110  tol 0.002r      ok
SPK_LEGEND1258_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                  got      46.216  want      46.216  tol 0.002r      ok
SPK_LEGEND1258_8 T/S only: peak at Fs (Hz)                                                 got          94  want          94  tol 0.002r      ok
SPK_V30_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                         got      19.467  want      19.467  tol 0.002r      ok
SPK_V30_8 T/S only: peak at Fs (Hz)                                                        got          75  want          75  tol 0.002r      ok
SPK_V30_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got        34.4  want        34.4  tol 0.002r      ok
SPK_V30_16 T/S only: peak at Fs (Hz)                                                       got          75  want          75  tol 0.002r      ok
SPK_G12M_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got       17.42  want       17.42  tol 0.002r      ok
SPK_G12M_8 T/S only: peak at Fs (Hz)                                                       got          75  want          75  tol 0.002r      ok
SPK_G12M_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                       got       34.06  want       34.06  tol 0.002r      ok
SPK_G12M_16 T/S only: peak at Fs (Hz)                                                      got          75  want          75  tol 0.002r      ok
SPK_G12H_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                        got        20.1  want        20.1  tol 0.002r      ok
SPK_G12H_8 T/S only: peak at Fs (Hz)                                                       got          85  want          85  tol 0.002r      ok
SPK_G12H_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                       got        39.3  want        39.3  tol 0.002r      ok
SPK_G12H_16 T/S only: peak at Fs (Hz)                                                      got          85  want          85  tol 0.002r      ok
SPK_G12T75_8 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                      got       20.31  want       20.31  tol 0.002r      ok
SPK_G12T75_8 T/S only: peak at Fs (Hz)                                                     got          85  want          85  tol 0.002r      ok
SPK_G12T75_16 T/S only: peak |Z| = Re(1+Qms/Qes) (ohm)                                     got        38.7  want        38.7  tol 0.002r      ok
SPK_G12T75_16 T/S only: peak at Fs (Hz)                                                    got          85  want          85  tol 0.002r      ok
-- lossy voice coil alone (motional part removed): Le at 1 kHz and constant phase
n=0.7: Im(Zcoil)/w at 1 kHz = Le (mH)                                                      got         0.7  want         0.7  tol 0.002r      ok
n=0.7: coil phase 20 Hz..20 kHz, worst deviation from n*90 (deg)                           got    0.012484  want           0  tol 2.5         ok
n=0.7: |Zcoil| slope 20 Hz..20 kHz (decades/decade)                                        got     0.69998  want         0.7  tol 0.02        ok
n=0.5: Im(Zcoil)/w at 1 kHz = Le (mH)                                                      got           1  want           1  tol 0.002r      ok
n=0.5: coil phase 20 Hz..20 kHz, worst deviation from n*90 (deg)                           got     0.02119  want           0  tol 2.5         ok
n=0.5: |Zcoil| slope 20 Hz..20 kHz (decades/decade)                                        got     0.49998  want         0.5  tol 0.02        ok
n=0.85: Im(Zcoil)/w at 1 kHz = Le (mH)                                                     got         0.5  want         0.5  tol 0.002r      ok
n=0.85: coil phase 20 Hz..20 kHz, worst deviation from n*90 (deg)                          got   0.0087407  want           0  tol 2.5         ok
n=0.85: |Zcoil| slope 20 Hz..20 kHz (decades/decade)                                       got     0.84999  want        0.85  tol 0.02        ok
-- closed box: Fc = Fs sqrt(1 + Vas/Vb)
SPK_P12Q_8 in 30 l: resonance (Hz)                                                         got      137.64  want      137.75  tol 0.02r       ok
SPK_LEGEND1258_8 in 40 l: resonance (Hz)                                                   got      126.41  want      126.55  tol 0.02r       ok
SPK_C12N_8 in 20 l: resonance (Hz)                                                         got      164.69  want      164.92  tol 0.02r       ok
-- .tran vs .ac: 1 A sine at Fs through SPK_V30_16
SPK_V30_16: .tran amplitude at Fs = |Z(Fs)| from .ac (ohm)                                 got      35.077  want      35.077  tol 0.01r       ok
-- convergence: push-pull 6V6 -> OT_1760H -> SPK_C12N_8 (and SPK_V30_8), clean to clipped
6V6 PP -> 1760H -> SPK_C12N_8, drive 10 V 100 Hz: V(spk) rms                               got      5.4901  want         nan  tol info        ok
6V6 PP -> 1760H -> SPK_C12N_8, drive 60 V 100 Hz: V(spk) rms                               got      22.376  want         nan  tol info        ok
6V6 PP -> 1760H -> SPK_C12N_8, drive 60 V 1000 Hz: V(spk) rms                              got      21.115  want         nan  tol info        ok
6V6 PP -> 1760H -> SPK_V30_8, drive 10 V 100 Hz: V(spk) rms                                got      6.7937  want         nan  tol info        ok
6V6 PP -> 1760H -> SPK_V30_8, drive 60 V 100 Hz: V(spk) rms                                got      20.399  want         nan  tol info        ok
6V6 PP -> 1760H -> SPK_V30_8, drive 60 V 1000 Hz: V(spk) rms                               got      20.146  want         nan  tol info        ok
all amp runs converged                                                                     got           1  want           1  tol 0           ok
-- impedance of every preset (info): |Z| at 400 Hz, 1 kHz, 5 kHz vs nominal
SPK_P10R_4 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 4): 400 Hz                                  got      4.2272  want           4  tol info        
SPK_P10R_4   1 kHz                                                                         got      5.1087  want           4  tol info        
SPK_P10R_4   5 kHz                                                                         got      9.7587  want           4  tol info        
SPK_P10R_4 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      4.2272  want         4.5  tol [3.6,5.4]   ok
SPK_P10R_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                  got      7.6528  want           8  tol info        
SPK_P10R_8   1 kHz                                                                         got      8.9415  want           8  tol info        
SPK_P10R_8   5 kHz                                                                         got      15.892  want           8  tol info        
SPK_P10R_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      7.6528  want        8.35  tol [6.68,10.02] ok
SPK_P10R_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                                got      13.607  want          16  tol info        
SPK_P10R_16   1 kHz                                                                        got      15.259  want          16  tol info        
SPK_P10R_16   5 kHz                                                                        got      24.422  want          16  tol info        
SPK_P10R_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                               got      13.607  want      15.375  tol [12.3,18.45] ok
SPK_P12Q_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                  got      6.9452  want           8  tol info        
SPK_P12Q_8   1 kHz                                                                         got      8.7193  want           8  tol info        
SPK_P12Q_8   5 kHz                                                                         got      17.808  want           8  tol info        
SPK_P12Q_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      6.9452  want           7  tol [5.6,8.4]   ok
SPK_P12Q_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                                got      13.513  want          16  tol info        
SPK_P12Q_16   1 kHz                                                                        got      14.763  want          16  tol info        
SPK_P12Q_16   5 kHz                                                                        got       21.71  want          16  tol info        
SPK_P12Q_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                               got      13.513  want      15.562  tol [12.45,18.675] ok
SPK_P12Q_32 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 32): 400 Hz                                got      28.141  want          32  tol info        
SPK_P12Q_32   1 kHz                                                                        got      31.702  want          32  tol info        
SPK_P12Q_32   5 kHz                                                                        got      51.152  want          32  tol info        
SPK_P12Q_32 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                               got      28.141  want        31.5  tol [25.2,37.8] ok
SPK_C12N_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                  got      7.7594  want           8  tol info        
SPK_C12N_8   1 kHz                                                                         got      10.277  want           8  tol info        
SPK_C12N_8   5 kHz                                                                         got       22.89  want           8  tol info        
SPK_C12N_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      7.7594  want      7.5625  tol [6.05,9.075] ok
SPK_C12N_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                                got      15.393  want          16  tol info        
SPK_C12N_16   1 kHz                                                                        got      19.493  want          16  tol info        
SPK_C12N_16   5 kHz                                                                        got      40.795  want          16  tol info        
SPK_C12N_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                               got      15.393  want      15.625  tol [12.5,18.75] ok
SPK_LEGEND1258_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                            got      8.7153  want           8  tol info        
SPK_LEGEND1258_8   1 kHz                                                                   got      10.409  want           8  tol info        
SPK_LEGEND1258_8   5 kHz                                                                   got      19.678  want           8  tol info        
SPK_LEGEND1258_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                          got      8.7153  want         9.3  tol [7.44,11.16] ok
SPK_V30_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                   got       8.735  want           8  tol info        
SPK_V30_8   1 kHz                                                                          got      10.282  want           8  tol info        
SPK_V30_8   5 kHz                                                                          got      19.569  want           8  tol info        
SPK_V30_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                 got       8.735  want       9.125  tol [7.3,10.95] ok
SPK_V30_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                                 got      15.436  want          16  tol info        
SPK_V30_16   1 kHz                                                                         got       18.17  want          16  tol info        
SPK_V30_16   5 kHz                                                                         got       34.58  want          16  tol info        
SPK_V30_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      15.436  want      16.125  tol [12.9,19.35] ok
SPK_G12M_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                  got      8.1554  want           8  tol info        
SPK_G12M_8   1 kHz                                                                         got       9.736  want           8  tol info        
SPK_G12M_8   5 kHz                                                                         got       19.14  want           8  tol info        
SPK_G12M_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      8.1554  want       8.375  tol [6.7,10.05] ok
SPK_G12M_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                                got      15.946  want          16  tol info        
SPK_G12M_16   1 kHz                                                                        got      19.038  want          16  tol info        
SPK_G12M_16   5 kHz                                                                        got       37.43  want          16  tol info        
SPK_G12M_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                               got      15.946  want      16.375  tol [13.1,19.65] ok
SPK_G12H_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                  got      8.2807  want           8  tol info        
SPK_G12H_8   1 kHz                                                                         got      9.6572  want           8  tol info        
SPK_G12H_8   5 kHz                                                                         got      19.103  want           8  tol info        
SPK_G12H_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                                got      8.2807  want       8.375  tol [6.7,10.05] ok
SPK_G12H_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                                got      16.191  want          16  tol info        
SPK_G12H_16   1 kHz                                                                        got      18.884  want          16  tol info        
SPK_G12H_16   5 kHz                                                                        got      37.358  want          16  tol info        
SPK_G12H_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                               got      16.191  want      16.375  tol [13.1,19.65] ok
SPK_G12T75_8 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 8): 400 Hz                                got      8.2618  want           8  tol info        
SPK_G12T75_8   1 kHz                                                                       got      9.7495  want           8  tol info        
SPK_G12T75_8   5 kHz                                                                       got      19.169  want           8  tol info        
SPK_G12T75_8 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                              got      8.2618  want      8.4625  tol [6.77,10.155] ok
SPK_G12T75_16 |Z| 400 Hz / 1 kHz / 5 kHz (nominal 16): 400 Hz                              got      15.743  want          16  tol info        
SPK_G12T75_16   1 kHz                                                                      got      18.578  want          16  tol info        
SPK_G12T75_16   5 kHz                                                                      got      36.529  want          16  tol info        
SPK_G12T75_16 minimum-region |Z| at 400 Hz within [Re, 1.5 Re]                             got      15.743  want      16.125  tol [12.9,19.35] ok
-- demo_speaker.asc netlisted by asc2net = hand netlist
demo |V(spk)| @75 Hz = hand netlist                                                        got     0.81416  want     0.81416  tol 0.0001r     ok
demo |V(spk)| @1000 Hz = hand netlist                                                      got     0.70464  want     0.70464  tol 0.0001r     ok
demo |V(spk)| @5000 Hz = hand netlist                                                      got      0.8485  want      0.8485  tol 0.0001r     ok

125/125 checks passed
```

## What it does not model

- **Small-signal only.** No voice-coil heating or power compression, and no Bl(x) or
  Cms(x) non-linearity. For guitar speakers, which Celestion notes go non-linear early,
  this matters at playing level.
- **Piston model.** The cone break-up resonances that put wiggles in the impedance above
  about 2 kHz are not modelled.
- **No cabinet acoustics** beyond a lossless closed box: no open-back or baffle loading,
  no port.
- **One lumped voice-coil law** (Leach); the frequency-dependent eddy loss is not
  separated.

## Files

- `speaker.sub`: the subckt and generated presets.
- `spk_presets.py`: the numbers and their sources.
- `make_symbols.py`: writes the presets, the `.asy` files and `demo_speaker.asc`.
- `bench_speaker.py`: the bench.

The demo is a Vintage 30 16 Ω on a 1 V source with 8 Ω output resistance. The `.ac`
voltage across the speaker shows the impedance curve.

## Sources of inspiration

- The RLC-RL impedance network and its guitar-speaker benchmark:
  `sources/tamivox/raw/speaker-graphs.txt`.
- Munro's measured Celestion networks and the T/S-derived Jensen and Eminence networks:
  `sources/ltwiki/extracted/lib/lib/sub/speaker.lib`.
- The measured-impedance-table method: `sources/preamp-org/raw/ltspice-model-from-impedance-measurement-data.txt`.
- The generic Stereophile 8 Ω network: `sources/suusi-tubes/extracted/SuusiTubes_V1/Speaker.cir`.

No text was copied from these sources.
