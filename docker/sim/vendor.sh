#!/bin/sh
# Fill the private vendor store with what the simulator images are built from, and check each file
# against the sha256 committed in docker/sim/sha256/.
#
#   sh docker/sim/vendor.sh VENDOR_DIR          (make sim-vendor)
#
# LTspice64.msi and InstallQSPICE.exe are fetched from their makers; neither may be redistributed, so the
# store is private and is the copy that counts: Analog Devices replaces LTspice64.msi at the same URL
# with every release, and a download that no longer matches its sha256 is reported, not used. Moving to
# a new release is a deliberate change of docker/sim/sha256/LTspice64.msi.sha256, and of the results
# that go with it. The QSPICE downloader is not checked here — what it installs is, once captured
# (qspice_capture.sh).
set -eu
VENDOR=${1:?give the vendor store directory}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$VENDOR"
cd "$VENDOR"
fetch() {  # name url
    if [ -f "$1" ]; then echo "have $1"; return; fi
    echo "fetching $1"
    curl -fsSL --retry 3 -o "$1.part" "$2" && mv "$1.part" "$1"
}
fetch ngspice-47.tar.gz https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/ngspice-47.tar.gz/download
fetch LTspice64.msi https://ltspice.analog.com/software/LTspice64.msi
fetch InstallQSPICE.exe https://getqspice.com/InstallQSPICE.exe
status=0
for f in ngspice-47.tar.gz LTspice64.msi qspice-program-files.tar.gz; do
    if [ ! -f "$f" ]; then
        case $f in
            qspice-*) echo "missing $f — run make sim-qspice-capture" ;;
            *) echo "missing $f" ;;
        esac
        status=1
    elif ! sha256sum -c "$HERE/sha256/$f.sha256" >/dev/null 2>&1; then
        echo "MISMATCH $f: $(sha256sum "$f" | cut -d' ' -f1) is not the pinned $(cut -d' ' -f1 "$HERE/sha256/$f.sha256")"
        status=1
    else
        echo "ok $f"
    fi
done
exit $status
