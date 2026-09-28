# syntax=docker/dockerfile:1.7
# Three SPICE simulators, each in an image whose every input is pinned, so that the same netlist gives the
# same numbers on another machine or in a year. See docker/sim/README.md for the whole procedure.
#
#   make sim-images            # builds parts-index-ngspice, parts-index-ltspice, parts-index-qspice
#
# What is pinned, and where:
#   - the base image, by digest (DEBIAN below);
#   - every Debian package, by reading the archive as it was at one instant (SNAPSHOT, snapshot.debian.org);
#   - the vendor programs, by sha256 (docker/sim/sha256/<file>.sha256), copied from the private vendor store that
#     `make sim-vendor` fills. LTspice and QSPICE may not be redistributed, so their installers never enter
#     the repository and the images are never pushed to a registry; each machine builds its own.
# The build context is docker/sim alone; the vendor store is the named context `vendor`.

ARG DEBIAN=debian:trixie-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a

FROM ${DEBIAN} AS base
ARG SNAPSHOT=20260926T000000Z
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC PYTHONDONTWRITEBYTECODE=1
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf '%s\n' \
    "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${SNAPSHOT} trixie main" \
    "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${SNAPSHOT} trixie-updates main" \
    "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${SNAPSHOT} trixie-security main" \
    > /etc/apt/sources.list \
 && printf 'Acquire::Retries "5";\nAcquire::http::Timeout "60";\n' > /etc/apt/apt.conf.d/80snapshot \
 && apt-get update && apt-get install -y --no-install-recommends python3 time procps \
 && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------- ngspice, built from the release tarball
FROM base AS ngspice-build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential bison flex \
 && rm -rf /var/lib/apt/lists/*
COPY --from=vendor ngspice-47.tar.gz /src/
COPY sha256/ngspice-47.tar.gz.sha256 /src/
RUN cd /src && sha256sum -c ngspice-47.tar.gz.sha256 \
 && tar xzf ngspice-47.tar.gz && cd ngspice-47 \
 && ./configure --prefix=/usr/local --with-x=no --with-readline=no --enable-xspice --enable-cider \
      --enable-openmp --disable-debug CFLAGS="-O2" \
 && make -j"$(nproc)" && make install

FROM base AS ngspice
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=ngspice-build /usr/local /usr/local
ENV SIM_ENGINE=ngspice
ARG UID=1000
ARG GID=1000
RUN mkdir -p /sim && groupadd -g ${GID} sim && useradd -m -d /sim/home -u ${UID} -g ${GID} sim && chown sim:sim /sim
USER sim
WORKDIR /work
RUN ngspice --version | head -2
COPY simrun /usr/local/bin/simrun
COPY bench /sim/bench

# ---------------------------------------------------------------- Wine, with a prefix made at build time
# The prefix is created here, as the user the containers run as, so a container starts with Wine ready
# instead of spending seconds in wineboot. Mono and Gecko are switched off: nothing here needs .NET or HTML.
# Both halves of Wine: LTspice is a 64-bit program, but QSPICE's engines (QSPICE64/QSPICE80 — the number
# is the floating-point width, 80 being the x87 extended type) are 32-bit ones.
FROM base AS wine
RUN dpkg --add-architecture i386 && apt-get update \
 && apt-get install -y --no-install-recommends wine wine64 wine32:i386 xvfb xauth xdotool \
 && rm -rf /var/lib/apt/lists/*
ARG UID=1000
ARG GID=1000
RUN mkdir -p /sim && groupadd -g ${GID} sim && useradd -m -d /sim/home -u ${UID} -g ${GID} sim && chown sim:sim /sim
USER sim
ENV WINEPREFIX=/sim/wine WINEARCH=win64 WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=" \
    XDG_RUNTIME_DIR=/tmp/runtime-sim
RUN mkdir -m 700 /tmp/runtime-sim && wineboot --init && wineserver -w
WORKDIR /work

# ---------------------------------------------------------------- LTspice (Analog Devices)
# The MSI is unpacked, not run: under Wine its installer hangs in a custom action that reports the
# installation home (InstallerAnalytics.dll), and LTspice itself is a program folder with no registry needs.
FROM base AS ltspice-files
RUN apt-get update && apt-get install -y --no-install-recommends msitools && rm -rf /var/lib/apt/lists/*
COPY --from=vendor LTspice64.msi /src/
COPY sha256/LTspice64.msi.sha256 /src/
RUN cd /src && sha256sum -c LTspice64.msi.sha256 && mkdir /x && cd /x && msiextract /src/LTspice64.msi >/dev/null \
 && mv "/x/APPDIR:." /x/LTspice && test -f /x/LTspice/LTspice.exe

FROM wine AS ltspice
COPY --from=ltspice-files --chown=sim ["/x/LTspice", "/sim/wine/drive_c/Program Files/ADI/LTspice"]
COPY --chown=sim ltspice/LTspice.ini /sim/wine/drive_c/users/sim/AppData/Roaming/LTspice.ini
COPY ltspice/firstrun.sh /sim/ltspice-firstrun.sh
RUN sh /sim/ltspice-firstrun.sh
ENV SIM_ENGINE=ltspice
COPY simrun /usr/local/bin/simrun
COPY bench /sim/bench

# ---------------------------------------------------------------- QSPICE (Qorvo)
# QSPICE's installer is a downloader that asks for its licence in a window, so it cannot run in a build.
# `make sim-qspice-capture` runs it once in the `qspice-installer` stage below and packs the installed
# program folder into the vendor store; this stage only unpacks that archive, checked by its sha256.
FROM wine AS qspice
ARG QSPICE_ARCHIVE=qspice-program-files.tar.gz
COPY --from=vendor --chown=sim ${QSPICE_ARCHIVE} /tmp/
COPY sha256/${QSPICE_ARCHIVE}.sha256 /tmp/
RUN cd /tmp && sha256sum -c ${QSPICE_ARCHIVE}.sha256 \
 && tar -C "$WINEPREFIX/drive_c/Program Files" -xzf "/tmp/${QSPICE_ARCHIVE}" && rm "/tmp/${QSPICE_ARCHIVE}" \
 && test -f "$WINEPREFIX/drive_c/Program Files/QSPICE/QSPICE64.exe"
ENV SIM_ENGINE=qspice
COPY simrun /usr/local/bin/simrun
COPY bench /sim/bench

# The one-off stage for that capture: the Wine above, plus a way to look at the virtual screen and the
# certificates the downloader needs to reach Qorvo.
FROM wine AS qspice-installer
USER root
RUN apt-get update && apt-get install -y --no-install-recommends scrot ca-certificates \
 && rm -rf /var/lib/apt/lists/*
USER sim
