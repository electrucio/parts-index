#!/bin/sh
# LTspice's first launches ask questions in windows, even in batch mode, and wait for an answer: a
# usage-data question (answered "no" beforehand by the seeded LTspice.ini) and whether to keep the
# keyboard shortcuts; it also unpacks its libraries. This runs it at image build time until a batch
# simulation finishes with no window left to answer, so no container ever meets one.
# A question about usage data is never answered here: if it appears, the build fails.
set -eu
EXE="$WINEPREFIX/drive_c/Program Files/ADI/LTspice/LTspice.exe"
export DISPLAY=:98
Xvfb :98 -screen 0 1280x900x24 -nolisten tcp >/dev/null 2>&1 &
XVFB=$!
for _ in $(seq 1 100); do [ -e /tmp/.X11-unix/X98 ] && break; sleep 0.05; done
D=$(mktemp -d)
cd "$D"
printf '* first run\nV1 a 0 1\nR1 a 0 1k\n.op\n.end\n' > t.cir
clean=0
seen=""
for attempt in 1 2 3 4 5; do
    rm -f t.raw t.log
    /usr/lib/wine/wine64 "$EXE" -b -ascii t.cir &
    pid=$!
    answered=0
    for _ in $(seq 1 600); do
        kill -0 $pid 2>/dev/null || break
        for w in $(xdotool search --onlyvisible --name '.' 2>/dev/null); do
            name=$(xdotool getwindowname "$w" 2>/dev/null || true)
            [ -n "$name" ] || continue
            case "$name" in
                *[Uu]sage*|*[Aa]nalytic*)
                    echo "LTspice asks about usage data ('$name'); refusing to answer" >&2
                    kill $pid; exit 1 ;;
            esac
            case "$seen" in *"|$name|"*) ;; *) echo "run $attempt: '$name' — answered with its default"; seen="$seen|$name|" ;; esac
            xdotool key Return  # there is no window manager: the key goes to the window that has the focus
            answered=1
        done
        sleep 0.2
    done
    wait $pid || true
    if [ -s t.raw ] && [ $answered -eq 0 ]; then clean=1; break; fi
done
wineserver -w
kill $XVFB 2>/dev/null || true
cd / && rm -rf "$D"
[ $clean -eq 1 ] || { echo "LTspice never ran without asking something" >&2; exit 1; }
echo "LTspice runs in batch mode with no window to answer"
