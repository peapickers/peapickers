#!/bin/bash
# update-database.sh
cd "$(dirname "$0")"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Updating images.json…"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 update-database.py
echo ""
echo "Done. Deploy your site to Netlify to publish."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "Press Enter to close..."