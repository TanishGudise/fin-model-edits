#!/bin/sh
# start-desktop W H: an X display of W x H, the filings open in Writer (one window each) and the workbook in Calc,
# every window maximized by JWM into the area above the taskbar (jwmrc). Calc opens last, so it is on top.
set -u
W=${1:-1280} H=${2:-800}
Xvfb :1 -screen 0 "${W}x${H}x24" -nolisten tcp >/tmp/xvfb.log 2>&1 &
for i in $(seq 1 50); do xdpyinfo -display :1 >/dev/null 2>&1 && break; sleep 0.2; done
jwm >/tmp/jwm.log 2>&1 &
sleep 1
export HOME=/tmp/home && mkdir -p $HOME && cp -r /opt/lo-profile /tmp/lo-profile
PROFILE=-env:UserInstallation=file:///tmp/lo-profile
soffice $PROFILE --nologo --norestore --nodefault --writer /app/docs/*.txt >/tmp/lo-docs.log 2>&1 &
sleep 8
soffice $PROFILE --nologo --norestore --calc /app/model.xlsx >/tmp/lo-calc.log 2>&1 &
for i in $(seq 1 60); do xdotool search --name "model.xlsx" >/dev/null 2>&1 && break; sleep 0.5; done
sleep 2
w=$(xdotool search --onlyvisible --name "model.xlsx" | head -1)
[ -n "$w" ] && xdotool windowactivate --sync "$w" 2>/dev/null
echo ready
