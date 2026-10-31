# Sheep: instalador de uma linha da Imersao Operacao de IA (Windows).
#   irm https://raw.githubusercontent.com/marcusforti/sheep/main/instalar.ps1 | iex
# Instala tudo na conta do usuario, sem winget e sem administrador.
# Pode rodar de novo: o que ja esta instalado e pulado e a pasta casa\ nunca e sobrescrita.
# Texto em ASCII de proposito: o Windows PowerShell 5.1 estraga acento em irm | iex.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    # SHEEP_INSTALAR_TESTE=1 simula PC zerado: nao mexe no registro, no Orca nem na area de trabalho.
    $teste = $env:SHEEP_INSTALAR_TESTE -eq '1'
    $programas = Join-Path $env:LOCALAPPDATA 'Programs'
    $tmp = Join-Path $env:TEMP 'sheep-instalar'
    $log = Join-Path $env:TEMP 'sheep-instalar.log'
    $casa = Join-Path $env:USERPROFILE 'Sheep'
    $binarios = Join-Path $env:USERPROFILE '.local\bin'
    $inicio = Join-Path $binarios 'sheep.cmd'
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $resultado = New-Object System.Collections.ArrayList
    $arquitetura = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }

    $urls = @{
        git       = 'https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.4/PortableGit-2.56.0.4-64-bit.7z.exe'
        node      = 'https://nodejs.org/dist/v26.13.0/node-v26.13.0-win-x64.zip'
        python    = 'https://www.nuget.org/api/v2/package/python/3.13.17'
        ffmpeg    = 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip'
        orca      = 'https://github.com/stablyai/orca/releases/latest/download/orca-windows-setup.exe'
        sheep     = if ($env:SHEEP_REPO_ZIP) { $env:SHEEP_REPO_ZIP } else { 'https://github.com/marcusforti/sheep/archive/refs/heads/main.zip' }
        instagram = 'https://github.com/Jakeschincariol/instagram-agent-skill/archive/refs/heads/main.zip'
        carrossel = 'https://github.com/marcusforti/carrossel-tweet/archive/refs/heads/main.zip'
        superpowers = 'https://github.com/obra/superpowers/archive/refs/heads/main.zip'
        prompt    = 'https://raw.githubusercontent.com/marcusforti/sheep/main/modelo/prompt-mestre.md'
        voz       = if ($env:SHEEP_VOZ_ZIP) { $env:SHEEP_VOZ_ZIP } else { 'https://raw.githubusercontent.com/marcusforti/sheep/main/instalador/voz.zip' }
        ytdlp     = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
        claudeApp = "https://claude.ai/api/desktop/win32/$arquitetura/msix/latest/redirect"
    }

    # Cada etapa tem uma fala. Atrasou, toca so a mais recente; as obrigatorias nunca sao puladas.
    $clipes = @{
        'Git' = 'git'; 'Node' = 'node'; 'Python' = 'python'; 'ffmpeg' = 'ffmpeg'; 'Claude Code' = 'claude'; 'Codex' = 'codex'
        'Orca' = 'orca'; 'Casa da Sheep' = 'casa'; 'Skills' = 'skills'; 'Superpowers' = 'superpowers'; 'Video' = 'video'; 'App do Claude' = 'apps'
    }
    $vozPasta = Join-Path $env:TEMP 'sheep-voz'
    $voz = [hashtable]::Synchronized(@{ Fila = New-Object System.Collections.ArrayList; Pasta = $vozPasta; Fim = $false; Tocador = $null; Espera = $null })

    # Roda em outra thread. SoundPlayer com WAV funciona ate no Windows N, que nao tem codec de MP3.
    $tocaFalas = {
        param($v)
        $player = New-Object System.Media.SoundPlayer
        while ($true) {
            $proxima = $null
            [System.Threading.Monitor]::Enter($v.Fila)
            try {
                $etapas = @($v.Fila.ToArray() | Where-Object { -not $_.Obrigatoria })
                if ($etapas.Count -gt 1) { foreach ($velha in $etapas[0..($etapas.Count - 2)]) { $v.Fila.Remove($velha) } }
                if ($v.Fila.Count -gt 0) { $proxima = $v.Fila[0]; $v.Fila.RemoveAt(0) }
            } finally { [System.Threading.Monitor]::Exit($v.Fila) }
            if ($proxima) {
                try { $player.SoundLocation = Join-Path $v.Pasta "$($proxima.Clipe).wav"; $player.PlaySync() } catch {}
            } elseif ($v.Fim) {
                return
            } else {
                Start-Sleep -Milliseconds 150
            }
        }
    }

    function Fala($texto) { Write-Host "`n[Sheep] $texto" -ForegroundColor Red }
    function Diz($clipe, [switch]$Obrigatoria) {
        if (-not $clipe -or -not $voz.Tocador) { return }
        try {
            [System.Threading.Monitor]::Enter($voz.Fila)
            try { [void]$voz.Fila.Add(@{ Clipe = $clipe; Obrigatoria = [bool]$Obrigatoria }) }
            finally { [System.Threading.Monitor]::Exit($voz.Fila) }
        } catch {}
    }

    function Passo($nome, $estado, $cor) { [void]$resultado.Add([pscustomobject]@{ Nome = $nome; Estado = $estado; Cor = $cor }) }

    function Baixa($url, $destino) {
        $curl = Join-Path $env:WINDIR 'System32\curl.exe'
        if (Test-Path $curl) {
            & $curl -fL --retry 4 --retry-delay 3 --connect-timeout 25 --speed-limit 20000 --speed-time 30 -# -o $destino $url
            if ($LASTEXITCODE -ne 0) { throw "download falhou ($url)" }
        } else {
            Invoke-WebRequest -Uri $url -OutFile $destino -UseBasicParsing
        }
    }

    function Extrai($zip, $pasta) {
        New-Item -ItemType Directory -Force $pasta | Out-Null
        $tar = Join-Path $env:WINDIR 'System32\tar.exe'
        if (Test-Path $tar) {
            & $tar -xf $zip -C $pasta
            if ($LASTEXITCODE -ne 0) { throw "nao consegui extrair $zip" }
        } else {
            Expand-Archive -LiteralPath $zip -DestinationPath $pasta -Force
        }
    }

    # A voz e enfeite: qualquer falha aqui fica muda e a instalacao segue.
    function VozLiga {
        if ($env:SHEEP_SEM_VOZ -eq '1') { return }
        try {
            if (Test-Path $vozPasta) { Remove-Item -Recurse -Force $vozPasta }
            New-Item -ItemType Directory -Force $vozPasta | Out-Null
            $arquivo = Join-Path $vozPasta 'voz.zip'
            Write-Host '  Trazendo a minha voz...'
            Baixa $urls.voz $arquivo
            Extrai $arquivo $vozPasta
            $tocador = [powershell]::Create()
            [void]$tocador.AddScript($tocaFalas).AddArgument($voz)
            $voz.Espera = $tocador.BeginInvoke()
            $voz.Tocador = $tocador
        } catch {
            Add-Content -LiteralPath $log -Value "Voz : $_" -ErrorAction SilentlyContinue
            Write-Host '  Sem voz desta vez. O resto segue normal.'
        }
    }

    # Sem isto o painel abre o assistente antigo e pode rodar winget e npm de novo.
    function MarcaInstalacao {
        $pasta = Join-Path $casa '.instalacao'
        $arquivo = Join-Path $pasta 'estado.json'
        New-Item -ItemType Directory -Force $pasta | Out-Null
        $estado = @{}
        if (Test-Path $arquivo) {
            try { (Get-Content -LiteralPath $arquivo -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $estado[$_.Name] = $_.Value } } catch {}
        }
        foreach ($id in 'boas_vindas', 'verificar', 'base', 'cerebros', 'casa') { $estado[$id] = 'feito' }
        [IO.File]::WriteAllText($arquivo, ($estado | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
    }

    # Espera a ultima fala acabar, porque o painel abre com audio proprio.
    function VozFim($segundos) {
        if (-not $voz.Tocador) { return }
        try {
            $voz.Fim = $true
            $limite = (Get-Date).AddSeconds($segundos)
            while (-not $voz.Espera.IsCompleted -and (Get-Date) -lt $limite) { Start-Sleep -Milliseconds 200 }
            [System.Threading.Monitor]::Enter($voz.Fila)
            try { $voz.Fila.Clear() } finally { [System.Threading.Monitor]::Exit($voz.Fila) }
            if ($voz.Espera.IsCompleted) { $voz.Tocador.Dispose() }
        } catch {}
        Remove-Item -Recurse -Force $vozPasta -ErrorAction SilentlyContinue
    }

    function PoePath($pasta) {
        if (-not $teste) {
            $atual = @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';' | Where-Object { $_ })
            if ($atual -notcontains $pasta) {
                [Environment]::SetEnvironmentVariable('Path', ((@($pasta) + $atual) -join ';'), 'User')
            }
        }
        if (($env:Path -split ';') -notcontains $pasta) { $env:Path = "$pasta;$env:Path" }
    }

    function RecarregaPath {
        if ($teste) { return }
        $maquina = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $usuario = [Environment]::GetEnvironmentVariable('Path', 'User')
        $env:Path = "$usuario;$maquina"
    }

    function Tem($comando) { [bool](Get-Command $comando -ErrorAction SilentlyContinue) }

    function NodeBom {
        if (-not (Tem 'node')) { return $false }
        try { return [int]((& node -v) -replace '^v(\d+)\..*', '$1') -ge 20 } catch { return $false }
    }

    # O "python" da Microsoft Store e um atalho falso: so vale se responder a versao.
    function PythonBom {
        if (-not (Tem 'python')) { return $false }
        try {
            $saida = cmd /c 'python --version 2>&1'
            return ($LASTEXITCODE -eq 0) -and ("$saida" -match 'Python 3\.(1[0-9]|[2-9][0-9])')
        } catch { return $false }
    }

    # Vindo do PowerShell 7, o PSModulePath herdado quebra o Windows PowerShell filho.
    function RodaInstalador($script) {
        $salvo = $env:PSModulePath
        Remove-Item Env:\PSModulePath -ErrorAction SilentlyContinue
        try { & $powershell -NoProfile -ExecutionPolicy Bypass -File $script }
        finally { $env:PSModulePath = $salvo }
    }

    # App da loja so responde no Windows PowerShell; o processo filho nao pode herdar modulos do PowerShell 7.
    function RodaNoWindowsPowerShell($comando) {
        $salvo = $env:PSModulePath
        Remove-Item Env:\PSModulePath -ErrorAction SilentlyContinue
        try {
            & $powershell -NoProfile -ExecutionPolicy Bypass -Command $comando | Out-Null
            return $LASTEXITCODE -eq 0
        } finally { $env:PSModulePath = $salvo }
    }

    function TemApp($pacote) { RodaNoWindowsPowerShell "if (Get-AppxPackage -Name '$pacote') { exit 0 } else { exit 1 }" }

    function Etapa($nome, [scriptblock]$jaTem, [scriptblock]$instala, [switch]$Opcional) {
        Fala "$nome..."
        Diz $clipes[$nome]
        $falha = if ($Opcional) { 'opcional, ficou de fora' } else { 'FALHOU' }
        try {
            if (& $jaTem) { Write-Host '  ja estava instalado'; Passo $nome 'ja tinha' 'Gray'; return }
            & $instala
            if (& $jaTem) { Passo $nome 'instalado' 'Green' }
            else { Passo $nome "$falha (instalou mas nao respondeu)" 'Yellow' }
        } catch {
            Write-Host "  erro: $_" -ForegroundColor Yellow
            Add-Content -LiteralPath $log -Value "$nome : $_"
            Passo $nome "${falha}: $_" 'Yellow'
        }
    }

    function CopiaSkills($origem) {
        # O painel so le as pastas do projeto; o terminal le as do usuario.
        foreach ($alvo in (Join-Path $env:USERPROFILE '.claude\skills'), (Join-Path $env:USERPROFILE '.agents\skills'), (Join-Path $casa '.claude\skills'), (Join-Path $casa '.agents\skills')) {
            New-Item -ItemType Directory -Force $alvo | Out-Null
            foreach ($skill in Get-ChildItem $origem -Directory) {
                if (-not (Test-Path (Join-Path $skill.FullName 'SKILL.md'))) { continue }
                $destino = Join-Path $alvo $skill.Name
                if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
                Copy-Item -Recurse -Force $skill.FullName $destino
            }
        }
    }

    # Abertura no estilo neofetch: a ovelha de olhos vermelhos e os dados do computador.
    function Abertura($livre) {
        $arte = @(
            '        .;;;;;;;;;;.        ',
            '     .;;;;;;;;;;;;;;;;.     ',
            '   _;;;;;;;;;;;;;;;;;;;;_   ',
            '  /_);;   .--.  .--.   ;;(_\',
            '     ;;   | O|  |O |   ;;   ',
            '     ;;   ''--''  ''--''   ;;   ',
            '      ;;      __      ;;    ',
            '       '';.   \__/   .;''     ',
            '         '';;;;;;;;;;''       '
        )
        try {
            $sistema = (Get-CimInstance Win32_OperatingSystem).Caption -replace 'Microsoft ', ''
            $memoria = "$([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)) GB"
        } catch { $sistema = 'Windows'; $memoria = '?' }
        $dados = @(
            @('SHEEP', 'a agente dos Incomparaveis'),
            @('', ''),
            @('Dono', $env:USERNAME),
            @('Computador', $env:COMPUTERNAME),
            @('Sistema', $sistema),
            @('Memoria', $memoria),
            @('Disco livre', "$([math]::Round($livre / 1GB)) GB"),
            @('', ''),
            @('Mudando pro seu computador.', 'Leva de 5 a 20 minutos.')
        )
        # Letreiro em blocos, montado aqui para o arquivo continuar em ASCII.
        $letreiro = @(
            '#######\##\  ##\#######\#######\######\ ',
            '##/====J##|  ##|##/====J##/====J##/==##\',
            '#######\#######|#####\  #####\  ######/J',
            'L====##|##/==##|##/==J  ##/==J  ##/===J ',
            '#######|##|  ##|#######\#######\##|     ',
            'L======JL=J  L=JL======JL======JL=J     '
        )
        $blocos = @{ '#' = 0x2588; '=' = 0x2550; '|' = 0x2551; '/' = 0x2554; '\' = 0x2557; 'L' = 0x255A; 'J' = 0x255D }
        Write-Host ''
        foreach ($linha in $letreiro) {
            $texto = -join ($linha.ToCharArray() | ForEach-Object { if ($blocos.ContainsKey("$_")) { [char]$blocos["$_"] } else { $_ } })
            Write-Host "  $texto" -ForegroundColor Red
        }
        Write-Host ''
        for ($i = 0; $i -lt $arte.Count; $i++) {
            foreach ($pedaco in ($arte[$i] -split '(O)')) {
                if ($pedaco -ceq 'O') { Write-Host $pedaco -NoNewline -ForegroundColor Red }
                else { Write-Host $pedaco -NoNewline }
            }
            Write-Host "  $($dados[$i][0]) " -NoNewline -ForegroundColor Red
            Write-Host $dados[$i][1]
        }
    }

    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    New-Item -ItemType Directory -Force $tmp, $programas, $binarios | Out-Null
    RecarregaPath
    $livre = (Get-PSDrive -Name ($env:LOCALAPPDATA.Substring(0, 1))).Free
    Abertura $livre

    if ($livre -lt 4GB) {
        Write-Host "`nFaltou espaco: precisa de 4 GB livres e tem $([math]::Round($livre / 1GB, 1)) GB." -ForegroundColor Yellow
        return
    }

    Write-Host ''
    VozLiga
    Diz 'abertura' -Obrigatoria

    # Enquanto instala, a pessoa puxa a propria memoria do Claude ou do ChatGPT.
    $motor = ''
    if (-not $teste) {
        Diz 'pergunta' -Obrigatoria
        do {
            Write-Host "`nQual IA paga voce usa?  1 = Claude   2 = ChatGPT   3 = nenhuma"
            $resposta = "$(Read-Host 'Digite 1, 2 ou 3 e aperte Enter')".Trim()
        } until ($resposta -in '1', '2', '3')
        if ($resposta -eq '1') { $motor = 'claude'; $endereco = 'https://claude.ai/new' }
        if ($resposta -eq '2') { $motor = 'codex'; $endereco = 'https://chatgpt.com/' }
        if ($motor) {
            try {
                $arquivo = Join-Path $tmp 'prompt-mestre.md'
                Baixa $urls.prompt $arquivo
                Get-Content -LiteralPath $arquivo -Raw -Encoding UTF8 | Set-Clipboard
                Start-Process $endereco
                Diz 'prompt' -Obrigatoria
                Write-Host ''
                Write-Host '  ENQUANTO EU INSTALO, FAZ ISSO:' -ForegroundColor Red
                Write-Host '  Abri a sua IA no navegador e ja copiei um prompt pra voce.'
                Write-Host '  1. Clique na caixa de mensagem, aperte Ctrl+V e envie.'
                Write-Host '  2. Quando ela responder, copie a resposta inteira.'
                Write-Host '  3. Quando eu abrir, cole essa resposta pra mim.'
                Write-Host '  Sua memoria vem junto comigo. Pode ir que eu sigo instalando.'
            } catch {
                Write-Host '  Nao consegui abrir o prompt agora. Ele fica em prompt-mestre.md, na pasta Sheep, e no botao Copiar prompt mestre do painel.' -ForegroundColor Yellow
            }
        }
    }

    Diz 'lista' -Obrigatoria

    Etapa 'Git' { Tem 'git' } {
        $destino = Join-Path $programas 'Git'
        $arquivo = Join-Path $tmp 'PortableGit.7z.exe'
        Baixa $urls.git $arquivo
        # Esse pacote ignora -o e sempre extrai em .\PortableGit, ao lado dele.
        Start-Process -FilePath $arquivo -ArgumentList '-y', '-gm2' -WorkingDirectory $tmp -Wait
        if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
        Move-Item (Join-Path $tmp 'PortableGit') $destino
        PoePath (Join-Path $destino 'cmd')
        $bash = Join-Path $destino 'bin\bash.exe'
        $env:CLAUDE_CODE_GIT_BASH_PATH = $bash
        if (-not $teste) { [Environment]::SetEnvironmentVariable('CLAUDE_CODE_GIT_BASH_PATH', $bash, 'User') }
    }

    Etapa 'Node' { NodeBom } {
        $arquivo = Join-Path $tmp 'node.zip'
        $destino = Join-Path $programas 'nodejs-sheep'
        Baixa $urls.node $arquivo
        if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
        Extrai $arquivo $tmp
        Move-Item (Get-ChildItem $tmp -Directory -Filter 'node-v*' | Select-Object -First 1).FullName $destino
        PoePath $destino
    }

    Etapa 'Python' { PythonBom } {
        $arquivo = Join-Path $tmp 'python.zip'
        $pacote = Join-Path $tmp 'python-pacote'
        $destino = Join-Path $programas 'Python313-sheep'
        Baixa $urls.python $arquivo
        if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
        Extrai $arquivo $pacote
        Move-Item (Join-Path $pacote 'tools') $destino
        PoePath (Join-Path $destino 'Scripts')
        PoePath $destino
    }

    Etapa 'ffmpeg' { Tem 'ffmpeg' } {
        $arquivo = Join-Path $tmp 'ffmpeg.zip'
        $destino = Join-Path $programas 'ffmpeg-sheep'
        Baixa $urls.ffmpeg $arquivo
        if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
        Extrai $arquivo $tmp
        Move-Item (Get-ChildItem $tmp -Directory -Filter 'ffmpeg-*' | Select-Object -First 1).FullName $destino
        PoePath (Join-Path $destino 'bin')
    }

    Etapa 'Claude Code' { Tem 'claude' } {
        $script = Join-Path $tmp 'claude.ps1'
        Baixa 'https://claude.ai/install.ps1' $script
        RodaInstalador $script
        PoePath $binarios
    }

    Etapa 'Codex' { Tem 'codex' } {
        $script = Join-Path $tmp 'codex.ps1'
        $env:CODEX_NON_INTERACTIVE = '1'
        Baixa 'https://chatgpt.com/codex/install.ps1' $script
        RodaInstalador $script
        PoePath (Join-Path $env:LOCALAPPDATA 'Programs\OpenAI\Codex\bin')
    }

    # A casa e as skills baixam sempre, para pegar a versao mais recente.
    $feito = @{ casa = $false; skills = $false; superpowers = $false; video = $false }

    Etapa 'Casa da Sheep' { $feito.casa } {
        $arquivo = Join-Path $tmp 'sheep.zip'
        Baixa $urls.sheep $arquivo
        Extrai $arquivo (Join-Path $tmp 'repo-sheep')
        $modelo = Join-Path $tmp 'repo-sheep\sheep-main\modelo'
        foreach ($item in Get-ChildItem $modelo -Recurse -File -Force) {
            $relativo = $item.FullName.Substring($modelo.Length + 1)
            $destino = Join-Path $casa $relativo
            if (($relativo -like 'casa\*' -or $relativo -like 'memoria\*') -and (Test-Path $destino)) { continue }
            New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
            Copy-Item -LiteralPath $item.FullName -Destination $destino -Force
        }
        $appOrigem = Join-Path $tmp 'repo-sheep\sheep-main\app'
        $appDestino = Join-Path $programas 'Sheep'
        if (Test-Path $appDestino) { Remove-Item -Recurse -Force $appDestino }
        Copy-Item -Recurse -Force $appOrigem $appDestino
        $bat = @'
@echo off
cd /d "%USERPROFILE%\Sheep"
if /i "%~1"=="claude" (>.motor echo claude)
if /i "%~1"=="codex" (>.motor echo codex)
if "%~1"=="" (
  where pythonw >nul 2>nul || goto semPainel
  pushd "%LOCALAPPDATA%\Programs\Sheep"
  python -c "import painel" >nul 2>nul
  if errorlevel 1 (popd & goto semPainel)
  popd
  start "" pythonw "%LOCALAPPDATA%\Programs\Sheep\painel.py"
  exit /b
)
if not exist .motor (>.motor echo claude)
set /p MOTOR=<.motor
if not exist casa\dono.md echo.
if not exist casa\dono.md echo Se perguntar se voce confia na pasta: aperte a SETA PARA BAIXO, escolha Yes e aperte ENTER.
if not exist casa\dono.md echo.
if exist casa\dono.md (call %MOTOR%) else (call %MOTOR% "Oi Sheep, acabei de te instalar. Vamos comecar?")
exit /b
:semPainel
start "Sheep" cmd /k echo Nao consegui abrir o painel. Digite: sheep claude
'@
        Set-Content -LiteralPath $inicio -Value $bat -Encoding Ascii
        if ($motor) { Set-Content -LiteralPath (Join-Path $casa '.motor') -Value $motor -Encoding Ascii }
        PoePath $binarios
        $feito.casa = $true
    }

    Etapa 'Skills' { $feito.skills } {
        foreach ($nome in 'instagram', 'carrossel') {
            $arquivo = Join-Path $tmp "$nome.zip"
            $pasta = Join-Path $tmp "repo-$nome"
            Baixa $urls[$nome] $arquivo
            Extrai $arquivo $pasta
        }
        CopiaSkills (Join-Path $tmp 'repo-instagram\instagram-agent-skill-main\skills')
        $carrossel = Join-Path $tmp 'skills-carrossel'
        New-Item -ItemType Directory -Force $carrossel | Out-Null
        Move-Item (Join-Path $tmp 'repo-carrossel\carrossel-tweet-main') (Join-Path $carrossel 'carrossel-tweet')
        CopiaSkills $carrossel
        $feito.skills = $true
    }

    Etapa 'Superpowers' { $feito.superpowers } {
        $arquivo = Join-Path $tmp 'superpowers.zip'
        $pasta = Join-Path $tmp 'repo-superpowers'
        Baixa $urls.superpowers $arquivo
        Extrai $arquivo $pasta
        CopiaSkills (Join-Path $pasta 'superpowers-main\skills')
        $feito.superpowers = $true
    }

    # yt-dlp sem login: baixa video publico do YouTube, Instagram e TikTok para a skill assistir-video.
    Etapa 'Video' { $feito.video } {
        Baixa $urls.ytdlp (Join-Path $binarios 'yt-dlp.exe')
        CopiaSkills (Join-Path $tmp 'repo-sheep\sheep-main\instalador\skills')
        PoePath $binarios
        $feito.video = $true
    }

    # O Orca vem depois da Casa e das Skills: se o Wi-Fi engasgar, a Sheep ja esta pronta.
    if ($teste -or $env:SHEEP_SEM_ORCA -eq '1') {
        Passo 'Orca' 'pulado' 'Gray'
    } else {
        Etapa 'Orca' { Test-Path (Join-Path $programas 'orca\Orca.exe') } {
            $arquivo = Join-Path $tmp 'orca-setup.exe'
            Baixa $urls.orca $arquivo
            Start-Process -FilePath $arquivo -ArgumentList '/S' -Wait
        }
    }

    # Os aplicativos sao os downloads maiores: vem por ultimo e, se falharem, nao atrapalham o resto.
    if ($teste -or $env:SHEEP_SEM_APPS -eq '1') {
        Passo 'Apps' 'pulado' 'Gray'
    } elseif ($livre -lt 8GB) {
        Passo 'Apps' 'opcional, ficou de fora: pouco espaco no disco' 'Yellow'
    } else {
        Etapa 'App do Claude' { (TemApp 'AnthropicPBC.Claude') -or (Test-Path (Join-Path $env:LOCALAPPDATA 'AnthropicClaude\claude.exe')) } {
            $arquivo = Join-Path $tmp 'Claude.msix'
            Baixa $urls.claudeApp $arquivo
            $caminho = $arquivo.Replace("'", "''")
            if (-not (RodaNoWindowsPowerShell "try { Add-AppxPackage -Path '$caminho' -ErrorAction Stop; exit 0 } catch { exit 1 }")) { throw 'baixe em claude.com/download' }
        } -Opcional

        Etapa 'App do Codex' { TemApp 'OpenAI.Codex' } {
            $winget = Get-Command winget -ErrorAction SilentlyContinue
            if ($winget) {
                $processo = Start-Process -FilePath $winget.Source -ArgumentList 'install', '--id', '9PLM9XGG6VKS', '-s', 'msstore', '--accept-package-agreements', '--accept-source-agreements', '--silent' -NoNewWindow -PassThru
                if (-not $processo.WaitForExit(600000)) { Stop-Process -Id $processo.Id -Force -ErrorAction SilentlyContinue }
            }
            if (-not (TemApp 'OpenAI.Codex')) {
                Start-Process 'ms-windows-store://pdp/?productid=9PLM9XGG6VKS'
                throw 'abri a Microsoft Store: clique em Obter'
            }
        } -Opcional
    }

    if ((Test-Path $inicio) -and -not $teste) {
        $atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Sheep.lnk'))
        $atalho.TargetPath = $inicio
        $atalho.WindowStyle = 7
        $atalho.WorkingDirectory = $casa
        $atalho.IconLocation = Join-Path $casa 'sheep.ico'
        $atalho.Save()
    }

    if ($feito.casa) { MarcaInstalacao }

    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

    Write-Host "`n  ------------- RESUMO -------------"
    foreach ($r in $resultado) { Write-Host ('  {0,-14} {1}' -f $r.Nome, $r.Estado) -ForegroundColor $r.Cor }
    $falhou = @($resultado | Where-Object { $_.Estado -like 'FALHOU*' })
    if ($falhou.Count -gt 0) {
        Write-Host "`nFaltou $($falhou.Count) item. Roda o mesmo comando de novo. Se repetir, levanta a mao e mostra esta tela." -ForegroundColor Yellow
        Write-Host "Registro: $log"
        Diz 'fim_falha' -Obrigatoria
    } else {
        Diz 'fim_ok' -Obrigatoria
    }
    VozFim 25
    if ((Test-Path $inicio) -and -not $teste) {
        Fala 'Abrindo o meu painel. Daqui pra frente e so clicar no atalho Sheep na area de trabalho.'
        Start-Process -FilePath $inicio -WindowStyle Minimized
    }
}
