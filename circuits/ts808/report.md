# Reference circuit: ts808

TS808 gain stage at 9 V single supply, drive at max, 1N914 pair in feedback.

Expected (design references):

- `gain_dB_small` in [37.0, 42.0] — 1 + 551k/|4.7k + 1/(j·2π·1k·47n)| = 96 → 39.6 dB at 1 kHz, measured at 0.1 mV in (at a few mV the 1N914 already conduct and the gain drops)
- `out_dc_V` in [4.3, 4.7] — bias at half supply
- `clip_pp_V_300mV` in [0.9, 1.6] — antiparallel 1N914 in the feedback: roughly ±0.55–0.7 V

| part | candidate | source | preferred | clip_pp_V_300mV | error | gain_dB_small | out_dc_V | in range |
|---|---|---|---|---|---|---|---|---|
| RC4558 | `ti.lib` | ti | ★ | 1.526 |  | 38.1 | 4.504 | yes |
| RC4558 | `kicad-spice-library.lib` | kicad-spice-library |  | 1.526 |  | 38.1 | 4.504 | yes |
| TL072 | `ti.lib` | ti |  | 1.526 |  | 38.8 | 4.5 | yes |
| TL072 | `stmicro.lib` | stmicro |  |  | SimError: LTspice failed on ts (exit 255): 
Direct Newton iteration for .op point succeeded.
Singular matrix:  Check node u1:15
   |  |  | NO |
| TL072 | `bordodynov.lib` | bordodynov |  | 1.526 |  | 38.8 | 4.5 | yes |
| TL072 | `bordodynov-2.lib` | bordodynov |  | 1.526 |  | 38.8 | 4.5 | yes |
| TL072 | `bordodynov-3.lib` | bordodynov |  | 0.0 |  | -103.6 | 0.0 | NO |
| TL072 | `bordodynov-4.lib` | bordodynov | ★ | 1.526 |  | 38.8 | 4.5 | yes |
| NE5532 | `bordodynov.lib` | bordodynov |  | 1.526 |  | 30.8 | 4.426 | NO |
| NE5532 | `ltwiki.lib` | ltwiki |  | 1.526 |  | 30.8 | 4.426 | NO |
| NE5532 | `ltwiki-2.lib` | ltwiki | ★ | 1.526 |  | 36.8 | 4.496 | NO |
| LM358 | `bordodynov.lib` | bordodynov |  | 1.526 |  | 39.0 | 4.51 | yes |
| LM358 | `bordodynov-2.lib` | bordodynov |  | 1.526 |  | 39.0 | 4.5 | yes |
| LM358 | `bordodynov-3.lib` | bordodynov |  | 1.526 |  | 38.9 | 4.501 | yes |
| LM358 | `bordodynov-4.lib` | bordodynov | ★ | 1.526 |  | 38.9 | 4.5 | yes |
| LM358 | `bordodynov-5.lib` | bordodynov |  | 1.526 |  | 39.0 | 4.5 | yes |
| LM358 | `bordodynov-6.lib` | bordodynov |  | 1.526 |  | 38.9 | 4.501 | yes |
| OPA2134 | `ti.lib` | ti | ★ |  | TimeoutExpired: Command '['/Applications/LTspice.app/Contents/MacOS/LTspice', '-ascii', '-b', 'ts.net']' timed out after 60 seconds |  |  | NO |
| OPA2134 | `ti-2.lib` | ti |  |  | TimeoutExpired: Command '['/Applications/LTspice.app/Contents/MacOS/LTspice', '-ascii', '-b', 'ts.net']' timed out after 60 seconds |  |  | NO |
| OPA2134 | `bordodynov.lib` | bordodynov |  | 0.0 |  | -102.4 | 0.353 | NO |

Netlists: the `.net` files next to this report (paths relative to the repo).
