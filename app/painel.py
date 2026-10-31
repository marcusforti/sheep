"""Painel da Sheep: mesma tela e mesmo núcleo do app, numa janela do navegador do próprio computador.
Só usa a biblioteca padrão do Python. Fechar a janela encerra o painel."""
import json, os, shutil, subprocess, sys, threading, time, webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nucleo import agentes, aprovacoes, caminhos, cofre, instalador, rotinas, servidor, sessoes_vivas, telegram, trava, whatsapp, zap


def navegador():
    locais = [os.environ.get(v, "") for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    caminhos_possiveis = [Path(base) / resto for base in locais if base for resto in
                          (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe")]
    return next((str(p) for p in caminhos_possiveis if p.exists()), None) or shutil.which("chrome") or shutil.which("msedge")


def abrir(endereco):
    """Abre em janela própria quando dá, e devolve o processo para saber quando ela fecha."""
    programa = navegador()
    if programa:
        perfil = caminhos.sub(".painel-navegador")
        # O Edge entra sozinho na conta do Windows e cobre a tela com um aviso: estes flags evitam isso.
        return subprocess.Popen([programa, f"--app={endereco}/", f"--user-data-dir={perfil}", "--window-size=1320,860",
                                 "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required",
                                 "--disable-sync", "--disable-features=msImplicitSignin,msEdgeSyncConsent,EdgeWelcomeSync"])
    webbrowser.open(endereco + "/")
    return None


def registrar_erro(texto):
    try:
        with (caminhos.sub("logs") / "servidor.log").open("a", encoding="utf-8") as log:
            log.write(texto + "\n")
    except OSError:
        pass


def motor_escolhido():
    """O instalador deixa em .motor a IA paga que a pessoa usa."""
    escolha = caminhos.casa() / ".motor"
    if escolha.exists() and not cofre.ler("MOTOR_PADRAO"):
        cofre.guardar("MOTOR_PADRAO", escolha.read_text(encoding="utf-8", errors="ignore").strip())


def monitorar_telegram(parar):
    bot = telegram.Bot()
    thread = None
    while not parar.is_set():
        if cofre.tem("TELEGRAM_TOKEN") and cofre.tem("TELEGRAM_DONO"):
            if thread is None or not thread.is_alive():
                thread = threading.Thread(target=bot.rodar_para_sempre, args=(parar,), daemon=True)
                thread.start()
            try:
                aprovacoes.avisar_novas("telegram", bot.avisar_aprovacao)
            except (OSError, ValueError):
                pass
        if parar.wait(10):
            break


def relogio(parar):
    bot = telegram.Bot()
    while not parar.wait(60):
        ligado = cofre.tem("TELEGRAM_TOKEN") and cofre.tem("TELEGRAM_DONO")
        rotinas.rodar_devidas(datetime.now(), avisar=(lambda t: bot._envia(cofre.ler("TELEGRAM_DONO"), t)) if ligado else None)


def main():
    instancia = caminhos.casa() / ".sheep.instancia"
    bloqueio = trava.obter_trava(caminhos.casa() / ".sheep.lock")
    if bloqueio is None:
        try:
            abrir(f"http://127.0.0.1:{json.loads(instancia.read_text(encoding='utf-8'))['porta']}")
        except (OSError, ValueError, KeyError):
            pass
        return
    instalador.completar_path()
    motor_escolhido()
    try:
        agentes.atualizar_bloco_app(caminhos.casa())
    except OSError as erro:
        registrar_erro(f"Não consegui atualizar as instruções do aplicativo: {erro}")
    srv, base, token = servidor.iniciar()
    instancia.write_text(json.dumps({"porta": srv.server_port, "token": token}), encoding="utf-8")
    parar = threading.Event()
    threading.Thread(target=monitorar_telegram, args=(parar,), daemon=True).start()
    threading.Thread(target=relogio, args=(parar,), daemon=True).start()
    ponte = whatsapp.ponte()
    bot_zap = zap.Bot(ponte=ponte)
    threading.Thread(target=bot_zap.rodar_para_sempre, args=(parar,), daemon=True).start()
    if cofre.ler("WHATSAPP_LIGADO") == "1":
        threading.Thread(target=ponte.conectar, daemon=True).start()
    janela = abrir(base)
    print(base, flush=True)
    try:
        inicio = time.time()
        if janela is not None:
            janela.wait()
        # Sem janela própria, ou se o navegador devolveu na hora, o painel fica de pé.
        if janela is None or time.time() - inicio < 5:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        bot_zap.parar(); ponte.parar()
        sessoes_vivas.fechar()
        parar.set(); srv.shutdown(); srv.server_close(); instancia.unlink(missing_ok=True); bloqueio.close()


if __name__ == "__main__":
    main()
