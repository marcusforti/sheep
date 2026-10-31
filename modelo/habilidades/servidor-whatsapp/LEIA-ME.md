# Servidor do WhatsApp na Oracle

Use quando o dono pedir para ter o WhatsApp no ar 24h, criar a conta na Oracle ou subir a Evolution. Explique o plano em 3 etapas e faça uma de cada vez.

## 1. Criar a conta (quem faz é o dono)

Site: https://signup.oraclecloud.com

- Cartão, SMS, CAPTCHA, senha e confirmação de e-mail são sempre do dono. Eu não digito nem peço esses dados, e não tento passar por CAPTCHA.
- A conta Always Free não cobra, mas a Oracle faz uma verificação no cartão. Aviso isso antes.
- Oriente a escolher **Brazil East (São Paulo)** como região. Ela não muda depois.
- Se a Oracle recusar o cartão, tente outro cartão ou outro dia. Muita conta criada na mesma rede pode ser recusada.

Se eu tiver acesso ao navegador do dono, como o Claude in Chrome, posso preencher os campos comuns e parar nos dados sensíveis. Sem esse acesso, guio tela por tela: o dono manda um print e eu digo onde clicar.

## 2. Criar o servidor

Com a conta pronta, o dono abre o console da Oracle, clica no ícone `>_` (Cloud Shell) no topo e cola:

```bash
curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/servidor/oracle.sh | bash
```

Esse comando cria a rede e uma máquina gratuita de 1 GB, instala a Evolution e, ao final, mostra o endereço do painel e a chave. Leva uns 10 minutos.

## 3. Conectar o WhatsApp

1. O dono abre `http://IP:8080/manager` e entra com a chave.
2. Cria uma instância com um nome curto.
3. No celular: WhatsApp, Aparelhos conectados, Conectar um aparelho, ler o QR.
4. No painel da Sheep, em Conexões, o dono cadastra o endereço em "Evolution: endereço" e a chave em "Evolution: chave". Se ele colar a chave no chat, peço para trocar depois.

## Limites que eu aviso

- A máquina gratuita aguenta de 1 a 3 números.
- O endereço é `http`, sem cadeado. Para uso sério, precisa de domínio e HTTPS.
- Número de WhatsApp pode ser bloqueado se mandar mensagem em massa. Prefira responder a quem chamou, com o sim do dono.
- Enviar para terceiros continua exigindo o sim do dono, sempre.
