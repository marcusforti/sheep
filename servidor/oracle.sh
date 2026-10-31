#!/bin/bash
# Sheep: cria um servidor gratuito na Oracle com a Evolution API (WhatsApp).
# Rode no Cloud Shell da Oracle, que ja vem logado na conta:
#   curl -fsSL https://raw.githubusercontent.com/marcusforti/sheep/main/servidor/oracle.sh | bash
# Usa a maquina Always Free de 1 GB, que aguenta de 1 a 3 numeros. Pode rodar de novo.

C="${OCI_TENANCY:-}"
if [ -z "$C" ]; then
    echo "Este comando roda no Cloud Shell da Oracle. Abra o icone >_ no topo do site da Oracle e cole de novo."
    exit 1
fi

fala() { printf '\n\033[31m[Sheep]\033[0m %s\n' "$1"; }
vazio() { [ -z "$1" ] || [ "$1" = "None" ] || [ "$1" = "null" ]; }

JA=$(oci compute instance list -c "$C" --display-name evolution-api --lifecycle-state RUNNING --query 'data[0].id' --raw-output 2>/dev/null)
if ! vazio "$JA"; then
    IP=$(oci compute instance list-vnics --instance-id "$JA" --query 'data[0]."public-ip"' --raw-output)
    fala "Voce ja tem um servidor: http://$IP:8080/manager"
    [ -f ~/evolution-chave.txt ] && fala "Chave: $(cat ~/evolution-chave.txt)"
    exit 0
fi

fala "Montando a rede..."
VCN=$(oci network vcn list -c "$C" --display-name evolution-vcn --query 'data[0].id' --raw-output 2>/dev/null)
if vazio "$VCN"; then
    VCN=$(oci network vcn create -c "$C" --cidr-blocks '["10.0.0.0/16"]' --display-name evolution-vcn --dns-label evovcn --wait-for-state AVAILABLE --query data.id --raw-output)
fi
IGW=$(oci network internet-gateway list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null)
if vazio "$IGW"; then
    IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true --display-name evolution-igw --wait-for-state AVAILABLE --query data.id --raw-output)
fi
RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
oci network security-list update --security-list-id "$SL" --force \
    --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' \
    --ingress-security-rules '[{"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},{"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":8080,"max":8080}}}]' >/dev/null
SUB=$(oci network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null)
if vazio "$SUB"; then
    SUB=$(oci network subnet create -c "$C" --vcn-id "$VCN" --cidr-block 10.0.0.0/24 --display-name evolution-subnet --dns-label evosub --wait-for-state AVAILABLE --query data.id --raw-output)
fi

CHAVE=$(openssl rand -hex 24)
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
    image: evoapicloud/evolution-api:latest
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

fala "Criando o servidor. A Oracle pode demorar alguns minutos..."
IMG=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" --shape VM.Standard.E2.1.Micro --sort-by TIMECREATED --sort-order DESC --query 'data[0].id' --raw-output)
ID=""
for AD in $(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]",'); do
    ID=$(oci compute instance launch -c "$C" --availability-domain "$AD" --shape VM.Standard.E2.1.Micro --image-id "$IMG" --subnet-id "$SUB" \
        --assign-public-ip true --display-name evolution-api --ssh-authorized-keys-file ~/.ssh/sheep_evolution.pub --user-data-file "$INICIO" \
        --wait-for-state RUNNING --query data.id --raw-output 2>~/evolution-erro.txt)
    vazio "$ID" || break
done
rm -f "$INICIO"
if vazio "$ID"; then
    fala "A Oracle recusou agora. Motivo:"
    grep -o '"message": "[^"]*"' ~/evolution-erro.txt | head -1
    fala "Mostra isso para a sua agente. Se for falta de capacidade, tente de novo mais tarde."
    exit 1
fi
IP=$(oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output)

fala "Servidor criado em $IP. Instalando a Evolution, leva uns 5 minutos..."
for _ in $(seq 1 60); do
    curl -fsS --max-time 5 "http://$IP:8080" >/dev/null 2>&1 && break
    sleep 10
done

fala "Pronto."
echo "  Painel: http://$IP:8080/manager"
echo "  Chave:  $CHAVE"
echo
echo "  Guarde a chave. No painel, crie uma instancia e leia o QR com o WhatsApp."
echo "  Nunca cole a chave no chat: cadastre em Conexoes, no painel da Sheep."
