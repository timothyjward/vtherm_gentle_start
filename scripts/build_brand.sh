#!/usr/bin/env bash
# Render the brand images of the integration from the SVG sources in assets/brand.
# The sizes are the ones of the Home Assistant brand images: the icon is 256 pixels square, the logo is 128 pixels high,
# and the @2x variants are twice as large. Needs rsvg-convert (librsvg).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/assets/brand"
out="$root/custom_components/vtherm_gentle_start/brand"
mkdir -p "$out"

render() {
  local name="$1" width="$2" height="$3" suffix="$4" scale="$5"
  rsvg-convert --width "$((width * scale))" --height "$((height * scale))" --format png \
    --output "$out/${name}${suffix}.png" "$src/${name}.svg"
}

render icon 256 256 "" 1
render icon 256 256 "@2x" 2
for name in logo dark_logo; do
  render "$name" 360 128 "" 1
  render "$name" 360 128 "@2x" 2
done
