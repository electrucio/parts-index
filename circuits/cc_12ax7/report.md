# Reference circuit: cc_12ax7

Common-cathode 12AX7 (Fender-style V1): 250 V, 100k plate, 1.5k/25u cathode,
    22n into a 1M grid leak.

Expected (design references):

- `Vk_V` in [1.0, 2.0] — typical Fender V1 voltage charts: 1.2–1.8 V on the cathode
- `Vp_V` in [130, 200] — plate ≈ 150–190 V at 250 V B+ with 100k
- `gain` in [45, 75] — μ·RL/(RL+rp) with RL = 100k∥1M, rp ≈ 62k → ≈ 55–65

| part | candidate | source | preferred | Vk_V | Vp_V | gain | in range |
|---|---|---|---|---|---|---|---|
| 12AX7 | `reefman.lib` | reefman |  | 1.083 | 177.8 | 58.6 | yes |
| 12AX7 | `reefman-2.lib` | reefman |  | 1.083 | 177.8 | 58.6 | yes |
| 12AX7 | `reefman-3.lib` | reefman |  | 1.374 | 158.4 | 62.0 | yes |
| 12AX7 | `ayumi.lib` | ayumi | ★ | 1.321 | 161.9 | 55.5 | yes |
| 12AX7 | `duncanamps.lib` | duncanamps |  | 1.3 | 163.3 | 56.0 | yes |
| 12AX7 | `duncanamps-2.lib` | duncanamps |  | 1.3 | 163.3 | 56.0 | yes |
| 12AX7 | `duncanamps-3.lib` | duncanamps |  | 1.3 | 163.4 | 55.9 | yes |
| 12AX7 | `koren.lib` | koren |  | 1.199 | 170.1 | 58.5 | yes |
| 12AX7 | `koren-2.lib` | koren |  | 1.185 | 171.0 | 59.1 | yes |
| 12AX7 | `suusi-tubes.lib` | suusi-tubes |  | 1.298 | 163.5 | 55.0 | yes |

Netlists: the `.net` files next to this report (paths relative to the repo).
