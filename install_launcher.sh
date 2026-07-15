#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s/Desktop' "$HOME")"
mkdir -p "$DESKTOP" "$HOME/.local/share/applications"
sed "s|^Exec=.*|Exec=$ROOT/start.sh|;s|^Icon=.*|Icon=$ROOT/assets/prompt-workbench.svg|" "$ROOT/Prompt成本工作台.desktop" > "$DESKTOP/Prompt成本工作台.desktop"
cp "$DESKTOP/Prompt成本工作台.desktop" "$HOME/.local/share/applications/prompt-workbench.desktop"
chmod +x "$ROOT/start.sh" "$DESKTOP/Prompt成本工作台.desktop" "$HOME/.local/share/applications/prompt-workbench.desktop"
if command -v gio >/dev/null 2>&1; then gio set "$DESKTOP/Prompt成本工作台.desktop" metadata::trusted true 2>/dev/null || true; fi
printf '桌面启动图标已安装：%s\n' "$DESKTOP/Prompt成本工作台.desktop"
