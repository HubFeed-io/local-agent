#!/bin/bash
set -e

# Start virtual framebuffer
Xvfb :0 -screen 0 1920x1080x24 &
sleep 1

# Start fluxbox window manager (maximize all windows by default)
mkdir -p ~/.fluxbox
echo "session.screen0.defaultDeco: NONE" > ~/.fluxbox/init
cat > ~/.fluxbox/apps <<'EOF'
[app] (.*)
  [Maximized] {yes}
[end]
EOF
fluxbox &
sleep 1

# Start x11vnc with password (password: 1234)
x11vnc -display :0 -forever -usepw -rfbport 5900 &
sleep 1

echo "VNC server running on port 5900 (password: 1234)"

# Run the agent
exec /py/bin/python -m src.main
