#!/bin/sh
# Build only; never installs or restarts desktop services.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK="$ROOT/.tmp/deepin-launch-fix"
mkdir -p "$WORK/source"
ARCHIVE="$WORK/source.tar.gz"
if [ ! -f "$ARCHIVE" ]; then
 curl --fail -L https://codeload.github.com/linuxdeepin/dde-application-manager/tar.gz/refs/tags/1.2.59 -o "$ARCHIVE"
fi
printf '%s  %s\n' 8395f08c7cdede8a7b0ecdfe9554cbdd6dde3bc824a8ec28ad0779349c303c8e "$ARCHIVE" | sha256sum -c -
tar -xzf "$ARCHIVE" -C "$WORK/source" --strip-components=1
patch -d "$WORK/source" -p1 < "$ROOT/tools/patches/deepin-am-1.2.59-long-path.patch"
cmake -S "$WORK/source" -B "$WORK/build" -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
cmake --build "$WORK/build" --target dde-application-manager -j 4
printf '\nBuilt: %s\n' "$WORK/build/apps/dde-application-manager/src/dde-application-manager"
