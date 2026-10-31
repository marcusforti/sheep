import io, json, os, re, shutil, stat, threading, unicodedata, uuid, zipfile, zlib
from datetime import datetime
from pathlib import Path, PureWindowsPath
from nucleo import agentes, caminhos, instalador

EMBUTIDOS = instalador.MODELO / "pacotes"
MAX_ARQUIVOS = 500
MAX_BYTES = 30 * 1024 * 1024
PROIBIDOS = {".exe", ".dll", ".msi", ".scr", ".com", ".pif", ".bat", ".cmd", ".vbs", ".ps1", ".lnk"}
TRAVA = threading.RLock()


class _FalhaRestauracao(ValueError):
    pass


def _id(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[a-z0-9-]{2,40}", valor):
        raise ValueError("O identificador do pacote deve ter de 2 a 40 letras minúsculas, números ou hífens.")
    _normalizar(valor)
    return valor


def _chave(valor):
    return unicodedata.normalize("NFC", valor).casefold()


def _normalizar(nome):
    if not isinstance(nome, str) or not nome or nome.startswith(("/", "\\")):
        raise ValueError("O pacote contém um caminho absoluto ou inválido.")
    partes = nome.replace("\\", "/").rstrip("/").split("/")
    for parte in partes:
        if not parte or parte in (".", "..") or parte.endswith((".", " ")):
            raise ValueError("O pacote contém um caminho inseguro.")
        if any(ord(c) < 32 or c in '<>:"|?*' for c in parte):
            raise ValueError("O pacote contém um nome de arquivo inválido no Windows.")
        if PureWindowsPath(parte).is_reserved():
            raise ValueError("O pacote contém um nome reservado do Windows.")
    return "/".join(partes)


def _sem_links(arquivo, raiz=None):
    arquivo = Path(arquivo).absolute()
    casa = caminhos.casa().absolute()
    raiz = casa if arquivo.is_relative_to(casa) else Path(raiz).absolute() if raiz is not None else arquivo
    partes = [arquivo]
    while partes[-1] != raiz:
        partes.append(partes[-1].parent)
    for parte in reversed(partes):
        try:
            info = parte.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
            raise ValueError("Links, atalhos e junções de pastas não são permitidos nos pacotes.")
        if parte != arquivo and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Uma pasta de destino já existe como arquivo.")


def _erro_percurso(erro):
    raise erro


def _arvore(pasta):
    _sem_links(pasta)
    entradas = []
    for raiz, pastas, arquivos in os.walk(pasta, followlinks=False, onerror=_erro_percurso):
        for nome in pastas + arquivos:
            arquivo = Path(raiz) / nome
            _sem_links(arquivo, pasta)
            info = arquivo.lstat()
            if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
                raise ValueError("O pacote contém um arquivo especial não permitido.")
            entradas.append((arquivo.relative_to(pasta).as_posix(), stat.S_ISDIR(info.st_mode), info.st_size, arquivo))
    return entradas


def _validar_entradas(entradas):
    vistos, explicitos = {}, set()
    quantidade, tamanho = 0, 0
    normalizadas = []
    for nome, diretorio, tamanho_item, origem in entradas:
        if _ignorar(nome):
            continue
        relativo = _normalizar(nome)
        partes = relativo.split("/")
        chave = _chave(relativo)
        if chave in explicitos:
            raise ValueError("O pacote contém um arquivo repetido ou uma colisão de nomes.")
        explicitos.add(chave)
        for indice in range(1, len(partes) + 1):
            caminho = "/".join(partes[:indice])
            chave_parte = _chave(caminho)
            eh_pasta = indice < len(partes) or diretorio
            if chave_parte in vistos and vistos[chave_parte] != (caminho, eh_pasta):
                raise ValueError("O pacote contém uma colisão entre arquivos ou pastas.")
            vistos[chave_parte] = (caminho, eh_pasta)
        if not diretorio:
            quantidade += 1
            tamanho += tamanho_item
        if quantidade > MAX_ARQUIVOS:
            raise ValueError("O pacote pode ter no máximo 500 arquivos.")
        if tamanho > MAX_BYTES:
            raise ValueError("O pacote pode ter no máximo 30 MB descompactados.")
        normalizadas.append((relativo, diretorio, tamanho_item, origem))
    arquivos = {nome for nome, diretorio, _, _ in normalizadas if not diretorio}
    raiz = ""
    if "pacote.json" not in arquivos:
        primeiros = {nome.split("/")[0] for nome, _, _, _ in normalizadas}
        if len(primeiros) != 1:
            raise ValueError("O pacote precisa de pacote.json na raiz ou dentro de uma única pasta.")
        raiz = next(iter(primeiros)) + "/"
        if raiz + "pacote.json" not in arquivos:
            raise ValueError("Não encontrei pacote.json na raiz do pacote.")
    for nome, diretorio, _, _ in normalizadas:
        relativo = nome.removeprefix(raiz)
        extensao = Path(relativo).suffix.lower()
        if not diretorio and extensao in PROIBIDOS:
            raise ValueError("O pacote contém um executável ou atalho não permitido.")
        if not diretorio and extensao in {".py", ".js"} and relativo.split("/")[0].lower() != "habilidades":
            raise ValueError("O pacote contém um script ou executável fora da pasta de habilidades, o que não é permitido.")
    return normalizadas, raiz


def _ignorar(nome):
    partes = nome.replace("\\", "/").rstrip("/").split("/")
    return "__macosx" in [p.casefold() for p in partes] or partes[-1].casefold() in {".ds_store", "thumbs.db", "desktop.ini"}


def _extrair(origem, destino):
    if isinstance(origem, (str, Path)):
        if isinstance(origem, str) and re.fullmatch(r"[a-z0-9-]{2,40}", origem):
            origem = EMBUTIDOS / origem
        else:
            origem = Path(origem)
        _sem_links(origem)
        if origem.is_dir():
            entradas, raiz = _validar_entradas(_arvore(origem))
            total = 0
            for nome, diretorio, _, arquivo in entradas:
                alvo = destino / nome
                if diretorio:
                    alvo.mkdir(parents=True, exist_ok=True)
                else:
                    with arquivo.open("rb") as entrada:
                        dados = entrada.read(MAX_BYTES + 1)
                    total += len(dados)
                    if total > MAX_BYTES:
                        raise ValueError("O pacote pode ter no máximo 30 MB descompactados.")
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    alvo.write_bytes(dados)
            return destino / raiz
        if not origem.is_file() or origem.suffix.lower() != ".zip":
            raise ValueError("Escolha um pacote embutido, uma pasta ou um arquivo ZIP existente.")
    elif isinstance(origem, bytes):
        origem = io.BytesIO(origem)
    else:
        raise ValueError("A origem do pacote deve ser uma pasta ou um arquivo ZIP.")
    with zipfile.ZipFile(origem) as arquivo_zip:
        entradas = []
        for info in arquivo_zip.infolist():
            if _ignorar(info.orig_filename):
                continue
            tipo = stat.S_IFMT(info.external_attr >> 16)
            if tipo not in (0, stat.S_IFREG, stat.S_IFDIR) or info.external_attr & 1024:
                raise ValueError("O ZIP contém um link, atalho ou arquivo especial não permitido.")
            if info.flag_bits & 1:
                raise ValueError("ZIP protegido por senha não é permitido.")
            entradas.append((info.orig_filename, info.is_dir(), info.file_size, info))
        entradas, raiz = _validar_entradas(entradas)
        total = 0
        for nome, diretorio, _, info in entradas:
            alvo = destino / nome
            if diretorio:
                alvo.mkdir(parents=True, exist_ok=True)
            else:
                with arquivo_zip.open(info) as entrada:
                    dados = entrada.read(MAX_BYTES + 1)
                total += len(dados)
                if total > MAX_BYTES:
                    raise ValueError("O pacote pode ter no máximo 30 MB descompactados.")
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(dados)
    return destino / raiz


def _json(arquivo, padrao=None):
    if not arquivo.exists() and padrao is not None:
        return padrao
    _sem_links(arquivo)
    try:
        return json.loads(arquivo.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as erro:
        raise ValueError(f"O arquivo {arquivo.name} não contém um JSON válido.") from erro


def _nomes(valores):
    if not isinstance(valores, list) or not all(isinstance(v, str) and v.strip() for v in valores):
        raise ValueError("A lista do pacote contém nomes inválidos.")
    if len({_chave(v) for v in valores}) != len(valores):
        raise ValueError("O pacote contém nomes repetidos.")
    return valores


def _rotinas(arquivo):
    rotinas = _json(arquivo, [])
    if not isinstance(rotinas, list):
        raise ValueError("rotinas.json deve conter uma lista.")
    for rotina in rotinas:
        if not isinstance(rotina, dict) or not isinstance(rotina.get("nome"), str) or not rotina["nome"].strip():
            raise ValueError("Uma rotina do pacote não tem um nome válido.")
        if not isinstance(rotina.get("hora"), str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", rotina["hora"]):
            raise ValueError("Uma rotina do pacote não tem um horário válido (HH:MM).")
        if not isinstance(rotina.get("prompt"), str) or not rotina["prompt"].strip():
            raise ValueError("Uma rotina do pacote não tem instruções válidas.")
        if "ativo" in rotina and not isinstance(rotina["ativo"], bool):
            raise ValueError("O campo ativo da rotina deve ser verdadeiro ou falso.")
    _nomes([r["nome"] for r in rotinas])
    return rotinas


def _rotinas_dono(arquivo):
    try:
        rotinas = _json(arquivo, [])
        if not isinstance(rotinas, list) or not all(isinstance(r, dict) for r in rotinas):
            raise ValueError("Formato inválido")
        return rotinas
    except (ValueError, OSError) as erro:
        raise ValueError("Seu rotinas.json está com problema. Abra a pasta da Sheep e confira esse arquivo.") from erro


def _dados(pasta):
    meta = _json(pasta / "pacote.json")
    if not isinstance(meta, dict):
        raise ValueError("pacote.json deve conter os dados do pacote.")
    _id(meta.get("id"))
    meta = {"descricao": "", "versao": "0.0.0", "autor": "", "traz": [], **meta}
    for campo in ("nome", "descricao", "versao", "autor"):
        if not isinstance(meta.get(campo), str) or campo in ("nome", "versao") and not meta[campo].strip():
            raise ValueError(f"O campo {campo} do pacote é obrigatório e deve ser um texto válido.")
    _nomes(meta.get("traz"))
    habilidades = []
    pasta_habilidades = pasta / "habilidades"
    if pasta_habilidades.exists():
        for habilidade in sorted(pasta_habilidades.iterdir()):
            if not habilidade.is_dir():
                raise ValueError("Cada habilidade deve estar em sua própria pasta.")
            _normalizar(habilidade.name)
            if habilidade.name.casefold() == "estado.json":
                raise ValueError("O nome estado.json é reservado ao estado das habilidades.")
            info = _json(habilidade / "habilidade.json")
            if not isinstance(info, dict) or not isinstance(info.get("nome"), str) or not info["nome"].strip():
                raise ValueError("habilidade.json deve conter um nome válido.")
            if not (habilidade / "LEIA-ME.md").is_file():
                raise ValueError("Cada habilidade precisa de LEIA-ME.md.")
            (habilidade / "LEIA-ME.md").read_text(encoding="utf-8-sig")
            habilidades.append(habilidade.name)
    instrucoes = None
    if (pasta / "AGENTS.md").exists():
        instrucoes = (pasta / "AGENTS.md").read_bytes()
        if "<!-- sheep:" in instrucoes.decode("utf-8-sig").lower():
            raise ValueError("As instruções do pacote não podem alterar os marcadores da Sheep.")
    return meta, habilidades, _rotinas(pasta / "rotinas.json"), instrucoes


def _estado(casa):
    estado = _json(casa / "pacotes" / "estado.json", {})
    if not isinstance(estado, dict):
        raise ValueError("O registro de pacotes da casa está inválido.")
    donos_habilidades, donos_rotinas = {}, {}
    for id, registro in estado.items():
        _id(id)
        if not isinstance(registro, dict):
            raise ValueError("O registro de pacotes da casa está inválido.")
        for habilidade in _nomes(registro.get("habilidades")):
            if "/" in _normalizar(habilidade) or habilidade.casefold() == "estado.json":
                raise ValueError("O registro de habilidades contém um caminho inválido.")
            if _chave(habilidade) in donos_habilidades:
                raise ValueError("O registro contém propriedade duplicada de uma habilidade.")
            donos_habilidades[_chave(habilidade)] = id
        for rotina in _nomes(registro.get("rotinas")):
            if _chave(rotina) in donos_rotinas:
                raise ValueError("O registro contém propriedade duplicada de uma rotina.")
            donos_rotinas[_chave(rotina)] = id
        if not isinstance(registro.get("versao"), str):
            raise ValueError("O registro do pacote não informa uma versão válida.")
    return estado


def _item(meta, habilidades, rotinas, estado, origem):
    instalado = estado.get(meta["id"])
    return {**{k: meta[k] for k in ("id", "nome", "descricao", "versao", "autor", "traz")},
            "origem": origem, "instalado": instalado is not None,
            "versao_instalada": instalado["versao"] if instalado else None,
            "habilidades": habilidades, "rotinas": [r["nome"] for r in rotinas]}


def listar():
    with TRAVA:
        try:
            casa = caminhos.casa()
            _sem_links(casa)
            estado, itens = _estado(casa), {}
            if EMBUTIDOS.exists():
                for pasta in sorted(EMBUTIDOS.iterdir()):
                    if pasta.is_dir():
                        itens[pasta.name] = _ler_item(pasta, pasta.name, estado, "embutido")
            for id, registro in estado.items():
                instalado = _ler_item(casa / "pacotes" / id, id, estado, "instalado")
                if id not in itens or instalado.get("erro"):
                    itens[id] = instalado
            return sorted(itens.values(), key=lambda item: item["nome"].casefold())
        except (OSError, UnicodeError) as erro:
            raise ValueError("Não consegui ler os pacotes. Confira os arquivos e tente novamente.") from erro


def _ler_item(pasta, id, estado, origem):
    try:
        _validar_entradas(_arvore(pasta))
        meta, habilidades, rotinas, _ = _dados(pasta)
        if meta["id"] != id:
            raise ValueError("A pasta do pacote não corresponde ao seu identificador.")
        return _item(meta, habilidades, rotinas, estado, origem)
    except Exception as erro:
        mensagem = str(erro) if isinstance(erro, ValueError) else "Não consegui ler este pacote. Remova e instale novamente."
        return {"id": id, "nome": id, "erro": mensagem}


def previa(origem):
    with TRAVA:
        casa, temporario, nova_casa = caminhos.casa(), None, False
        try:
            _sem_links(casa)
            nova_casa = not casa.exists()
            casa.mkdir(parents=True, exist_ok=True)
            temporario = _temporario(casa)
            extraido = _extrair(origem, temporario / "origem")
            meta, habilidades, rotinas, _ = _dados(extraido)
            return {"nome": meta["nome"], "descricao": meta["descricao"], "traz": meta["traz"],
                    "habilidades": habilidades, "rotinas": [r["nome"] for r in rotinas],
                    "scripts": sorted(p.relative_to(extraido).as_posix() for p in extraido.rglob("*") if p.is_file() and p.suffix.lower() in {".py", ".js"})}
        except (OSError, UnicodeError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError) as erro:
            raise ValueError("Não consegui ler o pacote. Confira a pasta ou o ZIP e tente novamente.") from erro
        finally:
            if temporario is not None:
                _limpar_temporario(temporario)
            if nova_casa and casa.exists() and not any(casa.iterdir()):
                casa.rmdir()


def _destino(casa, relativo):
    destino = casa / _normalizar(relativo)
    _sem_links(destino)
    if destino.is_dir():
        _arvore(destino)
    return destino


def _gravar_temporario(temporario, nome, dados):
    arquivo = temporario / nome
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(dados)
    return arquivo


def _serializar(dados):
    return (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _temporario(casa):
    pasta = casa / (".pacote-" + uuid.uuid4().hex)
    pasta.mkdir()
    return pasta


def _limpar_temporario(temporario):
    try:
        shutil.rmtree(temporario)
    except OSError:
        aviso = f"Não consegui limpar os temporários em {temporario}. Os arquivos remanescentes foram preservados."
        try:
            logs = temporario.parent / "logs"
            logs.mkdir(exist_ok=True)
            with (logs / "servidor.log").open("a", encoding="utf-8") as arquivo:
                arquivo.write(aviso + "\n")
        except OSError:
            pass
        return aviso


def _aplicar(plano, temporario):
    prontos = temporario / "prontos"
    backups = temporario / "backups"
    prontos.mkdir()
    backups.mkdir()
    for indice, (destino, origem) in enumerate(plano):
        _sem_links(destino)
        if origem is not None:
            if origem.is_dir():
                shutil.copytree(origem, prontos / str(indice))
            else:
                shutil.copy2(origem, prontos / str(indice))
    alterados, criadas = [], []
    try:
        for indice, (destino, origem) in enumerate(plano):
            _sem_links(destino)
            faltantes = []
            pasta = destino.parent
            while not pasta.exists():
                faltantes.append(pasta)
                pasta = pasta.parent
            for pasta in reversed(faltantes):
                pasta.mkdir()
                criadas.append(pasta)
            backup = backups / str(indice)
            existia = destino.exists()
            alterados.append((destino, backup, existia))
            if existia:
                os.replace(destino, backup)
            if origem is not None:
                os.replace(prontos / str(indice), destino)
    except BaseException as erro:
        falhas = []
        for destino, backup, existia in reversed(alterados):
            try:
                if existia and not backup.exists():
                    continue
                if destino.is_dir():
                    shutil.rmtree(destino)
                elif destino.exists():
                    destino.unlink()
                if existia:
                    os.replace(backup, destino)
            except BaseException as falha:
                falhas.append(falha)
        for pasta in reversed(criadas):
            try:
                pasta.rmdir()
            except OSError:
                pass
            except BaseException as falha:
                falhas.append(falha)
        if falhas:
            raise _FalhaRestauracao(f"Não consegui restaurar todos os arquivos. A cópia de recuperação está em {backups}.") from erro
        if isinstance(erro, (OSError, ValueError)):
            raise ValueError("Não consegui gravar o pacote. A casa foi restaurada; tente novamente.") from erro
        raise


def _mesclar_rotinas(atuais, novas, id, registro):
    antigas = set(registro.get("rotinas", []))
    desejadas = {_chave(r["nome"]): r for r in novas}
    for rotina in atuais:
        if isinstance(rotina.get("nome"), str) and _chave(rotina["nome"]) in desejadas and not (rotina["nome"] in antigas and rotina.get("pacote") == id):
            raise ValueError(f"A rotina {rotina['nome']} já existe e não pertence a este pacote.")
    preservadas = [r for r in atuais if not (isinstance(r.get("nome"), str) and r["nome"] in antigas and r.get("pacote") == id)]
    return preservadas + [{**r, "ativo": False, "pacote": id} for r in novas]


def instalar(origem):
    with TRAVA:
        casa, temporario, limpar, nova_casa = caminhos.casa(), None, True, False
        resultado, falha = None, None
        try:
            _sem_links(casa)
            nova_casa = not casa.exists()
            casa.mkdir(parents=True, exist_ok=True)
            temporario = _temporario(casa)
            extraido = _extrair(origem, temporario / "origem")
            meta, habilidades, novas_rotinas, instrucoes = _dados(extraido)
            id, estado, plano = meta["id"], _estado(casa), []
            registro = estado.get(id, {})
            antigas = registro.get("habilidades", [])
            for habilidade in habilidades:
                destino = _destino(casa, f"habilidades/{habilidade}")
                outros = [outro for outro, reg in estado.items() if outro != id and _chave(habilidade) in {_chave(h) for h in reg["habilidades"]}]
                if outros or destino.exists() and habilidade not in antigas:
                    raise ValueError(f"A habilidade {habilidade} já existe ou pertence a outro pacote.")
                plano.append((destino, extraido / "habilidades" / habilidade))
            for habilidade in antigas:
                if habilidade not in habilidades:
                    plano.append((_destino(casa, f"habilidades/{habilidade}"), None))
            contexto = extraido / "casa"
            if contexto.exists():
                for arquivo in sorted(contexto.rglob("*")):
                    if arquivo.is_file() and arquivo.name.lower() != "dono.md":
                        destino = _destino(casa, "casa/" + arquivo.relative_to(contexto).as_posix())
                        if not destino.exists():
                            plano.append((destino, arquivo))
            arquivo_agents = _destino(casa, "AGENTS.md")
            antes = arquivo_agents.read_bytes() if arquivo_agents.exists() else b""
            depois = agentes.conteudo_pacote(antes, id, instrucoes)
            if antes != depois:
                plano.append((arquivo_agents, _gravar_temporario(temporario, "AGENTS.md", depois)))
            arquivo_rotinas = _destino(casa, "rotinas.json")
            atuais = _rotinas_dono(arquivo_rotinas)
            nomes_rotinas = {_chave(r["nome"]) for r in novas_rotinas}
            if any(nomes_rotinas & {_chave(nome) for nome in reg["rotinas"]} for outro, reg in estado.items() if outro != id):
                raise ValueError("Uma rotina já pertence a outro pacote no registro de propriedade.")
            mescladas = _mesclar_rotinas(atuais, novas_rotinas, id, registro)
            if mescladas != atuais:
                plano.append((arquivo_rotinas, _gravar_temporario(temporario, "rotinas.json", _serializar(mescladas))))
            copia = _destino(casa, f"pacotes/{id}")
            if copia.exists() and id not in estado:
                raise ValueError("A pasta de cópia do pacote já existe e não tem propriedade registrada.")
            plano.append((copia, extraido))
            estado[id] = {"versao": meta["versao"], "habilidades": habilidades,
                          "rotinas": [r["nome"] for r in novas_rotinas], "instalado_em": datetime.now().isoformat(timespec="seconds")}
            plano.append((_destino(casa, "pacotes/estado.json"), _gravar_temporario(temporario, "estado.json", _serializar(estado))))
            _aplicar(plano, temporario)
            resultado = _item(meta, habilidades, novas_rotinas, estado, "embutido" if (EMBUTIDOS / id).is_dir() else "instalado")
            return resultado
        except _FalhaRestauracao:
            limpar = False
            raise
        except (OSError, UnicodeError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError) as erro:
            falha = ValueError("Não consegui instalar o pacote. Confira a pasta ou o ZIP e tente novamente.")
            raise falha from erro
        except ValueError as erro:
            falha = erro
            raise
        finally:
            if limpar and temporario is not None:
                aviso = _limpar_temporario(temporario)
                if aviso and resultado is not None:
                    resultado["aviso"] = aviso
                elif aviso and falha is not None:
                    falha.args = (str(falha) + " " + aviso,)
            if nova_casa and casa.exists() and not any(casa.iterdir()):
                casa.rmdir()


def remover(id):
    with TRAVA:
        temporario, limpar, falha = None, True, None
        try:
            _id(id)
            casa = caminhos.casa()
            _sem_links(casa)
            estado = _estado(casa)
            if id not in estado:
                raise ValueError("Este pacote não está instalado.")
            registro = estado[id]
            temporario = _temporario(casa)
            plano = [(_destino(casa, f"habilidades/{h}"), None) for h in registro["habilidades"]]
            arquivo_agents = _destino(casa, "AGENTS.md")
            if arquivo_agents.exists():
                antes = arquivo_agents.read_bytes()
                depois = agentes.conteudo_pacote(antes, id, None)
                if depois != antes:
                    plano.append((arquivo_agents, _gravar_temporario(temporario, "AGENTS.md", depois)))
            arquivo_rotinas = _destino(casa, "rotinas.json")
            atuais = _rotinas_dono(arquivo_rotinas)
            mescladas = _mesclar_rotinas(atuais, [], id, registro)
            if mescladas != atuais:
                plano.append((arquivo_rotinas, _gravar_temporario(temporario, "rotinas.json", _serializar(mescladas))))
            plano.append((_destino(casa, f"pacotes/{id}"), None))
            del estado[id]
            plano.append((_destino(casa, "pacotes/estado.json"), _gravar_temporario(temporario, "estado.json", _serializar(estado))))
            _aplicar(plano, temporario)
            return True
        except _FalhaRestauracao:
            limpar = False
            raise
        except (OSError, UnicodeError) as erro:
            falha = ValueError("Não consegui remover o pacote. Confira os arquivos e tente novamente.")
            raise falha from erro
        except ValueError as erro:
            falha = erro
            raise
        finally:
            if limpar and temporario is not None:
                aviso = _limpar_temporario(temporario)
                if aviso and falha is not None:
                    falha.args = (str(falha) + " " + aviso,)
