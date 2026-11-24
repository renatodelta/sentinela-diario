#!/usr/bin/env python3
"""
Coletor automático de PDFs do Diário do Município de São José dos Campos.
Acessa https://diariodomunicipio.sjc.sp.gov.br/, lê DADOS_ULTIMA_DATA
(e links .pdf como fallback) e baixa apenas edições que ainda não existem
em dou-sj/ nem em data/ocorrencias.json.
"""

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DOU_DIR = BASE_DIR / "dou-sj"
OCORRENCIAS_JSON = BASE_DIR / "data" / "ocorrencias.json"
PORTAL_URL = "https://diariodomunicipio.sjc.sp.gov.br/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SentinelaDiario/1.0; +https://sentineladiario.com/)"
}


def get_already_processed() -> tuple[set[str], set[str]]:
    processed_files: set[str] = set()
    processed_editions: set[str] = set()
    if DOU_DIR.exists():
        for p in DOU_DIR.glob("*.pdf"):
            processed_files.add(p.name)
    if OCORRENCIAS_JSON.exists():
        try:
            data = json.loads(OCORRENCIAS_JSON.read_text(encoding="utf-8"))
            for name in data.get("arquivos_analisados", []):
                processed_files.add(name)
            for occ in data.get("ocorrencias", []):
                ed = re.sub(r"\D", "", str(occ.get("edicao") or ""))
                if ed:
                    processed_editions.add(ed)
        except Exception:
            pass
    return processed_files, processed_editions


def extract_editions_from_portal(html: str) -> list[dict[str, str]]:
    """Extrai edições de let DADOS_ULTIMA_DATA = {...}; no HTML do portal de SJC."""
    m = re.search(r"let\s+DADOS_ULTIMA_DATA\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return []
    try:
        payload = json.loads(m.group(1))
        itens = payload.get("itens") or []
        editions: list[dict[str, str]] = []
        for it in itens:
            ed_id = it.get("id")
            ed_num = it.get("numero")
            if ed_id and ed_num:
                editions.append({
                    "id": str(ed_id),
                    "numero": str(ed_num),
                    "data": str(it.get("data") or ""),
                    "url": f"https://diariodomunicipio.sjc.sp.gov.br/portal/edicoes/download/{ed_id}",
                    "filename": f"diario_sjc_{ed_num}_{ed_id}.pdf",
                })
        return editions
    except Exception as exc:
        print(f"[fetch_dou] Falha ao interpretar DADOS_ULTIMA_DATA: {exc}")
        return []


def extract_pdf_links_fallback(html: str, base_url: str) -> list[dict[str, str]]:
    raw_matches = re.findall(r"""(?:href|src)=["']([^"']+\.pdf(?:\?[^"']*)?)["']""", html, re.IGNORECASE)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for m in raw_matches:
        full = urljoin(base_url, m.strip())
        if full not in seen:
            seen.add(full)
            fname = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", Path(urlparse(full).path).name or "edicao.pdf")
            out.append({"id": "", "numero": "", "data": "", "url": full, "filename": fname})
    return out


def fetch_new_pdfs(max_downloads: int = 5) -> list[str]:
    DOU_DIR.mkdir(parents=True, exist_ok=True)
    processed_files, processed_editions = get_already_processed()

    try:
        resp = requests.get(PORTAL_URL, headers=HEADERS, timeout=25)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[fetch_dou] Erro ao acessar {PORTAL_URL}: {exc}")
        return []

    candidates = extract_editions_from_portal(resp.text)
    if candidates:
        print(f"[fetch_dou] Edicoes encontradas em DADOS_ULTIMA_DATA: {len(candidates)}")
    else:
        candidates = extract_pdf_links_fallback(resp.text, PORTAL_URL)
        print(f"[fetch_dou] Links .pdf encontrados no fallback: {len(candidates)}")

    downloaded: list[str] = []
    for item in candidates:
        if len(downloaded) >= max_downloads:
            break
        fname = item["filename"]
        ed_num_digits = re.sub(r"\D", "", item.get("numero") or "")
        url = item["url"]

        if fname in processed_files or (ed_num_digits and ed_num_digits in processed_editions):
            print(f"[fetch_dou] Pulando (ja lido/baixado): {fname} (edicao {item.get('numero') or '-'})")
            continue

        dest = DOU_DIR / fname
        try:
            print(f"[fetch_dou] Baixando novo boletim: {fname} ({url})")
            r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            r.raise_for_status()
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "html" in ctype:
                print(f"[fetch_dou] Ignorado (retornou HTML, nao PDF): {fname}")
                continue
            with dest.open("wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            processed_files.add(fname)
            if ed_num_digits:
                processed_editions.add(ed_num_digits)
            downloaded.append(fname)
            print(f"[fetch_dou] Salvo em {dest}")
        except Exception as exc:
            print(f"[fetch_dou] Falha ao baixar {url}: {exc}")
            if dest.exists():
                dest.unlink(missing_ok=True)

    print(f"[fetch_dou] Novos PDFs baixados: {len(downloaded)}")
    return downloaded


if __name__ == "__main__":
    fetch_new_pdfs()
