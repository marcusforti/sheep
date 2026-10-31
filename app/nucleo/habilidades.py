import json
from nucleo import caminhos

def _estado():
    p = caminhos.sub("habilidades") / "estado.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def listar():
    est = _estado(); out = []
    for d in sorted(caminhos.sub("habilidades").iterdir()):
        j = d / "habilidade.json"
        if d.is_dir() and j.exists():
            info = json.loads(j.read_text(encoding="utf-8"))
            out.append({"id": d.name, "nome": info.get("nome", d.name), "descricao": info.get("descricao", ""),
                        "exemplo": info.get("exemplo", ""), "ligada": est.get(d.name, True), "pasta": str(d)})
    return out

def ligar(id, ligada):
    est = _estado(); est[id] = bool(ligada)
    (caminhos.sub("habilidades") / "estado.json").write_text(json.dumps(est), encoding="utf-8")
