#!/bin/bash
# check_paste_enter.sh
if /usr/bin/grep -q "# BEGIN paste-enter-toggle" "$HOME/.xbindkeysrc"; then
    echo "PasteSubmit ✅"
else
    echo "PasteSubmit️ ⛔"
fi
