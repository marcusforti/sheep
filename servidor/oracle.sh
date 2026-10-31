#!/bin/bash
# Sheep: cria um servidor gratuito na Oracle com a Evolution API (WhatsApp).
# Rode no Cloud Shell da Oracle, que ja vem logado na conta:
#   curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/servidor/oracle.sh | bash
# Tenta a maquina Always Free de 6 GB (Arm) e depois a de 1 GB (AMD), repetindo enquanto a Oracle
# estiver sem capacidade. Pode rodar de novo: nao cria um segundo servidor.
# Passo a passo completo: servidor/README.md

C="${OCI_TENANCY:-}"
# SHEEP_PREFIXO separa um teste de qualquer servidor que ja exista na conta.
P="${SHEEP_PREFIXO:-evolution}"
ROTULO=$(echo "$P" | tr -cd "a-z0-9" | cut -c1-12)
if [ -z "$C" ]; then
    echo "Este comando roda no Cloud Shell da Oracle. Abra o icone >_ no topo do site da Oracle e cole de novo."
    exit 1
fi

fala() { printf '\n\033[31m[Sheep]\033[0m %s\n' "$1"; }
vazio() { [ -z "$1" ] || [ "$1" = "None" ] || [ "$1" = "null" ]; }

JA=$(oci compute instance list -c "$C" --display-name "$P-api" --query "data[?\"lifecycle-state\"!='TERMINATED' && \"lifecycle-state\"!='TERMINATING'] | [0].id" --raw-output 2>/dev/null)
if ! vazio "$JA"; then
    IP=$(oci compute instance list-vnics --instance-id "$JA" --query 'data[0]."public-ip"' --raw-output)
    fala "Voce ja tem um servidor: http://$IP:8080/manager"
    [ -f ~/evolution-chave.txt ] && fala "Chave: $(cat ~/evolution-chave.txt)"
    exit 0
fi

fala "Montando a rede..."
VCN=$(oci network vcn list -c "$C" --display-name "$P-vcn" --query 'data[0].id' --raw-output 2>/dev/null)
if vazio "$VCN"; then
    VCN=$(oci network vcn create -c "$C" --cidr-blocks '["10.0.0.0/16"]' --display-name "$P-vcn" --dns-label "${ROTULO}vcn" --wait-for-state AVAILABLE --query data.id --raw-output)
fi
IGW=$(oci network internet-gateway list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null)
if vazio "$IGW"; then
    IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true --display-name "$P-igw" --wait-for-state AVAILABLE --query data.id --raw-output)
