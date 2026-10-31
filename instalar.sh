#!/bin/bash
# Sheep: instalador de uma linha da Imersao Operacao de IA (Mac).
#   curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/instalar.sh | bash
# Pode rodar de novo: o que ja esta instalado e pulado e a pasta casa/ nunca e sobrescrita.

NODE_VERSAO=v26.13.0
CASA="$HOME/Sheep"
PASTA="$HOME/.sheep"
BIN="$HOME/.local/bin"
PERFIL="$HOME/.zshrc"
TMP="$(mktemp -d)"
RESUMO=""

fala() { printf '\n\033[31m[Sheep]\033[0m %s\n' "$1"; }
passo() { RESUMO="$RESUMO$(printf '  %-14s %s' "$1" "$2")"$'\n'; }
tem() { command -v "$1" >/dev/null 2>&1; }
poe_path() {
    export PATH="$1:$PATH"
    touch "$PERFIL"
    grep -qF "$1" "$PERFIL" || echo "export PATH=\"$1:\$PATH\"" >> "$PERFIL"
}
baixa_repo() { curl -fsSL "https://github.com/$1/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP"; }
copia_skills() {
    for alvo in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
        mkdir -p "$alvo"
        for skill in "$1"/*/; do
            [ -f "$skill/SKILL.md" ] || continue
            rm -rf "$alvo/$(basename "$skill")"
            cp -R "$skill" "$alvo/$(basename "$skill")"
        done
    done
}

mkdir -p "$PASTA" "$BIN"
case "$(uname -m)" in arm64) ARQ=arm64 ;; *) ARQ=x64 ;; esac
fala "Mudando pro seu Mac. Leva uns 5 a 15 minutos."

fala "Git..."
if xcode-select -p >/dev/null 2>&1 && tem git; then
    passo Git "ja tinha"
else
    xcode-select --install 2>/dev/null
    fala "Abriu uma janela da Apple. Clica em Instalar, espera terminar e roda este comando de novo."
    exit 0
fi

fala "Node..."
if tem node && [ "$(node -v | sed 's/^v\([0-9]*\).*/\1/')" -ge 20 ]; then
    passo Node "ja tinha"
elif curl -fL --retry 4 -# "https://nodejs.org/dist/$NODE_VERSAO/node-$NODE_VERSAO-darwin-$ARQ.tar.gz" -o "$TMP/node.tar.gz" \
    && tar -xzf "$TMP/node.tar.gz" -C "$PASTA"; then
    poe_path "$PASTA/node-$NODE_VERSAO-darwin-$ARQ/bin"
    passo Node "instalado"
else
    passo Node "FALHOU"
fi

if tem python3; then passo Python "ja tinha"; else passo Python "FALHOU"; fi

fala "Claude Code..."
if tem claude; then
    passo "Claude Code" "ja tinha"
else
    curl -fsSL https://claude.ai/install.sh | bash </dev/null
    poe_path "$BIN"
    if tem claude; then passo "Claude Code" "instalado"; else passo "Claude Code" "FALHOU"; fi
fi

fala "Codex..."
if tem codex; then
    passo Codex "ja tinha"
else
    curl -fsSL https://chatgpt.com/codex/install.sh -o "$TMP/codex.sh" && CODEX_NON_INTERACTIVE=1 sh "$TMP/codex.sh" </dev/null
    poe_path "$BIN"
    if tem codex; then passo Codex "instalado"; else passo Codex "FALHOU"; fi
fi

fala "Orca..."
if [ -d /Applications/Orca.app ]; then
    passo Orca "ja tinha"
elif curl -fL --retry 4 -# "https://github.com/stablyai/orca/releases/latest/download/orca-macos-$ARQ.dmg" -o "$TMP/orca.dmg" \
    && VOLUME="$(hdiutil attach -nobrowse "$TMP/orca.dmg" | grep -o '/Volumes/.*' | head -1)" \
    && cp -R "$VOLUME/Orca.app" /Applications/; then
    hdiutil detach "$VOLUME" >/dev/null
    passo Orca "instalado"
else
    passo Orca "FALHOU"
fi

if tem ffmpeg; then
    passo ffmpeg "ja tinha"
elif tem brew; then
    if brew install ffmpeg </dev/null; then passo ffmpeg "instalado"; else passo ffmpeg "FALHOU"; fi
else
    passo ffmpeg "pulado (a Sheep instala se precisar)"
fi

fala "Casa da Sheep..."
if baixa_repo marcusforti/sheep; then
    mkdir -p "$CASA"
    (cd "$TMP/sheep-main/modelo" && find . -type f) | while read -r arquivo; do
        case "$arquivo" in ./casa/*|./memoria/*) [ -e "$CASA/$arquivo" ] && continue ;; esac
        mkdir -p "$(dirname "$CASA/$arquivo")"
        cp "$TMP/sheep-main/modelo/$arquivo" "$CASA/$arquivo"
    done
    cat > "$BIN/sheep" <<'FIM'
#!/bin/bash
cd "$HOME/Sheep" || exit 1
case "$1" in claude|codex) echo "$1" > .motor ;; esac
[ -f .motor ] || echo claude > .motor
MOTOR="$(cat .motor)"
if [ -f casa/dono.md ]; then exec "$MOTOR"; else exec "$MOTOR" "Oi Sheep, acabei de te instalar. Vamos comecar?"; fi
FIM
    chmod +x "$BIN/sheep"
    poe_path "$BIN"
    passo "Casa da Sheep" "instalado"
else
    passo "Casa da Sheep" "FALHOU"
fi

fala "Skills..."
if baixa_repo Jakeschincariol/instagram-agent-skill && baixa_repo marcusforti/carrossel-tweet; then
    copia_skills "$TMP/instagram-agent-skill-main/skills"
    mkdir -p "$TMP/skills-carrossel"
    mv "$TMP/carrossel-tweet-main" "$TMP/skills-carrossel/carrossel-tweet"
    copia_skills "$TMP/skills-carrossel"
    passo Skills "instalado"
else
    passo Skills "FALHOU"
fi

rm -rf "$TMP"
printf '\n  ------------- RESUMO -------------\n%s\n' "$RESUMO"
fala "Pronto. Fecha este terminal, abre outro e digita: sheep  (ou: sheep codex, se voce usa o ChatGPT)"
