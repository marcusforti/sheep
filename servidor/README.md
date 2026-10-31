# WhatsApp no ar 24 horas: servidor na Oracle com a Evolution

Este guia cria um servidor gratuito na Oracle, instala a Evolution e conecta o seu WhatsApp, para o seu agente poder ler e mandar mensagens mesmo com o notebook desligado.

Leva de 30 a 60 minutos. A maior parte do tempo é espera.

## Comece aqui

Abra o Claude Code ou o Codex e cole esta mensagem:

```text
Leia https://raw.githubusercontent.com/marcusforti/sheep/main/servidor/README.md inteiro e me guie, uma etapa por vez, para criar o meu servidor na Oracle e conectar o meu WhatsApp. Siga a seção "Regras para o agente". Se não conseguir abrir o link, me diga para abrir no navegador e colar o texto aqui. Comece perguntando se eu já tenho conta na Oracle e qual número de WhatsApp vou usar.
```

Prefere fazer sem agente? Siga as etapas abaixo na ordem.

## O que você precisa ter

- Um e-mail e um celular que recebam código.
- Um cartão de crédito no seu nome. A conta gratuita não cobra, mas a Oracle faz uma verificação no cartão. Cartão pré-pago ou virtual pode ser recusado.
- Um computador com navegador.
- Um celular com o WhatsApp que você vai conectar.

## Etapa 1: escolha o número

Você pode conectar o seu número atual ou um número novo só para o agente.

**Recomendo um número novo.** Se o WhatsApp bloquear o número do agente, o seu número pessoal fica fora disso.

**Quem quiser um número novo pode usar o eSIM da Fluke:**

1. Confira se o seu celular aceita eSIM. A Fluke pede um aparelho com EID: digite `*#06#` e veja se esse código aparece. Se não aparecer, procure o modelo do celular no app dela antes de pagar.
2. Cadastre-se no app ou no site da Fluke: https://flu.ke
3. Escolha eSIM e siga o passo a passo do app. Segundo a Fluke, o eSIM fica pronto na hora.
4. Instale o eSIM no celular.
5. Crie o WhatsApp nesse número novo. O WhatsApp Business serve bem: ele roda no mesmo celular, ao lado do WhatsApp comum.

Confira o preço no app, porque ele muda conforme o plano.

## Etapa 2: crie a conta na Oracle

Quem faz esta etapa é você. Cartão, senha, SMS e CAPTCHA são seus.

1. Abra https://signup.oraclecloud.com
2. Preencha os dados e confirme o e-mail.
3. Em **Home Region**, escolha **Brazil East (São Paulo)**. A máquina gratuita só pode ser criada nessa região, e ela não muda depois.
4. Cadastre o cartão e conclua a verificação.
5. Espere a conta ficar pronta. Pode levar alguns minutos.

Se o cartão for recusado, tente outro cartão ou outro dia. Muitas contas criadas na mesma rede também podem ser recusadas, então faça em casa ou pelos dados do celular.

## Etapa 3: crie o servidor

1. Entre no console da Oracle: https://cloud.oracle.com
2. No topo da página, clique no ícone `>_` e escolha **Cloud Shell**.
3. Espere o terminal abrir na parte de baixo da tela.
4. Cole este comando e aperte Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/servidor/oracle.sh | bash
```

O comando faz tudo sozinho: monta a rede, cria a máquina e instala a Evolution.

Deixe a aba aberta. Quando terminar, ele mostra:

```text
Painel: http://SEU-IP:8080/manager
Chave:  uma sequência longa de letras e números
```

Guarde a chave num lugar seguro. Se fechar a tela, rode o mesmo comando de novo: ele mostra o endereço e a chave, sem criar outro servidor.

### Se aparecer "sem capacidade"

É o erro mais comum da Oracle, e não significa que a sua conta tem problema. As máquinas gratuitas de São Paulo vivem cheias.

O comando tenta sozinho a cada minuto, por 40 minutos. Se ainda não conseguir, rode de novo mais tarde. De madrugada costuma ser mais fácil.

## Etapa 4: conecte o WhatsApp

1. Abra o endereço do Painel no navegador.
2. Em **Server URL**, coloque `http://SEU-IP:8080`, sem o `/manager`.
3. Em **API Key Global**, cole a chave.
4. Clique em **Login**.
5. Clique em **Instance +**.
6. Em **Name**, escreva um nome curto, sem espaço, como `meu-whats`.
7. Em **Channel**, deixe **Baileys**.
8. Deixe o **Token** como veio. Em **Number**, coloque o número com 55 e DDD, só com dígitos.
9. Clique em **Save**.
10. Clique no nome da instância e depois em **Get QR Code**.
11. No celular, abra o WhatsApp do número escolhido e vá em **Aparelhos conectados > Conectar um aparelho**.
12. Leia o QR Code. A instância deve mudar para **Connected**.

