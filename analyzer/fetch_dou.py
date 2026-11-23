#!/usr/bin/env python3
"""
Coletor automático de PDFs do Diário do Município de São José dos Campos.
Acessa https://diariodomunicipio.sjc.sp.gov.br/, encontra links de PDFs de edições
e baixa apenas os arquivos que ainda não existem em dou-sj/ nem em data/ocorrencias.json.
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


def get_already_processed() -> set[str]:
    processed: set[str] = set()
    if DOU_DIR.exists():
        for p in DOU_DIR.glob("*.pdf"):
            processed.add(p.name)
    if OCORRENCIAS_JSON.exists():
        try:
            data = json.loads(OCORRENCIAS_JSON.read_text(encoding="utf-8"))
            for name in data.get("arquivos_analisados", []):
                processed.add(name)
        except Exception:
            pass
    return processed


def extract_pdf_links(html: str, base_url: str) -> list[str]:
    # Captura hrefs e URLs diretas para arquivos .pdf
    raw_matches = re.findall(r"""(?:href|src)=["']([^"']+\.pdf(?:\?[^"']*)?)["']""", html, re.IGNORECASE)
    if not raw_matches:
        raw_matches = re.findall(r"""(https?://[^\s"'<>]+\.pdf(?:\?[^\s"'<>]*)?)""", html, re.IGNORECASE)

    seen: set[str] = set()
    urls: list[str] = []
    for m in raw_matches:
        full = urljoin(base_url, m.strip())
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def safe_filename(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name or "edicao.pdf"
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)


def fetch_new_pdfs(max_downloads: int = 5) -> list[str]:
    DOU_DIR.mkdir(parents=True, exist_ok=True)
    already = get_already_processed()

    try:
        resp = requests.get(PORTAL_URL, headers=HEADERS, timeout=25)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[fetch_dou] Erro ao acessar {PORTAL_URL}: {exc}")
        return []

    pdf_urls = extract_pdf_links(resp.text, PORTAL_URL)
    print(f"[fetch_dou] Links .pdf encontrados no portal: {len(pdf_urls)}")

    downloaded: list[str] = []
    for url in pdf_urls:
        if len(downloaded) >= max_downloads:
            break
        fname = safe_filename(url)
        if fname in already:
            print(f"[fetch_dou] Pulando (ja lido/baixado): {fname}")
            continue

        dest = DOU_DIR / fname
        try:
            print(f"[fetch_dou] Baixando novo boletim: {fname} ({url})")
            r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            r.raise_for_status()
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "pdf" not in ctype and not fname.lower().endswith(".pdf"):
                print(f"[fetch_dou] Ignorado (nao e PDF): {fname} ({ctype})")
                continue
            with dest.open("wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            already.add(fname)
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
