#!/bin/bash
set -e

SOURCE="assets/app_icon.jpg"
ICONSET="assets/icon.iconset"

mkdir -p "$ICONSET"

# Check if source exists
if [ ! -f "$SOURCE" ]; then
    echo "Error: $SOURCE not found!"
    exit 1
fi

echo "Generating iconset..."
sips -z 16 16     -s format png "$SOURCE" --out "$ICONSET/icon_16x16.png"
sips -z 32 32     -s format png "$SOURCE" --out "$ICONSET/icon_16x16@2x.png"
sips -z 32 32     -s format png "$SOURCE" --out "$ICONSET/icon_32x32.png"
sips -z 64 64     -s format png "$SOURCE" --out "$ICONSET/icon_32x32@2x.png"
sips -z 128 128   -s format png "$SOURCE" --out "$ICONSET/icon_128x128.png"
sips -z 256 256   -s format png "$SOURCE" --out "$ICONSET/icon_128x128@2x.png"
sips -z 256 256   -s format png "$SOURCE" --out "$ICONSET/icon_256x256.png"
sips -z 512 512   -s format png "$SOURCE" --out "$ICONSET/icon_256x256@2x.png"
sips -z 512 512   -s format png "$SOURCE" --out "$ICONSET/icon_512x512.png"
sips -z 1024 1024 -s format png "$SOURCE" --out "$ICONSET/icon_512x512@2x.png"

echo "Creating .icns file..."
iconutil -c icns "$ICONSET"

echo "Done: assets/icon.icns created."
rm -rf "$ICONSET"
