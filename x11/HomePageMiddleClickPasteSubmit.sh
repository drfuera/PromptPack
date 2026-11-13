#!/bin/bash
RC="$HOME/.xbindkeysrc"
MARK_START="# BEGIN paste-enter-toggle"
MARK_END="# END paste-enter-toggle"

if grep -q "$MARK_START" "$RC"; then
    sed -i "/$MARK_START/,/$MARK_END/d" "$RC"
    STATUS="Av"
else
    cat >> "$RC" <<EOF
$MARK_START
"xdotool key Shift+Insert; sleep 0.2; xdotool key Return"
    b:2
$MARK_END
EOF
    STATUS="På"
fi

pkill xbindkeys 2>/dev/null
sleep 0.2
xbindkeys

# notify-send "Paste+Enter" "$STATUS"
