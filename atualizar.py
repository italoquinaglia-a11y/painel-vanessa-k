#!/usr/bin/env python3
"""Monta data.json do painel a partir das respostas brutas do conector Meta Ads.

Uso (na pasta do repositório):
  python3 atualizar.py dados        # usa raw/dias.json, raw/mes.json, raw/ads7.json, raw/criativos.json
  python3 atualizar.py saldo 123.45 # só atualiza o saldo (lido na tela de cobrança)

Cada arquivo em raw/ é a resposta da ferramenta salva como veio (JSON).
O saldo e a verba da semana já gravados em data.json são preservados no modo "dados".
"""
import json, sys, os, datetime as dt

TZ = dt.timezone(dt.timedelta(hours=-3))
CONV = "actions:onsite_conversion.messaging_conversation_started_7d"


def agora():
    return dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def ler(p):
    j = json.load(open(p, encoding="utf-8"))
    for k in ("ad_entities", "ad_creatives"):
        if k in j:
            v = j[k]
            return json.loads(v) if isinstance(v, str) else v
    return j


def num(v):
    if isinstance(v, dict):
        v = v.get("value")
        if isinstance(v, list):
            v = v[0].get("value") if v else 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def conv(row):
    if CONV in row:
        return int(num(row[CONV]))
    r = row.get("results")
    if r and "messaging_conversation" in str(r.get("indicator", "")):
        vals = r.get("values")
        return int(num(vals[0])) if vals else 0
    return 0


def titulo(c, reserva="Anúncio"):
    import re
    body = (c.get("body") or "").strip()
    linha = next((l.strip() for l in body.splitlines() if l.strip()), "")
    if not linha or re.match(r"^\d{4}-\d{2}-\d{2}-[0-9a-f]+$", linha):
        linha = reserva
    linha = linha.strip("🎾🚨⚠️💬📲✨ ").strip()
    return linha[:70] + ("…" if len(linha) > 70 else "")


def dados():
    base = json.load(open("data.json", encoding="utf-8")) if os.path.exists("data.json") else {}
    dias_raw = ler("raw/dias.json")
    dias = sorted(({"data": r["date_start"], "gasto": round(num(r["amount_spent"]), 2), "conversas": conv(r)} for r in dias_raw), key=lambda x: x["data"])
    hoje_iso = dt.datetime.now(TZ).date().isoformat()
    hoje = next((d for d in dias if d["data"] == hoje_iso), {"data": hoje_iso, "gasto": 0, "conversas": 0})
    completos = [d for d in dias if d["data"] < hoje_iso][-14:]
    mes = ler("raw/mes.json")[0]
    ads = ler("raw/ads7.json")
    crs = {c["id"]: c for c in ler("raw/criativos.json")}
    agg = {}
    for a in ads:
        cid = a.get("creative_id")
        if not cid:
            continue
        g = agg.setdefault(cid, {"gasto": 0.0, "conversas": 0, "nome": (a.get("name") or "Anúncio").replace(" — Cópia", "")})
        g["gasto"] += num(a.get("amount_spent"))
        g["conversas"] += conv(a)
    criativos = []
    for cid, g in agg.items():
        c = crs.get(cid, {})
        criativos.append({
            "id": cid,
            "titulo": titulo(c, g["nome"]) if c else g["nome"],
            "tipo": "vídeo" if c.get("video_id") or c.get("object_type") == "VIDEO" else "imagem",
            "gasto": round(g["gasto"], 2),
            "conversas": g["conversas"],
            "miniatura": c.get("image_url") or c.get("thumbnail_url") or "",
        })
    criativos.sort(key=lambda x: (-x["conversas"], -x["gasto"]))
    criativos = [c for c in criativos if c["gasto"] >= 5 or c["conversas"] > 0][:10]
    out = {
        "cliente": base.get("cliente", "Vanessa Kreitchmann"),
        "atualizado_em": agora(),
        "saldo": base.get("saldo", {"valor": None, "lido_em": None}),
        "verba_semana": base.get("verba_semana"),
        "hoje": hoje,
        "ontem": completos[-1] if completos else hoje,
        "anteontem": completos[-2] if len(completos) > 1 else None,
        "mes": {"gasto": round(num(mes["amount_spent"]), 2), "conversas": conv(mes)},
        "dias": completos,
        "criativos_periodo": "últimos 7 dias",
        "criativos": criativos,
    }
    json.dump(out, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ok: ontem R$ {out['ontem']['gasto']:.2f}, {len(criativos)} criativos, mês R$ {out['mes']['gasto']:.2f}")


def saldo(valor):
    d = json.load(open("data.json", encoding="utf-8"))
    d["saldo"] = {"valor": round(float(str(valor).replace(".", "").replace(",", ".")) if "," in str(valor) else float(valor), 2), "lido_em": agora()}
    json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok: saldo", d["saldo"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["dados"]:
        dados()
    elif sys.argv[1:2] == ["saldo"] and len(sys.argv) > 2:
        saldo(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
