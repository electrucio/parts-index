# Reference circuit: ltp

Long-tailed pair, 1 mA tail, 4.7k collector loads, +/-15 V.

Expected (design references):

- `Vc1_V` in [12.3, 12.95] — 15 − 0.5 mA·4.7k = 12.65 V, less base current
- `gain_single_ended` in [40, 50] — one input driven, output at one collector: gm·Rc/2 = (0.5 mA/25.7 mV)·4.7k/2 ≈ 46 (less for large RB/RE)

| part | candidate | source | preferred | Vc1_V | Vc2_V | gain_single_ended | in range |
|---|---|---|---|---|---|---|---|
| BC550C | `cordell.lib` | cordell |  | 12.655 | 12.656 | 44.3 | yes |
| BC550C | `bordodynov.lib` | bordodynov |  | 12.653 | 12.654 | 42.5 | yes |
| BC550C | `bordodynov-2.lib` | bordodynov |  | 12.655 | 12.656 | 44.3 | yes |
| BC550C | `bordodynov-3.lib` | bordodynov | ★ | 12.655 | 12.656 | 44.3 | yes |
| BC550C | `ltwiki.lib` | ltwiki |  | 12.655 | 12.656 | 44.3 | yes |
| BC550C | `ltwiki-2.lib` | ltwiki |  | 12.655 | 12.656 | 44.3 | yes |
| KSC1845 | `onsemi.lib` | onsemi | ★ | 12.653 | 12.654 | 43.9 | yes |
| KSC1845 | `bordodynov.lib` | bordodynov |  | 12.653 | 12.654 | 42.8 | yes |
| KSC1845 | `bordodynov-2.lib` | bordodynov |  | 12.653 | 12.654 | 42.8 | yes |
| KSC1845 | `bordodynov-3.lib` | bordodynov |  | 12.655 | 12.656 | 44.3 | yes |
| KSC1845 | `ltwiki.lib` | ltwiki |  | 12.653 | 12.654 | 42.8 | yes |
| KSC1845 | `ltwiki-2.lib` | ltwiki |  | 12.653 | 12.654 | 42.8 | yes |
| 2N5089 | `central-semi.lib` | central-semi | ★ | 12.653 | 12.654 | 44.3 | yes |
| 2N5089 | `ltspice-native.lib` | ltspice-native |  | 12.652 | 12.653 | 42.8 | yes |
| 2N5089 | `cordell.lib` | cordell |  | 12.654 | 12.655 | 43.5 | yes |
| 2N5089 | `bordodynov.lib` | bordodynov |  | 12.652 | 12.653 | 42.8 | yes |
| 2N5089 | `bordodynov-2.lib` | bordodynov |  | 12.652 | 12.653 | 42.8 | yes |
| 2N5089 | `bordodynov-3.lib` | bordodynov |  | 12.654 | 12.655 | 43.5 | yes |
| 2N3904 | `onsemi.lib` | onsemi | ★ | 12.672 | 12.674 | 29.2 | NO |
| 2N3904 | `central-semi.lib` | central-semi |  | 12.662 | 12.664 | 44.1 | yes |
| 2N3904 | `ltspice-native.lib` | ltspice-native |  | 12.656 | 12.658 | 44.2 | yes |
| 2N3904 | `cordell.lib` | cordell |  | 12.664 | 12.667 | 44.6 | yes |
| 2N3904 | `cordell-2.lib` | cordell |  | 12.664 | 12.667 | 44.5 | yes |
| 2N3904 | `duncanamps.lib` | duncanamps |  | 12.669 | 12.673 | 43.3 | yes |

Netlists: the `.net` files next to this report (paths relative to the repo).
