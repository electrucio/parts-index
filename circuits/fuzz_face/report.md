# Reference circuit: fuzz_face

Silicon NPN Fuzz Face, 9 V; 100k feedback from Q2 emitter to Q1 base.

Expected (design references):

- `Vc2_mean_V` in [2.0, 3.6] — from the DC loop: Ic2 ≈ (Vbe1 + 100k·Ic1/β1)/1k with Ic1 ≈ (9−1.3)/33k, so Vc2 ≈ 9 − 8.67k·Ic2 ≈ 2.3–3.4 V for Vbe 0.6–0.7 V and β 150–400. The 4.5 V builders aim for needs a bias trim or a lower-gain Q2; the spread between models here is the hFE sensitivity of this circuit

| part | candidate | source | preferred | Vc2_mean_V | out_asym | out_pp_V | in range |
|---|---|---|---|---|---|---|---|
| BC108 | `bordodynov.lib` | bordodynov |  | 2.42 | 0.67 | 7.771 | yes |
| BC108 | `bordodynov-2.lib` | bordodynov |  | 2.45 | 0.67 | 7.794 | yes |
| BC108 | `bordodynov-3.lib` | bordodynov |  | 2.43 | 0.66 | 7.832 | yes |
| BC108 | `kicad-spice-library.lib` | kicad-spice-library | ★ | 2.71 | 0.61 | 7.887 | yes |
| BC108 | `kicad-spice-library-2.lib` | kicad-spice-library |  | 3.1 | 0.55 | 7.988 | yes |
| BC108 | `kicad-spice-library-3.lib` | kicad-spice-library |  | 3.1 | 0.55 | 7.988 | yes |
| BC109C | `bordodynov.lib` | bordodynov |  | 2.43 | 0.66 | 7.832 | yes |
| BC109C | `kicad-spice-library.lib` | kicad-spice-library | ★ | 2.72 | 0.61 | 7.902 | yes |
| 2N3904 | `onsemi.lib` | onsemi | ★ | 2.3 | 0.65 | 7.732 | yes |
| 2N3904 | `central-semi.lib` | central-semi |  | 2.37 | 0.68 | 7.74 | yes |
| 2N3904 | `ltspice-native.lib` | ltspice-native |  | 2.64 | 0.61 | 7.901 | yes |
| 2N3904 | `cordell.lib` | cordell |  | 2.38 | 0.67 | 7.73 | yes |
| 2N3904 | `cordell-2.lib` | cordell |  | 2.4 | 0.67 | 7.737 | yes |
| 2N3904 | `duncanamps.lib` | duncanamps |  | 3.0 | 0.56 | 7.89 | yes |
| 2N5088 | `central-semi.lib` | central-semi | ★ | 3.15 | 0.55 | 8.005 | yes |
| 2N5088 | `bordodynov.lib` | bordodynov |  | 2.51 | 0.66 | 7.827 | yes |
| 2N5088 | `bordodynov-2.lib` | bordodynov |  | 2.8 | 0.58 | 7.958 | yes |
| 2N5088 | `ltwiki.lib` | ltwiki |  | 2.51 | 0.66 | 7.827 | yes |
| 2N5088 | `ltwiki-2.lib` | ltwiki |  | 2.8 | 0.58 | 7.958 | yes |
| 2N5088 | `spiceypedals.lib` | spiceypedals |  | 1.99 | 0.67 | 7.775 | NO |

Netlists: the `.net` files next to this report (paths relative to the repo).
