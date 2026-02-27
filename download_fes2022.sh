#!/bin/bash
# Download FES2022 ocean tide data from AVISO
# Usage: ./download_fes2022.sh

set -e

AVISO_USER="karim.mesallam@gmail.com"
AVISO_HOST="ftp-access.aviso.altimetry.fr"
AVISO_PORT="2221"
LOCAL_DIR="/var/www/dahab-api/tide-models/FES2022"
REMOTE_DIR="/auxiliary/tide_model/fes2022b"

echo "=== FES2022 Download Script ==="
echo ""
echo "This will download FES2022 ocean tide extrapolated files (~5.5GB)"
echo "Local directory: $LOCAL_DIR"
echo ""
echo "You will be prompted for your AVISO password."
echo ""

# Create local directories
mkdir -p "$LOCAL_DIR/ocean_tide_extrapolated"

# Download using sftp
sftp -P $AVISO_PORT $AVISO_USER@$AVISO_HOST << EOF
cd $REMOTE_DIR/ocean_tide_extrapolated
lcd $LOCAL_DIR/ocean_tide_extrapolated
mget *.xz
quit
EOF

echo ""
echo "Download complete!"
echo ""
echo "Decompressing .xz files..."
cd "$LOCAL_DIR/ocean_tide_extrapolated"
for f in *.xz; do
    echo "  Decompressing $f..."
    xz -d -k "$f"
done

echo ""
echo "Done! Files saved to: $LOCAL_DIR/ocean_tide_extrapolated/"
ls -lh "$LOCAL_DIR/ocean_tide_extrapolated/"*.nc | head -10
echo "... ($(ls -1 "$LOCAL_DIR/ocean_tide_extrapolated/"*.nc | wc -l) total .nc files)"
