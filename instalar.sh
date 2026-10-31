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
VOZ="$(mktemp -d)"
RESUMO=""
ESPERA="--speed-limit 20000 --speed-time 30"

fala() { printf '\n\033[31m[Sheep]\033[0m %s\n' "$1"; }
passo() { RESUMO="$RESUMO$(printf '  %-14s %s' "$1" "$2")"$'\n'; }
tem() { command -v "$1" >/dev/null 2>&1; }
poe_path() {
    export PATH="$1:$PATH"
    touch "$PERFIL"
    grep -qF "$1" "$PERFIL" || echo "export PATH=\"$1:\$PATH\"" >> "$PERFIL"
}
baixa_repo() { curl -fsSL $ESPERA "https://github.com/$1/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP"; }
copia_skills() {
    for alvo in "$HOME/.claude/skills" "$HOME/.agents/skills" "$CASA/.claude/skills" "$CASA/.agents/skills"; do
        mkdir -p "$alvo"
        for skill in "$1"/*/; do
            [ -f "$skill/SKILL.md" ] || continue
            rm -rf "$alvo/$(basename "$skill")"
            cp -R "$skill" "$alvo/$(basename "$skill")"
        done
    done
}

# Voz da Sheep: "diz clipe o" nao pode ser pulada. Atrasou, das outras toca so a mais recente.
diz() { [ -f "$VOZ/$1.wav" ] && printf '%s %s\n' "$1" "${2:-e}" >> "$VOZ/fila"; return 0; }
toca_falas() {
    while :; do
        if [ -s "$VOZ/fila" ]; then
            mv "$VOZ/fila" "$VOZ/lote"
            awk 'NR==FNR { if ($2 != "o") u = FNR; next } $2 == "o" || FNR == u { print $1 }' "$VOZ/lote" "$VOZ/lote" \
                | while read -r clipe; do afplay "$VOZ/$clipe.wav" 2>/dev/null; done
        elif [ -f "$VOZ/fim" ]; then
            return
        else
            sleep 0.2
        fi
    done
}
voz_liga() {
    [ "$SHEEP_SEM_VOZ" = 1 ] && return
    printf '\n  Trazendo a minha voz...\n'
    curl -fsL --connect-timeout 15 --max-time 120 "${SHEEP_VOZ_ZIP:-https://raw.githubusercontent.com/marcusforti/sheep/main/instalador/voz.zip}" -o "$VOZ/voz.zip" \
        && unzip -qo "$VOZ/voz.zip" -d "$VOZ" || return
    toca_falas </dev/null >/dev/null 2>&1 &
    VOZ_PID=$!
}
# Espera a ultima fala acabar, com limite, para o proximo passo nao falar por cima.
voz_fim() {
    touch "$VOZ/fim"
    [ -n "$VOZ_PID" ] && { ( sleep 25; kill "$VOZ_PID" 2>/dev/null ) & wait "$VOZ_PID" 2>/dev/null; }
    rm -rf "$VOZ"
}
# Sem isto o painel abre o assistente antigo e pode repetir etapas.
marca_instalacao() {
    mkdir -p "$CASA/.instalacao"
    if tem python3; then
        python3 -c 'import json, os, sys
c = sys.argv[1]
e = json.load(open(c)) if os.path.exists(c) else {}
e.update(dict.fromkeys(["boas_vindas", "verificar", "base", "cerebros", "casa"], "feito"))
json.dump(e, open(c, "w"))' "$CASA/.instalacao/estado.json"
    elif [ ! -f "$CASA/.instalacao/estado.json" ]; then
        printf '{"boas_vindas":"feito","verificar":"feito","base":"feito","cerebros":"feito","casa":"feito"}' > "$CASA/.instalacao/estado.json"
    fi
}

mkdir -p "$PASTA" "$BIN"
case "$(uname -m)" in arm64) ARQ=arm64 ;; *) ARQ=x64 ;; esac
abertura() {
    MEMORIA="$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
    DISCO="$(df -h "$HOME" | awk 'NR==2 {print $4}')"
    SISTEMA="macOS $(sw_vers -productVersion 2>/dev/null)"
    V=$'\033[31m'; N=$'\033[0m'
    printf '\n%s' "$V"
    cat <<'LETREIRO'
  ███████╗██╗  ██╗███████╗███████╗██████╗
  ██╔════╝██║  ██║██╔════╝██╔════╝██╔══██╗
  ███████╗███████║█████╗  █████╗  ██████╔╝
  ╚════██║██╔══██║██╔══╝  ██╔══╝  ██╔═══╝
  ███████║██║  ██║███████╗███████╗██║
  ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝
LETREIRO
    printf '%s\n' "$N"
    printf '        .;;;;;;;;;;.          %sSHEEP%s a agente dos Incomparaveis\n' "$V" "$N"
    printf '     .;;;;;;;;;;;;;;;;.\n'
    printf "   _;;;;;;;;;;;;;;;;;;;;_     %sDono%s %s\n" "$V" "$N" "$USER"
    printf '  /_);;   .--.  .--.   ;;(_\  %sComputador%s %s\n' "$V" "$N" "$(hostname -s)"
    printf '     ;;   | %sO%s|  |%sO%s |   ;;     %sSistema%s %s\n' "$V" "$N" "$V" "$N" "$V" "$N" "$SISTEMA"
    printf "     ;;   '--'  '--'   ;;     %sMemoria%s %s\n" "$V" "$N" "$MEMORIA"
    printf '      ;;      __      ;;      %sDisco livre%s %s\n' "$V" "$N" "$DISCO"
    printf "       ';.   \__/   .;'\n"
    printf "         ';;;;;;;;;;'         %sMudando pro seu Mac.%s Leva de 5 a 20 minutos.\n" "$V" "$N"
}

abertura

# As ferramentas da Apple vem antes da pergunta: sem elas o instalador para aqui.
if ! { xcode-select -p >/dev/null 2>&1 && tem git; }; then
    xcode-select --install 2>/dev/null
    fala "Abriu uma janela da Apple. Clica em Instalar, espera terminar e roda este comando de novo."
    exit 0
fi

voz_liga
diz abertura o

MOTOR=""
diz pergunta o
RESPOSTA=""
until [ "$RESPOSTA" = 1 ] || [ "$RESPOSTA" = 2 ] || [ "$RESPOSTA" = 3 ]; do
    printf '\nQual IA paga voce usa?  1 = Claude   2 = ChatGPT   3 = nenhuma\n'
    printf 'Digite 1, 2 ou 3 e aperte Enter: '
    read -r RESPOSTA </dev/tty
done
case "$RESPOSTA" in
    1) MOTOR=claude; ENDERECO=https://claude.ai/new ;;
    2) MOTOR=codex; ENDERECO=https://chatgpt.com/ ;;
esac
if [ -n "$MOTOR" ] && curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/modelo/prompt-mestre.md | pbcopy; then
    open "$ENDERECO"
    diz prompt o
    printf '\n  \033[31mENQUANTO EU INSTALO, FAZ ISSO:\033[0m\n'
    printf '  Abri a sua IA no navegador e ja copiei um prompt pra voce.\n'
    printf '  1. Clique na caixa de mensagem, aperte Command+V e envie.\n'
    printf '  2. Quando ela responder, copie a resposta inteira.\n'
    printf '  3. Quando eu abrir, cole essa resposta pra mim.\n'
    printf '  Sua memoria vem junto comigo. Pode ir que eu sigo instalando.\n'
fi

diz lista o

fala "Git..."
diz git
passo Git "ja tinha"

fala "Node..."
diz node
if tem node && [ "$(node -v | sed 's/^v\([0-9]*\).*/\1/')" -ge 20 ]; then
    passo Node "ja tinha"
elif curl -fL --retry 4 $ESPERA -# "https://nodejs.org/dist/$NODE_VERSAO/node-$NODE_VERSAO-darwin-$ARQ.tar.gz" -o "$TMP/node.tar.gz" \
    && tar -xzf "$TMP/node.tar.gz" -C "$PASTA"; then
    poe_path "$PASTA/node-$NODE_VERSAO-darwin-$ARQ/bin"
    passo Node "instalado"
else
    passo Node "FALHOU"
fi

diz python
if tem python3; then passo Python "ja tinha"; else passo Python "FALHOU"; fi

fala "Claude Code..."
diz claude
if tem claude; then
    passo "Claude Code" "ja tinha"
else
    curl -fsSL https://claude.ai/install.sh | bash </dev/null
    poe_path "$BIN"
    if tem claude; then passo "Claude Code" "instalado"; else passo "Claude Code" "FALHOU"; fi
fi

fala "Codex..."
diz codex
if tem codex; then
    passo Codex "ja tinha"
else
    curl -fsSL https://chatgpt.com/codex/install.sh -o "$TMP/codex.sh" && CODEX_NON_INTERACTIVE=1 sh "$TMP/codex.sh" </dev/null
    poe_path "$BIN"
    if tem codex; then passo Codex "instalado"; else passo Codex "FALHOU"; fi
fi

diz ffmpeg
if tem ffmpeg; then
    passo ffmpeg "ja tinha"
elif tem brew; then
    if brew install ffmpeg </dev/null; then passo ffmpeg "instalado"; else passo ffmpeg "FALHOU"; fi
else
    passo ffmpeg "pulado (a Sheep instala se precisar)"
fi

fala "Casa da Sheep..."
diz casa
CASA_OK=""
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
[ -f casa/dono.md ] || printf '
Se perguntar se voce confia na pasta: aperte a SETA PARA BAIXO, escolha Yes e aperte ENTER.

'
if [ -f casa/dono.md ]; then exec "$MOTOR"; else exec "$MOTOR" "Oi Sheep, acabei de te instalar. Vamos comecar?"; fi
FIM
    chmod +x "$BIN/sheep"
    [ -z "$MOTOR" ] || echo "$MOTOR" > "$CASA/.motor"
    poe_path "$BIN"
    CASA_OK=1
    passo "Casa da Sheep" "instalado"
else
    passo "Casa da Sheep" "FALHOU"
fi

fala "Skills..."
diz skills
if baixa_repo Jakeschincariol/instagram-agent-skill && baixa_repo marcusforti/carrossel-tweet; then
    copia_skills "$TMP/instagram-agent-skill-main/skills"
    mkdir -p "$TMP/skills-carrossel"
    mv "$TMP/carrossel-tweet-main" "$TMP/skills-carrossel/carrossel-tweet"
    copia_skills "$TMP/skills-carrossel"
    passo Skills "instalado"
else
    passo Skills "FALHOU"
fi

fala "Superpowers..."
diz superpowers
if baixa_repo obra/superpowers; then
    copia_skills "$TMP/superpowers-main/skills"
    passo Superpowers "instalado"
else
    passo Superpowers "FALHOU"
fi

# yt-dlp sem login: baixa video publico do YouTube, Instagram e TikTok para a skill assistir-video.
fala "Video..."
diz video
if curl -fL --retry 4 $ESPERA -# https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos -o "$BIN/yt-dlp" \
    && [ -d "$TMP/sheep-main/instalador/skills" ]; then
    chmod +x "$BIN/yt-dlp"
    copia_skills "$TMP/sheep-main/instalador/skills"
    passo Video "instalado"
else
    passo Video "FALHOU"
fi

# O Orca vem depois da Casa e das Skills: se o Wi-Fi engasgar, a Sheep ja esta pronta.
if [ "$SHEEP_SEM_ORCA" = 1 ]; then
    passo Orca "pulado"
else
    fala "Orca..."
    diz orca
    if [ -d /Applications/Orca.app ]; then
        passo Orca "ja tinha"
    elif curl -fL --retry 4 $ESPERA -# "https://github.com/stablyai/orca/releases/latest/download/orca-macos-$ARQ.dmg" -o "$TMP/orca.dmg" \
        && VOLUME="$(hdiutil attach -nobrowse "$TMP/orca.dmg" | grep -o '/Volumes/.*' | head -1)" \
        && cp -R "$VOLUME/Orca.app" /Applications/; then
        hdiutil detach "$VOLUME" >/dev/null
        passo Orca "instalado"
    else
        passo Orca "FALHOU"
    fi
fi

# Os aplicativos sao os downloads maiores: vem por ultimo e, se falharem, nao atrapalham o resto.
if [ "$SHEEP_SEM_APPS" = 1 ]; then
    passo Apps "pulado"
else
fala "App do Claude..."
diz apps
if [ -d /Applications/Claude.app ]; then
    passo "App do Claude" "ja tinha"
else
    ENDERECO_APP="$(curl -fsSL https://downloads.claude.ai/releases/darwin/universal/RELEASES.json | sed -n 's/.*"url":"\([^"]*\)".*/\1/p' | head -1)"
    if [ -n "$ENDERECO_APP" ] && curl -fL --retry 4 $ESPERA -# "$ENDERECO_APP" -o "$TMP/claude-app.zip" \
        && ditto -xk "$TMP/claude-app.zip" /Applications/; then
        passo "App do Claude" "instalado"
    else
        passo "App do Claude" "opcional, baixe em claude.com/download"
    fi
fi

fala "App do Codex..."
if [ -d /Applications/Codex.app ]; then
    passo "App do Codex" "ja tinha"
else
    case "$ARQ" in arm64) DMG=Codex.dmg ;; *) DMG=Codex-latest-x64.dmg ;; esac
    if curl -fL --retry 4 $ESPERA -# "https://persistent.oaistatic.com/codex-app-prod/$DMG" -o "$TMP/codex-app.dmg" \
        && VOLUME="$(hdiutil attach -nobrowse "$TMP/codex-app.dmg" | grep -o '/Volumes/.*' | head -1)" \
        && cp -R "$VOLUME/Codex.app" /Applications/; then
        hdiutil detach "$VOLUME" >/dev/null
        passo "App do Codex" "instalado"
    else
        passo "App do Codex" "opcional, baixe em chatgpt.com/codex"
    fi
fi
fi

[ -z "$CASA_OK" ] || marca_instalacao

rm -rf "$TMP"
printf '\n  ------------- RESUMO -------------\n%s\n' "$RESUMO"
if printf '%s' "$RESUMO" | grep -q FALHOU; then
    fala "Faltou um item. Roda o mesmo comando de novo. Se repetir, levanta a mao e mostra esta tela."
    diz fim_falha o
else
    diz fim_ok o
fi
voz_fim
fala "Pronto. Fecha este terminal, abre outro e digita: sheep  (ou: sheep codex, se voce usa o ChatGPT)"
