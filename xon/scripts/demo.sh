#!/usr/bin/env bash
# XON Tier A demo: init -> crawl -> one learning cycle -> agent builds + critiques an app -> report.
set -euo pipefail
cd "$(dirname "$0")/.."
xon doctor || true
xon init --budget ${BUDGET:-30m}
xon crawl                     # live if the network works (polite, tiny), else mock web
xon crawl --mock --no-open    # adds image-text pairs from the mock gallery
xon train
xon gate m1
xon gate m4
xon report
echo "Dashboard: xon dashboard  (http://127.0.0.1:8787)"
