#!/usr/bin/env bash
# Regenerate the translation template, merge every catalog and compile it.
#   bash tools/i18n.sh          update .pot, .po and .mo files
#   bash tools/i18n.sh --check  fail if any of them is stale or invalid
set -euo pipefail
cd "$(dirname "$0")/.."

domain=biglinux-config
app=biglinux-config/usr/share/biglinux/biglinux-config
podir=biglinux-config/locale
modir=biglinux-config/usr/share/locale
version=$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$app/ui/metadata.py")
check=false
[[ ${1:-} == --check ]] && check=true

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

mapfile -t sources < <(git ls-files "$app/*.py" | sort)
xgettext --language=Python --from-code=UTF-8 --keyword=_ --keyword=ngettext:1,2 \
    --add-comments=TRANSLATORS: --sort-by-file --package-name="$domain" \
    --package-version="$version" \
    --msgid-bugs-address=https://github.com/ruscher/biglinux-config/issues \
    --output="$work/$domain.pot" "${sources[@]}"

# Ignore the creation date when deciding whether the template changed.
strip_date() { grep -v '^"POT-Creation-Date:' "$1"; }
if ! cmp -s <(strip_date "$work/$domain.pot") <(strip_date "$podir/$domain.pot"); then
    $check && { echo "$podir/$domain.pot is out of date: run tools/i18n.sh" >&2; exit 1; }
    cp "$work/$domain.pot" "$podir/$domain.pot"
fi

status=0
for po in "$podir"/*.po; do
    lang=$(basename "$po" .po)
    merged="$work/$lang.po"
    msgmerge --quiet --no-fuzzy-matching --previous --output-file="$merged" "$po" "$podir/$domain.pot"
    msgattrib --no-obsolete --output-file="$merged" "$merged"
    if $check; then
        cmp -s "$merged" "$po" || { echo "$po is not merged with the template" >&2; status=1; }
    else
        cp "$merged" "$po"
    fi
    msgfmt --check --output-file="$work/$lang.mo" "$po"
    mo="$modir/$lang/LC_MESSAGES/$domain.mo"
    if $check; then
        # Compare the decompiled catalogs: .mo files are not byte-reproducible
        # across gettext versions.
        cmp -s <(msgunfmt "$work/$lang.mo") <(msgunfmt "$mo") \
            || { echo "$mo is not compiled from $po" >&2; status=1; }
    else
        mkdir -p "$(dirname "$mo")"
        cp "$work/$lang.mo" "$mo"
    fi
done
exit "$status"