## Etapa 5: teste

Peça ao seu agente para mandar um "oi" para um número seu. Ele usa o endereço, a chave e o nome da instância:

```bash
curl -X POST "http://SEU-IP:8080/message/sendText/meu-whats" \
  -H "Content-Type: application/json" \
  -H "apikey: SUA-CHAVE" \
  -d '{"number":"5515999999999","text":"Oi, deu certo!"}'
```

Só confie no teste quando a mensagem chegar no celular. Resposta `PENDING` significa que a Evolution aceitou, não que chegou.

## Etapa 6: ligue no seu agente

**Na Sheep:** abra o painel, vá em **Conexões**, coloque o endereço `http://SEU-IP:8080` em **Evolution: endereço** e a chave em **Evolution: chave**.

**Sem a Sheep:** guarde `EVOLUTION_URL` e `EVOLUTION_API_KEY` no arquivo `.env` do seu projeto e peça ao agente para não colocar esse arquivo no Git.

## Problemas comuns

| O que aconteceu | O que fazer |
|---|---|
| "Sem capacidade" até o fim das tentativas | Rode o mesmo comando mais tarde. |
| O Cloud Shell fechou no meio | Abra de novo e rode o mesmo comando. Ele continua de onde parou. |
| "Este comando roda no Cloud Shell" | Você colou no computador. Cole no terminal do site da Oracle. |
| O painel não abre | A instalação pode levar até 15 minutos. Espere e tente de novo. |
| O QR Code não aparece | Atualize a página, peça o QR de novo e confira a sua internet. |
| O WhatsApp desconectou | Peça o QR Code de novo na instância e leia pelo celular. |
| Aparece conectado, mas nada chega | Reconecte a instância: leia o QR de novo e faça o teste da etapa 5. |
| O servidor parou sozinho | A Oracle pode recuperar máquina gratuita parada. No console, abra **Compute > Instances** e clique em **Start**. |

## Limites e cuidados

- **Mensagem em massa bloqueia número.** A Evolution não é o canal oficial do WhatsApp. Responda a quem chamou você, mande poucas mensagens e dê intervalo entre elas.
- **Número novo pede calma.** Use como uma pessoa normal nos primeiros dias, antes de automatizar.
- **A chave dá controle total do seu WhatsApp.** Não mande em grupo, print ou chat. Se ela vazar, peça ao agente para trocar.
- **O endereço é `http`, sem cadeado.** Serve para começar. Para uso sério ou dados de clientes, peça ao agente para colocar um domínio com HTTPS.
- **Tamanho da máquina.** O comando tenta primeiro a de 6 GB e, se não houver, a de 1 GB. A de 1 GB aguenta de 1 a 3 números.
- **Gratuito tem limite.** A Oracle pode recuperar máquina gratuita considerada parada por 7 dias. Faça cópia do que for importante.

## Para apagar tudo

No console da Oracle, abra **Compute > Instances**, entre em `evolution-api`, clique em **Terminate** e marque a opção de apagar o disco. Depois, em **Networking > Virtual Cloud Networks**, apague `evolution-vcn`.

## Regras para o agente

Siga estas regras enquanto guia o dono:

1. Faça uma etapa por vez, explique em português simples e espere o dono confirmar antes de seguir.
2. Cartão, senha, SMS, CAPTCHA e confirmação de e-mail são sempre do dono. Não digite, não peça e não tente passar por CAPTCHA.
3. Avise da verificação no cartão antes de o dono começar a etapa 2.
4. Insista na região Brazil East (São Paulo) e avise que ela não muda depois.
5. O comando da etapa 3 roda no Cloud Shell da Oracle, nunca no computador do dono.
6. Se o dono colar a chave no chat, peça para trocar depois. Nunca grave a chave em arquivo que vá para o Git.
7. Se o dono mandar print, leia e diga exatamente onde clicar. Não invente nome de botão: se a tela for diferente deste guia, descreva o que está vendo e peça confirmação.
8. Nunca diga que uma mensagem foi entregue sem ver chegar. `PENDING` não é entrega.
9. Só mande mensagem para outra pessoa com o sim do dono.
10. No fim, diga o que funcionou, o que não foi testado e onde a chave ficou guardada.
