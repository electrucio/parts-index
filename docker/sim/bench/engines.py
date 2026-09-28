"""Run one netlist in the simulator of this image and say what it cost.

Each image sets SIM_ENGINE. A run returns the waveform file, the simulator's own log, and its cost: wall
time, the CPU time of the simulator process, the CPU time of the whole container over the run (which also
counts Wine's server process, invisible to the first), and the largest resident size of the simulator.
"""

import json
import os
import resource
import subprocess
import time
from pathlib import Path

WINE_PROGRAMS = Path(os.environ.get("WINEPREFIX", "/sim/wine")) / "drive_c" / "Program Files"
LTSPICE = WINE_PROGRAMS / "ADI" / "LTspice" / "LTspice.exe"
QSPICE = WINE_PROGRAMS / "QSPICE" / "QSPICE64.exe"
WINE64 = "/usr/lib/wine/wine64"  # LTspice is 64-bit; the `wine` wrapper would start the 32-bit loader first
WINE = "wine"  # QSPICE64.exe and QSPICE80.exe are 32-bit programs


def engine_name():
    return os.environ.get("SIM_ENGINE", "ngspice")


def _cgroup_cpu_s():
    try:
        for line in Path("/sys/fs/cgroup/cpu.stat").read_text().splitlines():
            if line.startswith("usage_usec"):
                return int(line.split()[1]) / 1e6
    except OSError:
        pass
    return None


def _cgroup_mem_peak_mb():
    try:
        return int(Path("/sys/fs/cgroup/memory.peak").read_text()) / 2**20
    except (OSError, ValueError):
        return None


_display_started = False


def _ensure_display():
    """A virtual screen for Windows programs that open a window even in batch mode (one per container)."""
    global _display_started
    if _display_started or os.environ.get("SIM_NO_DISPLAY"):
        return
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":99"
        subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if Path("/tmp/.X11-unix/X99").exists():
                break
            time.sleep(0.05)
    # One Wine server for the life of the container: every run after the first finds it already there.
    subprocess.run(["wineserver", "-p"], check=False)
    _display_started = True


def header(engine):
    """Options each simulator needs to write comparable, full-precision, uncompressed waveforms."""
    if engine == "ltspice":
        # plotwinsize=0: no waveform compression; numdgt>6: doubles in the .raw file. (LTspice starts one
        # solver thread per CPU of the host and offers no option to change that in batch mode.)
        return ".options plotwinsize=0 numdgt=15"
    return ""


def command(engine, netlist):
    name = netlist.name
    if engine == "ngspice":
        return ["ngspice", "-b", "-r", netlist.with_suffix(".raw").name, name]
    if engine == "ltspice":
        return [WINE64, str(LTSPICE), "-b", "-ascii", name]
    if engine == "qspice":
        return [WINE, str(QSPICE), name, "-ascii", "-r", raw_path(engine, netlist).name]
    raise ValueError(f"unknown engine {engine}")


def raw_path(engine, netlist):
    if engine == "qspice":
        return netlist.with_suffix(".qraw")
    return netlist.with_suffix(".raw")


def run(netlist, engine=None, timeout=600):
    """Simulate `netlist` (a Path) in its own folder; return a dict with the files and the cost."""
    engine = engine or engine_name()
    netlist = Path(netlist)
    if engine in ("ltspice", "qspice"):
        _ensure_display()
    env = dict(os.environ, SPICE_ASCIIRAWFILE="1")
    raw = raw_path(engine, netlist)
    raw.unlink(missing_ok=True)
    log = netlist.with_suffix(".out")
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    cg0 = _cgroup_cpu_s()
    t0 = time.perf_counter()
    timed_out = False
    with log.open("wb") as out:
        try:
            proc = subprocess.run(command(engine, netlist), cwd=netlist.parent, env=env, stdout=out,
                                  stderr=subprocess.STDOUT, timeout=timeout)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out, returncode = True, None
            if engine in ("ltspice", "qspice"):  # the simulator is Wine's child, not ours: stop them all
                subprocess.run(["wineserver", "-k"], check=False)
                subprocess.run(["wineserver", "-p"], check=False)
    wall = time.perf_counter() - t0
    cg1 = _cgroup_cpu_s()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "engine": engine,
        "netlist": netlist.name,
        "returncode": returncode,
        "timed_out": timed_out,
        "raw": str(raw) if raw.exists() and not timed_out else None,
        "log": str(log),
        "wall_s": round(wall, 4),
        "cpu_user_s": round(after.ru_utime - before.ru_utime, 4),
        "cpu_sys_s": round(after.ru_stime - before.ru_stime, 4),
        "container_cpu_s": round(cg1 - cg0, 4) if cg0 is not None and cg1 is not None else None,
        "maxrss_mb": round(after.ru_maxrss / 1024, 1),
        "container_mem_peak_mb": _cgroup_mem_peak_mb(),
    }


def version(engine=None):
    engine = engine or engine_name()
    if engine == "ngspice":
        out = subprocess.run(["ngspice", "--version"], capture_output=True, text=True).stdout
        return next((ln.strip("* ").strip() for ln in out.splitlines() if "ngspice-" in ln), out.strip())
    exe = LTSPICE if engine == "ltspice" else QSPICE
    return {"exe": exe.name, "sha256": _sha256(exe)}


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":  # simrun: one netlist, cost as JSON on stdout
    import sys
    for arg in sys.argv[1:]:
        print(json.dumps(run(Path(arg).resolve())))
    if len(sys.argv) == 1:
        print(json.dumps({"engine": engine_name(), "version": version()}))
