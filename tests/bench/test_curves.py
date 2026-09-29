"""The bench's own helpers (docker/sim/bench), which run inside the simulator images."""
import sys

from parts_index.core import config

sys.path.insert(0, str(config.sim_bench().parent))
from bench import curves, spec  # noqa: E402


def test_a_switching_time_is_read_where_the_waveform_crosses_its_threshold_interpolated():
    t = [0.0, 1.0, 2.0, 3.0, 4.0]
    rising = [0.0, 0.0, 0.5, 1.0, 1.0]
    assert spec.crossing(t, rising, 0.1, 0, True) == 1.2
    assert spec.crossing(t, rising, 0.9, 0, True) == 2.8
    falling = [1.0, 1.0, 0.5, 0.0, 0.0]
    assert spec.crossing(t, falling, 0.9, 0, False) == 1.2
    assert spec.crossing(t, falling, 0.9, 2.5, False) is None      # nothing after the time asked for


def test_a_curve_is_sampled_evenly_on_the_figures_own_scale():
    assert [round(x, 6) for x in curves.grid(0.1, 10, "log", 3)] == [0.1, 1.0, 10.0]
    assert curves.grid(0, 200, "lin", 5) == [0, 50, 100, 150, 200]
