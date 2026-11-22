#!/usr/bin/env python3
"""
Coletor automático do Diário do Município de São José dos Campos.
1. Verifica em https://diariodomunicipio.sjc.sp.gov.br/ se há edição nova.
2. Baixa o PDF temporariamente em dou-sj/.
3. Executa analyzer/analisar_dou.py --enrich.
4. Apaga o PDF baixado, mantendo apenas os dados extraídos.
5. Se SENTINELA_WORKER_URL estiver definida, sincroniza com o Cloudflare Worker
   (que dispara os e-mails somente se o botão no painel estiver ATIVADO).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DOU_DIR = BASE_DIR / "dou-sj"
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "ultima_edicao_sjc.json"
OCORRENCIAS_FILE = DATA_DIR / "ocorrencias.json"
ANALYZER_SCRIPT = BASE_DIR / "analyzer" / "analisar_dou.py"

PORTAL_URL = "https://diariodomunicipio.sjc.sp.gov.br/"


def fetch_latest_edition() -> dict:
    resp = requests.get(PORTAL_URL, timeout=20, headers={"User-Agent": "SentinelaDiario/1.0"})
    resp.raise_for_status()
    m = re.search(r"let\s+DADOS_ULTIMA_DATA\s*=\s*(\{.*?\});", resp.text)
    if not m:
        raise RuntimeError("Não foi possível localizar DADOS_ULTIMA_DATA na página do Diário.")
    payload = json.loads(m.group(1))
    itens = payload.get("itens") or []
    if not itens:
        raise RuntimeError("Nenhuma edição retornada em DADOS_ULTIMA_DATA.")
    return itens[0]


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def download_pdf(edition_id: int, numero: int) -> Path:
    DOU_DIR.mkdir(parents=True, exist_ok=True)
    pdf_url = f"https://diariodomunicipio.sjc.sp.gov.br/portal/edicoes/download/{edition_id}"
    pdf_path = DOU_DIR / f"diario_sjc_{numero}_{edition_id}.pdf"
    with requests.get(pdf_url, stream=True, timeout=60, headers={"User-Agent": "SentinelaDiario/1.0"}) as r:
        r.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return pdf_path


def sync_with_worker(worker_url: str, sync_secret: str) -> dict:
    if not OCORRENCIAS_FILE.exists():
        return {"skipped": True, "reason": "ocorrencias.json ausente"}
    data = json.loads(OCORRENCIAS_FILE.read_text(encoding="utf-8"))
    url = worker_url.rstrip("/")
    if "?" in url:
        url = f"{url}&action=sync_and_send"
    else:
        url = f"{url}?action=sync_and_send"
    headers = {"Content-Type": "application/json"}
    if sync_secret:
        headers["X-Sync-Secret"] = sync_secret
    resp = requests.post(url, json=data, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Coletor automático do Diário de SJC")
    parser.add_argument("--force", action="store_true", help="Baixa e processa mesmo que a edição já tenha sido processada.")
    parser.add_argument("--keep-pdf", action="store_true", help="Não apaga o PDF após a análise.")
    args = parser.parse_args()

    edition = fetch_latest_edition()
    ed_id = int(edition["id"])
    ed_num = int(edition["numero"])
    ed_data = edition.get("data", "")

    state = load_state()
    if not args.force and state.get("last_id") == ed_id:
        print(f"Nenhuma edição nova. Última já processada: nº {ed_num} ({ed_data}, id={ed_id}).")
        return 0

    print(f"Nova edição encontrada: nº {ed_num} ({ed_data}, id={ed_id}). Baixando PDF...")
    pdf_path = download_pdf(ed_id, ed_num)
    try:
        print(f"PDF salvo temporariamente em {pdf_path}. Executando analisador...")
        res = subprocess.run(
            [sys.executable, str(ANALYZER_SCRIPT), "--enrich"],
            cwd=str(BASE_DIR),
            check=True,
        )
        print(f"Análise concluída (código {res.returncode}).")
    finally:
        if not args.keep_pdf and pdf_path.exists():
            pdf_path.unlink(missing_ok=True)
            print(f"PDF removido: {pdf_path.name}")

    save_state({
        "last_id": ed_id,
        "last_numero": ed_num,
        "last_data": ed_data,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    })

    worker_url = os.getenv("SENTINELA_WORKER_URL", "").strip()
    sync_secret = os.getenv("SYNC_SECRET", "").strip()
    if worker_url:
        print(f"Sincronizando com Cloudflare Worker ({worker_url})...")
        sync_res = sync_with_worker(worker_url, sync_secret)
        print("Resposta do Worker:", json.dumps(sync_res, ensure_ascii=False))
    else:
        print("SENTINELA_WORKER_URL não configurada; sincronização com a nuvem pulada.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
