#!/bin/bash
# R16 x: copy the four demo customers' document packs to var/r16_demo_files/ (the Mac pack; the originals stay in
# data/dealdesk/demo_customers/). Per customer: ASK.md (what to type), word/, pdf/, images/, business_request/ (C2), reference/.
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"; SRC="$V5/data/dealdesk/demo_customers"; DST="$V5/var/r16_demo_files"
mkdir -p "$DST"
for d in "$SRC"/c*_*/; do
  n="$(basename "$d")"; mkdir -p "$DST/$n"
  for x in ASK.md word pdf images business_request reference; do [ -e "$d/$x" ] && cp -a "$d/$x" "$DST/$n/"; done
done
cp "$SRC/ANSWER_KEY.md" "$SRC/CONTRACT.md" "$DST/"
cat > "$DST/README.txt" <<'T'
CreditProbe R16 demo files (all names fictional). See docs/v5/DEMO_SCRIPT.md, Part A and Part B.
Part A (RM side):     c1_dar_al_naseem   -> Deal Desk > New proposal > upload word/ or pdf/ or images/; type the ask and notes from ASK.md
Part B (credit side): c2_sawaed_al_bina  -> Deal Desk > Credit response > upload business_request/ (photos, Word or PDF) + pdf/
Also: c3_nukhba_polymer (new to bank, takeover), c4_sanad_facility (new-to-bank SME, checklist gaps).
T
echo "demo files -> $DST ($(find "$DST" -type f | wc -l) files)"
