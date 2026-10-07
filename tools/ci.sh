#!/usr/bin/env bash
# Clean-room validation of the committed tree, as root in an Arch container:
#   podman run --rm -v "$PWD:/src:ro" docker.io/library/archlinux:latest bash /src/tools/ci.sh /src
# Runs the tests, validates metadata and translations, builds the package
# from this commit with the release PKGBUILD, installs it and starts it.
set -euo pipefail
src=$(realpath "${1:-$(dirname "$0")/..}")
out=${2:-}

pacman -Syu --noconfirm --needed base-devel git python python-gobject gtk4 libadwaita \
    dconf dbus python-pytest gettext appstream desktop-file-utils shellcheck namcap
git config --system --add safe.directory '*'
id builder >/dev/null 2>&1 || useradd --create-home builder
as_builder() { runuser -u builder -- "$@"; }

work=/home/builder/biglinux-config
rm -rf "$work"
as_builder git clone --quiet "$src" "$work"
cd "$work"

as_builder bash tools/check.sh
as_builder bash tools/check-dconf.sh
as_builder bash tools/i18n.sh --check
desktop-file-validate biglinux-config/usr/share/applications/*.desktop
appstreamcli validate --no-net biglinux-config/usr/share/metainfo/*.metainfo.xml
shellcheck biglinux-config/usr/bin/biglinux-config tools/*.sh
namcap pkgbuild/PKGBUILD

# The release PKGBUILD fetches the v$pkgver tag; build this commit instead.
commit=$(git rev-parse HEAD)
sed "s|^source=.*|source=(\"\$pkgname::git+file://$work#commit=$commit\")|" \
    pkgbuild/PKGBUILD > pkgbuild/PKGBUILD.ci
chown builder: pkgbuild/PKGBUILD.ci
(cd pkgbuild && as_builder makepkg --cleanbuild --noconfirm -p PKGBUILD.ci)
package=$(find pkgbuild -maxdepth 1 -name 'biglinux-config-*.pkg.tar.zst' | head -n 1)
namcap "$package"
pacman -U --noconfirm "$package"
as_builder biglinux-config --version
if [[ -n $out ]]; then
    cp "$package" "$out/"
fi
