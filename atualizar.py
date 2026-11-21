#!/usr/bin/env python3
"""Monta data.json do painel a partir das respostas brutas do conector Meta Ads.

Uso (na pasta do repositório):
  python3 atualizar.py dados        # usa raw/dias.json, raw/mes.json, raw/ads7.json, raw/criativos.json
  python3 atualizar.py vendas       # só atualiza o ranking de vendas por criativo (raw/vendas.json)
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
    vendas_criativos, vendas_periodo = base.get("vendas_criativos", []), base.get("vendas_periodo")
    if not USAR_VENDAS_META or os.path.exists("raw/vendas.json"):
        vendas_criativos, vendas_periodo = vendas(crs)
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
        "vendas_periodo": vendas_periodo,
        "vendas_criativos": vendas_criativos,
        "ia": base.get("ia"),
        "estrutura": base.get("estrutura"),
    }
    json.dump(out, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ok: ontem R$ {out['ontem']['gasto']:.2f}, {len(criativos)} criativos, mês R$ {out['mes']['gasto']:.2f}")


def nome_limpo(n):
    import re
    n = (n or "Anúncio").replace(" — Cópia", "")
    return re.sub(r"^(RMKT|ADV|LAL)\s+—\s+", "", n).strip()


USAR_VENDAS_META = False


def vendas(crs=None):
    """Vendas (Compra) que a Meta ligou a cada anúncio, somadas por criativo.
    raw/vendas.json: anúncios do mês com name, creative_id, amount_spent, omni_purchase."""
    # Desligado em 21/11/2026: o "omni_purchase" da Meta soma compras de pixels de lojas
    # parceiras ligados à conta (ex.: 1389448392342708, 1524540272377373, 1047353003237528),
    # que não são vendas da Vanessa. O ranking volta quando vier das vendas do Google Forms.
    if not USAR_VENDAS_META:
        return [], None
    crs = crs or {}
    j = json.load(open("raw/vendas.json", encoding="utf-8"))
    periodo = j.get("periodo", "este mês") if isinstance(j, dict) else "este mês"
    agg = {}
    for a in ler("raw/vendas.json"):
        v = int(num(a.get("omni_purchase") or a.get("offsite_conversion_fb_pixel_purchase")))
        if not v:
            continue
        nome = nome_limpo(a.get("name"))
        g = agg.setdefault(nome, {"nome": nome, "vendas": 0, "gasto": 0.0, "miniatura": ""})
        g["vendas"] += v
        g["gasto"] += num(a.get("amount_spent"))
        c = crs.get(a.get("creative_id"), {})
        g["miniatura"] = g["miniatura"] or c.get("image_url") or c.get("thumbnail_url") or ""
    out = sorted(agg.values(), key=lambda x: (-x["vendas"], x["gasto"]))
    for g in out:
        g["gasto"] = round(g["gasto"], 2)
    return out, periodo


def saldo(valor):
    d = json.load(open("data.json", encoding="utf-8"))
    d["saldo"] = {"valor": round(float(str(valor).replace(".", "").replace(",", ".")) if "," in str(valor) else float(valor), 2), "lido_em": agora()}
    json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok: saldo", d["saldo"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["dados"]:
        dados()
    elif sys.argv[1:2] == ["vendas"]:
        d = json.load(open("data.json", encoding="utf-8"))
        crs = {c["id"]: {"image_url": c.get("miniatura")} for c in d.get("criativos", [])}
        d["vendas_criativos"], d["vendas_periodo"] = vendas(crs)
        json.dump(d, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("ok:", sum(x["vendas"] for x in d["vendas_criativos"]), "vendas em", len(d["vendas_criativos"]), "criativos")
    elif sys.argv[1:2] == ["saldo"] and len(sys.argv) > 2:
        saldo(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
