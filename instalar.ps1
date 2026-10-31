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

    $urls = @{
        git       = 'https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.4/PortableGit-2.56.0.4-64-bit.7z.exe'
        node      = 'https://nodejs.org/dist/v26.13.0/node-v26.13.0-win-x64.zip'
        python    = 'https://www.nuget.org/api/v2/package/python/3.13.17'
        ffmpeg    = 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip'
        orca      = 'https://github.com/stablyai/orca/releases/latest/download/orca-windows-setup.exe'
        sheep     = 'https://github.com/marcusforti/sheep/archive/refs/heads/main.zip'
        instagram = 'https://github.com/Jakeschincariol/instagram-agent-skill/archive/refs/heads/main.zip'
        carrossel = 'https://github.com/marcusforti/carrossel-tweet/archive/refs/heads/main.zip'
        prompt    = 'https://raw.githubusercontent.com/marcusforti/sheep/main/modelo/prompt-mestre.md'
    }

    function Fala($texto) { Write-Host "`n[Sheep] $texto" -ForegroundColor Red }
    function Passo($nome, $estado, $cor) { [void]$resultado.Add([pscustomobject]@{ Nome = $nome; Estado = $estado; Cor = $cor }) }

    function Baixa($url, $destino) {
        $curl = Join-Path $env:WINDIR 'System32\curl.exe'
        if (Test-Path $curl) {
            & $curl -fL --retry 4 --retry-delay 3 --connect-timeout 25 -# -o $destino $url
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

    function Etapa($nome, [scriptblock]$jaTem, [scriptblock]$instala) {
        Fala "$nome..."
        try {
            if (& $jaTem) { Write-Host '  ja estava instalado'; Passo $nome 'ja tinha' 'Gray'; return }
            & $instala
            if (& $jaTem) { Passo $nome 'instalado' 'Green' }
            else { Passo $nome 'FALHOU (instalou mas nao respondeu)' 'Yellow' }
        } catch {
            Write-Host "  erro: $_" -ForegroundColor Yellow
            Add-Content -LiteralPath $log -Value "$nome : $_"
            Passo $nome "FALHOU: $_" 'Yellow'
        }
    }

    function CopiaSkills($origem) {
        foreach ($alvo in (Join-Path $env:USERPROFILE '.claude\skills'), (Join-Path $env:USERPROFILE '.agents\skills')) {
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
            @('Mudando pro seu computador.', 'Leva de 5 a 15 minutos.')
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

    # Enquanto instala, a pessoa puxa a propria memoria do Claude ou do ChatGPT.
    $motor = ''
    if (-not $teste) {
        Write-Host "`nQual IA paga voce usa?  1 = Claude   2 = ChatGPT   3 = nenhuma"
        $resposta = Read-Host 'Digite 1, 2 ou 3 e aperte Enter'
        if ($resposta -eq '1') { $motor = 'claude'; $endereco = 'https://claude.ai/new' }
        if ($resposta -eq '2') { $motor = 'codex'; $endereco = 'https://chatgpt.com/' }
        if ($motor) {
            try {
                $arquivo = Join-Path $tmp 'prompt-mestre.md'
                Baixa $urls.prompt $arquivo
                Get-Content -LiteralPath $arquivo -Raw -Encoding UTF8 | Set-Clipboard
                Start-Process $endereco
                Write-Host ''
                Write-Host '  ENQUANTO EU INSTALO, FAZ ISSO:' -ForegroundColor Red
                Write-Host '  Abri a sua IA no navegador e ja copiei um prompt pra voce.'
                Write-Host '  1. Clique na caixa de mensagem, aperte Ctrl+V e envie.'
                Write-Host '  2. Quando ela responder, copie a resposta inteira.'
                Write-Host '  3. Quando eu abrir, cole essa resposta pra mim.'
                Write-Host '  Sua memoria vem junto comigo. Pode ir que eu sigo instalando.'
            } catch {
                Write-Host '  Nao consegui abrir o prompt agora. Eu te mostro de novo quando abrir.' -ForegroundColor Yellow
            }
        }
    }

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

    if ($teste) {
        Passo 'Orca' 'pulado no teste' 'Gray'
    } else {
        Etapa 'Orca' { Test-Path (Join-Path $programas 'orca\Orca.exe') } {
            $arquivo = Join-Path $tmp 'orca-setup.exe'
            Baixa $urls.orca $arquivo
            Start-Process -FilePath $arquivo -ArgumentList '/S' -Wait
        }
    }

    # A casa e as skills baixam sempre, para pegar a versao mais recente.
    $feito = @{ casa = $false; skills = $false }

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
  start "" pythonw "%LOCALAPPDATA%\Programs\Sheep\painel.py"
  exit /b
)
if not exist .motor (>.motor echo claude)
set /p MOTOR=<.motor
if not exist casa\dono.md echo.
if not exist casa\dono.md echo Se perguntar se voce confia na pasta: aperte a SETA PARA BAIXO, escolha Yes e aperte ENTER.
if not exist casa\dono.md echo.
if exist casa\dono.md (call %MOTOR%) else (call %MOTOR% "Oi Sheep, acabei de te instalar. Vamos comecar?")
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

    if ((Test-Path $inicio) -and -not $teste) {
        $atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Sheep.lnk'))
        $atalho.TargetPath = $inicio
        $atalho.WindowStyle = 7
        $atalho.WorkingDirectory = $casa
        $atalho.IconLocation = Join-Path $casa 'sheep.ico'
        $atalho.Save()
    }

    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

    Write-Host "`n  ------------- RESUMO -------------"
    foreach ($r in $resultado) { Write-Host ('  {0,-14} {1}' -f $r.Nome, $r.Estado) -ForegroundColor $r.Cor }
    $falhou = @($resultado | Where-Object { $_.Estado -like 'FALHOU*' })
    if ($falhou.Count -gt 0) {
        Write-Host "`nFaltou $($falhou.Count) item. Roda o mesmo comando de novo. Se repetir, levanta a mao e mostra esta tela." -ForegroundColor Yellow
        Write-Host "Registro: $log"
    }
    if ((Test-Path $inicio) -and -not $teste) {
        Fala 'Abrindo o meu painel. Daqui pra frente e so clicar no atalho Sheep na area de trabalho.'
        Start-Process -FilePath $inicio -WindowStyle Minimized
    }
}
