#!/bin/bash
# Switch between tide models (GOT4.10 or FES2022)
# Usage: ./switch_tide_model.sh [GOT4.10|FES2022]

MODEL=${1:-""}

if [ -z "$MODEL" ]; then
    echo "Usage: ./switch_tide_model.sh [GOT4.10|FES2022]"
    echo ""
    echo "Current model: $(grep TIDE_MODEL /var/www/pm2-ecosystem.config.js 2>/dev/null | head -1 || echo 'GOT4.10 (default)')"
    exit 1
fi

if [ "$MODEL" != "GOT4.10" ] && [ "$MODEL" != "FES2022" ]; then
    echo "Error: Model must be GOT4.10 or FES2022"
    exit 1
fi

if [ "$MODEL" == "FES2022" ]; then
    # Verify FES2022 is installed
    echo "Verifying FES2022 installation..."
    /var/www/dahab-api/venv/bin/python3 /var/www/dahab-api/verify_fes2022.py
    if [ $? -ne 0 ]; then
        echo ""
        echo "Cannot switch to FES2022 - installation incomplete"
        exit 1
    fi
fi

echo ""
echo "Switching to $MODEL..."

# Update PM2 environment
pm2 set DahabAPI:TIDE_MODEL "$MODEL" 2>/dev/null || true

# Clear cache and restart
rm -f /var/www/dahab-api/data/cache.json
TIDE_MODEL="$MODEL" pm2 restart DahabAPI --update-env

echo ""
echo "Switched to $MODEL"
echo "Verify with: curl -s https://dahab-api.karimmesallam.com/api/conditions | python3 -c \"import sys,json; d=json.load(sys.stdin); print('Tide range:', min(d['tide']), '-', max(d['tide']), 'cm')\""