fi
RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
oci network security-list update --security-list-id "$SL" --force \
    --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' \
    --ingress-security-rules '[{"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},{"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":8080,"max":8080}}}]' >/dev/null
SUB=$(oci network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null)
if vazio "$SUB"; then
    SUB=$(oci network subnet create -c "$C" --vcn-id "$VCN" --cidr-block 10.0.0.0/24 --display-name "$P-subnet" --dns-label "${ROTULO}sub" --wait-for-state AVAILABLE --query data.id --raw-output)
fi

# Reaproveita a chave de uma tentativa anterior.
CHAVE=$(cat ~/evolution-chave.txt 2>/dev/null)
[ -n "$CHAVE" ] || CHAVE=$(openssl rand -hex 24)
SENHA=$(openssl rand -hex 16)
echo "$CHAVE" > ~/evolution-chave.txt
chmod 600 ~/evolution-chave.txt
[ -f ~/.ssh/sheep_evolution ] || ssh-keygen -t ed25519 -f ~/.ssh/sheep_evolution -N '' -q

INICIO=$(mktemp)
cat > "$INICIO" <<FIM
#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
iptables -I INPUT 5 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
netfilter-persistent save || true
curl -fsSL https://get.docker.com | sh
mkdir -p /opt/evolution && cd /opt/evolution
IP=\$(curl -fsS https://ifconfig.me)
cat > .env <<ENV
SERVER_TYPE=http
SERVER_PORT=8080
SERVER_URL=http://\$IP:8080
AUTHENTICATION_API_KEY=$CHAVE
AUTHENTICATION_EXPOSE_IN_FETCH_INSTANCES=true
DEL_INSTANCE=false
LANGUAGE=pt-BR
DATABASE_ENABLED=true
DATABASE_PROVIDER=postgresql
DATABASE_CONNECTION_URI=postgresql://evolution:$SENHA@postgres:5432/evolution?schema=public
DATABASE_CONNECTION_CLIENT_NAME=evolution_exchange
DATABASE_SAVE_DATA_INSTANCE=true
DATABASE_SAVE_DATA_NEW_MESSAGE=true
DATABASE_SAVE_MESSAGE_UPDATE=true
DATABASE_SAVE_DATA_CONTACTS=true
DATABASE_SAVE_DATA_CHATS=true
DATABASE_SAVE_DATA_LABELS=true
DATABASE_SAVE_DATA_HISTORIC=true
CACHE_REDIS_ENABLED=false
CACHE_REDIS_SAVE_INSTANCES=false
CACHE_LOCAL_ENABLED=true
POSTGRES_USER=evolution
POSTGRES_PASSWORD=$SENHA
POSTGRES_DB=evolution
ENV
cat > docker-compose.yml <<'YML'
services:
  evolution-api:
    image: evoapicloud/evolution-api:v2.3.7
    container_name: evolution_api
    restart: always
    ports:
      - "8080:8080"
    env_file: .env
    environment:
      - NODE_OPTIONS=--max-old-space-size=384
    volumes:
      - evolution_instances:/evolution/instances
    depends_on:
      - postgres
  postgres:
    image: postgres:16-alpine
    container_name: evolution_postgres
    restart: always
    env_file: .env
    command: postgres -c shared_buffers=32MB -c max_connections=30 -c work_mem=2MB
    volumes:
      - postgres_data:/var/lib/postgresql/data
volumes:
  evolution_instances:
  postgres_data:
YML
docker compose up -d
FIM

imagem() {
    oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" --shape "$1"         --sort-by TIMECREATED --sort-order DESC --query "data[?!contains(\"display-name\", 'Minimal')] | [0].id" --raw-output
}
ERRO=~/evolution-erro.txt
ID=""
# Devolve 0 se criou, 1 se faltou capacidade e 2 em qualquer outra recusa.
tenta() {
    local AD="$1" FORMA="$2" IMG="$3"; shift 3
    ID=$(oci compute instance launch -c "$C" --availability-domain "$AD" --shape "$FORMA" --image-id "$IMG" --subnet-id "$SUB"         --assign-public-ip true --display-name "$P-api" --ssh-authorized-keys-file ~/.ssh/sheep_evolution.pub --user-data-file "$INICIO"         --wait-for-state RUNNING --query data.id --raw-output "$@" 2>"$ERRO")
    vazio "$ID" || return 0
    ID=""
    grep -qi "capacity" "$ERRO" && return 1
    return 2
}

IMG_ARM=$(imagem VM.Standard.A1.Flex)
IMG_AMD=$(imagem VM.Standard.E2.1.Micro)
TOTAL="${SHEEP_TENTATIVAS:-40}"
fala "Criando o servidor. Se a Oracle estiver sem capacidade, tento de novo a cada minuto, ate $TOTAL vezes. Deixe esta aba aberta."
RECUSA=0
for N in $(seq 1 "$TOTAL"); do
    RECUSA=0
    for AD in $(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]",'); do
        tenta "$AD" VM.Standard.A1.Flex "$IMG_ARM" --shape-config '{"ocpus":1,"memoryInGBs":6}'; R=$?
        [ "$R" = 0 ] && break 2
        [ "$R" = 2 ] && RECUSA=1 && cp "$ERRO" ~/evolution-erro-arm.txt
        tenta "$AD" VM.Standard.E2.1.Micro "$IMG_AMD"; R=$?
        [ "$R" = 0 ] && break 2
        [ "$R" = 2 ] && RECUSA=$((RECUSA + 1))
    done
    # As duas maquinas recusadas por outro motivo: repetir nao adianta.
    [ "$RECUSA" -ge 2 ] && break
    echo "  Tentativa $N de $TOTAL: sem capacidade."
    [ "$N" -lt "$TOTAL" ] && sleep 60
done
rm -f "$INICIO"
if vazio "$ID"; then
    if [ "$RECUSA" -ge 2 ]; then
        fala "A Oracle recusou. Motivo:"
        grep -o '"message": "[^"]*"' "$ERRO" | head -1
        fala "Mostre isso para o seu agente."
        exit 2
    fi
    fala "A Oracle continua sem maquina gratuita livre. Nao ha nada errado com a sua conta."
    fala "Rode este mesmo comando mais tarde. De madrugada costuma ser mais facil."
    exit 1
fi
IP=$(oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output)

fala "Servidor criado em $IP. Instalando a Evolution, leva de 5 a 15 minutos..."
NO_AR=""
for _ in $(seq 1 120); do
    if curl -fsS --max-time 5 "http://$IP:8080" >/dev/null 2>&1; then NO_AR=1; break; fi
    sleep 10
done

if [ -n "$NO_AR" ]; then
    fala "Pronto."
else
    fala "O servidor foi criado, mas a Evolution ainda nao respondeu. Espere 10 minutos e abra o painel."
fi
echo "  Painel: http://$IP:8080/manager"
echo "  Chave:  $CHAVE"
echo
echo "  Guarde a chave. No painel, crie uma instancia e leia o QR com o WhatsApp."
echo "  Nunca cole a chave no chat: cadastre em Conexoes, no painel da Sheep."
