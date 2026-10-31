# Sheep

A agente dos Incomparáveis, instalada no seu computador com uma linha. Criada por Marcus Forti.

Ela responde clientes, cuida do Instagram e trabalha do seu lado com Claude Code ou Codex. Os arquivos e a memória ficam no seu computador, e nada sai sem o seu sim.

## Instalar no Windows

Aperte a tecla Windows, digite `PowerShell` e aperte Enter. Cole a linha abaixo com o botão direito do mouse e aperte Enter:

```powershell
irm https://raw.githubusercontent.com/marcusforti/sheep/main/instalar.ps1 | iex
```

## Instalar no Mac

Aperte Command + Espaço, digite `Terminal` e aperte Enter. Cole a linha abaixo e aperte Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/instalar.sh | bash
```

## O que vem junto

Git, Node.js, Python, ffmpeg, Claude Code, Codex, Orca, a casa da Sheep na pasta `Sheep`, as skills de Instagram e carrossel, o [Superpowers](https://github.com/obra/superpowers) (MIT), o [yt-dlp](https://github.com/yt-dlp/yt-dlp) com a skill `assistir-video` e, se der, os aplicativos do Claude e do Codex. Leva de 5 a 20 minutos, com a Sheep falando o que está acontecendo, e a tela dela só abre quando tudo termina. Se a internet cair, rode a mesma linha de novo. Para pular a voz, defina `SHEEP_SEM_VOZ=1` antes de rodar; para pular o Orca, `SHEEP_SEM_ORCA=1`; para pular os aplicativos, `SHEEP_SEM_APPS=1`.

## Enquanto instala

A instalação abre a sua IA no navegador e copia o [prompt mestre](modelo/prompt-mestre.md). Cole lá, envie e guarde a resposta: ela traz o que a sua IA já sabe sobre você e o seu negócio. Depois, é só colar a resposta na Sheep.

## Depois de instalar

No Windows, clique no atalho **Sheep** na área de trabalho ou digite `sheep` no terminal: abre o painel dela. No Mac, digite `sheep` no terminal.

Para usar no terminal: `sheep claude` ou `sheep codex`. Quando ele perguntar se você confia na pasta, escolha **Yes** com a seta para baixo.

Quer outro nome para o seu agente? Peça para ela. Boa sorte: a Sheep não vai facilitar.

## Dicionário

Palavra técnica travou você? Busque aqui: https://imersao-operacao-ia.marcusforti2.workers.dev/dicionario/
