#!/bin/sh
# Content-only crops of the author's screenshots for the PDF (originals in screenshots/ are not modified).
# sips: --cropToHeightWidth H W --cropOffset Y X (pixels of the original image)
cd "$(dirname "$0")/.." || exit 1
sips --cropToHeightWidth 590 2770 --cropOffset 219 0  screenshots/hand_join_check.png     --out report/fig/hand_join_check.png >/dev/null
sips --cropToHeightWidth 489 2650 --cropOffset 211 0  screenshots/hand_ap_check.png       --out report/fig/hand_ap_check.png >/dev/null
sips --cropToHeightWidth 1208 2120 --cropOffset 574 604 screenshots/kaggle_best_private.png --out report/fig/kaggle_best_private.png >/dev/null
cp screenshots/hand_reveal_check.png report/fig/hand_reveal_check.png
