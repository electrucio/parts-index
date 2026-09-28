#!/bin/sh
# One-off: install QSPICE under Wine and pack its program folder into the vendor store, so the `qspice`
# image is built from a file checked by sha256 like the other two simulators.
#
#   sh docker/sim/qspice_capture.sh VENDOR_DIR          (make sim-qspice-capture)
#
# QSPICE's InstallQSPICE.exe is a downloader: it fetches the current build from Qorvo and asks for the
# licence in a window. This is the one step that is not reproducible by itself — whatever build Qorvo
# serves today is what gets captured. What it leaves is the archive, its sha256 (docker/sim/sha256/),
# screenshots of the licence it accepted and of the build it installed, and QSPICE's revision history.
# From then on every image built from that archive is the same. If Qorvo still serves the same build, a
# second capture gives the same sha256: the archive is packed with sorted names, fixed times and owners.
#
# The licence is the "Software License Agreement for QSPICE Software". Its terms forbid giving the
# software to third parties, hence the private vendor store, and no image built from it is ever pushed.
# The windows are answered below with xdotool — the "I ACCEPT" box included — so run this only if you
# accept that licence yourself. The maintainer did, for build "Sep 13 2026 09:34:10", on 2026-09-20.
#
# The clicks are screen positions: the dialogs open centred on the 1280x900 virtual screen, and they are
# the positions of QSPICE downloader 1.18. A later downloader may move a button; the script then stops
# at the window it could not get past and leaves a screenshot of it.
set -eu
VENDOR=$(cd "${1:?give the vendor store directory}" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
NAME=qspice-capture
ARCHIVE=qspice-program-files.tar.gz
IMAGE=${IMAGE:-parts-index-qspice-installer}
PROGRAMS='/sim/wine/drive_c/Program Files'

test -f "$VENDOR/InstallQSPICE.exe" || { echo "run make sim-vendor first: no InstallQSPICE.exe"; exit 1; }
docker rm -f $NAME >/dev/null 2>&1 || true
docker run -d --name $NAME -e DISPLAY=:99 -v "$VENDOR":/vendor "$IMAGE" \
    sh -c 'Xvfb :99 -screen 0 1280x900x24 -nolisten tcp & sleep infinity' >/dev/null
trap 'docker rm -f $NAME >/dev/null 2>&1 || true' EXIT
x() { docker exec $NAME "$@"; }
shot() { x scrot -o "/tmp/$1.png" && docker cp "$NAME:/tmp/$1.png" "$VENDOR/qspice-capture-$1.png"; }
has() { x xdotool search --onlyvisible --name "$1" >/dev/null 2>&1; }
# answer WINDOW X Y STEP: wait for the window, click at (X, Y), wait for it to go.
answer() {
    n=0
    until has "$1"; do
        n=$((n + 1)); [ $n -lt 180 ] || { shot "stuck-$4"; echo "no window '$1' (step $4)"; exit 1; }
        sleep 1
    done
    sleep 1
    x xdotool mousemove "$2" "$3" click 1
    n=0
    while has "$1"; do
        n=$((n + 1)); [ $n -lt 60 ] || { shot "stuck-$4"; echo "window '$1' stays (step $4)"; exit 1; }
        sleep 1
    done
    echo "step $4: '$1' answered"
}

sleep 2
x winecfg -v win10
x sh -c 'cp /vendor/InstallQSPICE.exe /tmp/ && cd /tmp && (wine InstallQSPICE.exe >/tmp/install.log 2>&1 &)'
answer 'Installing QSPICE' 641 492 1-directx-warning        # "requires Windows 11 with DirectX 12": OK
answer 'Run Elevated' 744 517 2-install-as-admin            # into C:\Program Files, like a normal install
answer 'Installing QSPICE' 641 492 3-directx-warning
answer 'QSPICE.*by Qorvo' 822 511 4-download                # "Do you wish to download and install": Yes
answer 'Installing QSPICE' 641 492 5-directx-warning
n=0
until has 'Installation Program for QSPICE'; do
    n=$((n + 1)); [ $n -lt 180 ] || { shot stuck-licence; echo "no licence window"; exit 1; }
    sleep 1
done
sleep 2
shot licence                                                # the terms and the build, as accepted
x xdotool mousemove 263 688 click 1                         # I ACCEPT these terms of use
sleep 1
x xdotool mousemove 964 688 click 1                         # Install
n=0
until has '^QSPICE.{1,2}$'; do                                   # "Installation complete!"
    n=$((n + 1)); [ $n -lt 600 ] || { shot stuck-install; echo "installation did not finish"; exit 1; }
    sleep 1
done
shot installed
x xdotool mousemove 641 472 click 1
sleep 2
x wineserver -k || true

x test -f "$PROGRAMS/QSPICE/QSPICE64.exe"
# The capture goes to a new name: the archive already pinned is the only copy of its build (Qorvo serves
# only the latest), so it is never overwritten here.
NEW=qspice-program-files.new.tar.gz
x sh -c "cd '$PROGRAMS' && tar --sort=name --mtime=2000-01-01 --owner=0 --group=0 --numeric-owner -cf - QSPICE \
    | gzip -n -9 > /vendor/$NEW"
x cat "$PROGRAMS/QSPICE/RevisionHistory.txt" > "$VENDOR/qspice-RevisionHistory.txt"
new_sum=$(cd "$VENDOR" && sha256sum $NEW | cut -d' ' -f1)
if [ ! -f "$VENDOR/$ARCHIVE" ]; then
    mv "$VENDOR/$NEW" "$VENDOR/$ARCHIVE"
    (cd "$VENDOR" && sha256sum $ARCHIVE) > "$HERE/sha256/$ARCHIVE.sha256"
    echo "captured and pinned: $new_sum"
elif [ "$new_sum" = "$(cut -d' ' -f1 "$HERE/sha256/$ARCHIVE.sha256")" ]; then
    rm "$VENDOR/$NEW"
    echo "same build as the pinned one: $new_sum"
else
    echo "Qorvo now serves another build ($new_sum), kept as $VENDOR/$NEW beside the pinned one."
    echo "To move to it: mv it over $ARCHIVE, rewrite sha256/$ARCHIVE.sha256, rebuild, and re-measure."
fi
