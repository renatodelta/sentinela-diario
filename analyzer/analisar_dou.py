#!/usr/bin/env python3
"""
Analisador de Diários Oficiais de São José dos Campos (pasta dou-sj/).
Extrai contratos, aditivos, apostilamentos, rescisões, dispensas e notificações sanitárias,
classifica por prioridade de prospecção e gera textos de e-mail personalizados.
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DOU_DIR = BASE_DIR / "dou-sj"
DATA_DIR = BASE_DIR / "data"
OCORRENCIAS_JSON = DATA_DIR / "ocorrencias.json"
OCORRENCIAS_CSV = DATA_DIR / "ocorrencias.csv"
CONHECIDAS_JSON = DATA_DIR / "empresas_conhecidas.json"

LANDING_URL = "https://sentinela-diario.pages.dev/"

MESES = {
    "janeiro": "01",
    "fevereiro": "02",
    "março": "03",
    "marco": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}

CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
VALOR_RE = re.compile(r"R\$\s*[\d\.]+,\d{2}")


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def format_cnpj(digits: str) -> str:
    d = re.sub(r"\D", "", digits or "")
    if len(d) != 14:
        return digits or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def parse_valor_float(valor_str: str) -> float:
    if not valor_str:
        return 0.0
    m = VALOR_RE.search(valor_str)
    if not m:
        return 0.0
    num = m.group(0).replace("R$", "").strip().replace(".", "").replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return 0.0


def extract_columns_from_pdf(pdf_path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Extrai metadados da edição e o texto limpo por página/coluna (layout 2 colunas)."""
    meta = {
        "arquivo": pdf_path.name,
        "edicao": "",
        "data_publicacao": "",
    }
    columns: list[dict[str, Any]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages):
            pno = idx + 1
            w, h = page.width, page.height
            # Captura edição e data no cabeçalho da página 1
            if pno == 1:
                full_top = page.crop((0, 0, w, 220)).extract_text() or ""
                m_ed = re.search(r"ANO\s+[IVXLCDM]+.*?N[º°o]\s*([\d\.]+)", full_top, re.IGNORECASE | re.DOTALL)
                if not m_ed:
                    m_ed = re.search(r"N[º°o]\s*([\d\.]+)", full_top)
                if m_ed:
                    meta["edicao"] = m_ed.group(1)
                m_dt = re.search(
                    r"(\d{1,2})\s+DE\s+([A-ZÇÃÕÉÊÓÔ]+)\s+DE\s+(\d{4})",
                    full_top,
                    re.IGNORECASE,
                )
                if m_dt:
                    dia = m_dt.group(1).zfill(2)
                    mes = MESES.get(m_dt.group(2).lower(), "01")
                    ano = m_dt.group(3)
                    meta["data_publicacao"] = f"{dia}/{mes}/{ano}"

            for side, box in [("L", (0, 0, w / 2, h)), ("R", (w / 2, 0, w, h))]:
                raw = page.crop(box).extract_text() or ""
                lines = []
                for line in raw.splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    # Remove cabeçalhos recorrentes
                    if re.match(r"^DI[ÁA]RIO DO MUNIC[ÍI]PIO", s, re.IGNORECASE):
                        continue
                    if re.match(r"^\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\s*-\s*p[áa]gina", s, re.IGNORECASE):
                        continue
                    if s.startswith("EXPEDIENTE:") or s.startswith("- e-mail do Diário"):
                        continue
                    if s.startswith("https://diariodomunicipio.sjc.sp.gov.br"):
                        continue
                    lines.append(s)
                if lines:
                    columns.append({"pagina": pno, "lado": side, "lines": lines, "text": "\n".join(lines)})

    return meta, columns


def extract_company_from_partes(partes_text: str) -> str:
    """Extrai o nome da empresa privada a partir do campo PARTES."""
    t = clean_spaces(partes_text)
    # Remove prefixos comuns do Município
    t = re.sub(
        r"^(?:O\s+)?MUNIC[ÍI]PIO\s+DE\s+S[ÃA]O\s+JOS[ÉE]\s+DOS\s+CAMPOS(?:\s*\([^\)]+\))?\s*(?:,|E\s+A\s+|E\s+O\s+|E\s+)",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^(?:INSTITUTO\s+DE\s+PREVID[ÊE]NCIA\s+DO\s+SERVIDOR\s+MUNICIPAL\s*[-–]?\s*IPSM\s+E\s+(?:A\s+)?)",
        "",
        t,
        flags=re.IGNORECASE,
    )
    return t.strip(" .,-")


def parse_structured_blocks(columns: list[dict[str, Any]], meta: dict[str, str]) -> list[dict[str, Any]]:
    """Extrai atos estruturados (Contratos, Aditivos, Apostilamentos, Rescisões, Dispensas, Vigilância)."""
    results: list[dict[str, Any]] = []

    # Regex de início de bloco estruturado de Contratos/Aditivos/Rescisões/ARPs
    header_re = re.compile(
        r"^(CONTRATO\s+N[º°]\s*[\d/]+|"
        r"ARP\s+N[º°]\s*[\d/]+|"
        r"\d+[º°]\s*TERMO\s+DE\s+ADITAMENTO\s+(?:DO|AO)\s+(?:CONTRATO|ARP|TERMO\s+DE\s+COLABORA[ÇC][ÃA]O)\s+N[º°]\s*[\d/]+|"
        r"RESCIS[ÃA]O\s+DO\s+CONTRATO\s+N[º°]\s*[\d/]+|"
        r"TERMO\s+DE\s+RESCIS[ÃA]O\s+.*?N[º°]\s*[\d/]+)$",
        re.IGNORECASE,
    )

    public_cnpjs = {"57.522.468/0001-63", "45.693.777/0001-17", "46.643.466/0001-06"}

    # Junta todas as colunas mantendo o rastreamento de página por linha
    stream: list[tuple[int, str]] = []
    for col in columns:
        for line in col["lines"]:
            stream.append((col["pagina"], line))

    i = 0
    n = len(stream)
    while i < n:
        pno, line = stream[i]

        # 1. Blocos estruturados padrão (CONTRATO / ADITAMENTO / RESCISÃO)
        if header_re.match(line):
            titulo = line
            block_lines = [line]
            j = i + 1
            while j < n:
                _, nxt = stream[j]
                if header_re.match(nxt):
                    break
                if re.match(r"^(PROCESSO\s+N[º°]|Portarias|Licitações|Secretaria|Urbam|PREFEITURA)", nxt, re.IGNORECASE):
                    break
                if nxt.startswith("PROCESSO ADMINISTRATIVO DIGITAL:"):
                    block_lines.append(nxt)
                    j += 1
                    break
                block_lines.append(nxt)
                j += 1
                if len(block_lines) > 35:
                    break

            block_text = "\n".join(block_lines)
            # Extrai campos chave: DATA, PARTES, OBJETO, VALOR, NOVA VIGÊNCIA, MODALIDADE, PROCESSO
            fields: dict[str, str] = {}
            current_key = None
            key_re = re.compile(
                r"^(DATA|PARTES|OBJETO|VALOR|NOVA\s+VIG[ÊE]NCIA|VIG[ÊE]NCIA|MODALIDADE|PROCESSO\s+ADMINISTRATIVO\s+DIGITAL):\s*(.*)$",
                re.IGNORECASE,
            )
            for bl in block_lines[1:]:
                km = key_re.match(bl)
                if km:
                    current_key = km.group(1).upper()
                    fields[current_key] = km.group(2).strip()
                elif current_key:
                    fields[current_key] = (fields[current_key] + " " + bl).strip()

            partes = fields.get("PARTES", "")
            empresa = extract_company_from_partes(partes)
            if empresa:
                cnpjs = [c for c in CNPJ_RE.findall(block_text) if c not in public_cnpjs]
                results.append(
                    {
                        "arquivo_pdf": meta["arquivo"],
                        "edicao": meta["edicao"],
                        "data_publicacao": meta["data_publicacao"],
                        "pagina": pno,
                        "tipo_ato": titulo,
                        "contrato_ou_arp": titulo,
                        "empresa": empresa,
                        "cnpj": cnpjs[0] if cnpjs else "",
                        "objeto": clean_spaces(fields.get("OBJETO", "")),
                        "valor": clean_spaces(fields.get("VALOR", "")),
                        "vigencia": clean_spaces(fields.get("NOVA VIGÊNCIA") or fields.get("NOVA VIGENCIA") or fields.get("VIGÊNCIA") or ""),
                        "modalidade": clean_spaces(fields.get("MODALIDADE", "")),
                        "processo": clean_spaces(fields.get("PROCESSO ADMINISTRATIVO DIGITAL", "")),
                        "trecho": clean_spaces(block_text)[:600],
                    }
                )
            i = j
            continue

        # 2. Termos de Apostilamento (texto corrido iniciado por PROCESSO Nº ou Xº TERMO DE APOSTILAMENTO)
        m_apost = re.match(
            r"^(\d+[º°]\s+TERMO\s+DE\s+APOSTILAMENTO\s+AO\s+CONTRATO\s+N[º°]\.?\s*[\d/]+)",
            line,
            re.IGNORECASE,
        )
        if m_apost:
            titulo = m_apost.group(1)
            # Evita duplicar se a linha seguinte repetir o título
            block_lines = [line]
            j = i + 1
            while j < n and len(block_lines) < 28:
                _, nxt = stream[j]
                if header_re.match(nxt) or re.match(r"^\d+[º°]\s+TERMO\s+DE\s+APOSTILAMENTO", nxt, re.IGNORECASE):
                    break
                if re.match(r"^(EDITAL|Portarias|Secretaria|Urbam)", nxt, re.IGNORECASE):
                    break
                block_lines.append(nxt)
                if "PASSA A FAZER PARTE INTEGRANTE" in nxt.upper():
                    j += 1
                    break
                j += 1
            block_text = clean_spaces(" ".join(block_lines))
            # Extrai empresa após "E A EMPRESA " ou "CELEBRADO ENTRE ... E "
            empresa = ""
            m_emp = re.search(
                r"(?:E\s+A\s+EMPRESA\s+|CELEBRADO\s+ENTRE\s+.*?\s+E\s+(?:A\s+)?)([A-Z0-9À-Ú\s\.\-/&]+?)(?:,|\s+INSCRITA|\s+1\s*-|\s*-\s*DO\s+OBJETO|\s+CL[ÁA]USULA|\.(?:\s|$))",
                block_text,
                re.IGNORECASE,
            )
            if m_emp:
                empresa = clean_spaces(m_emp.group(1))
            # Se houve alteração de razão social ("CONSTAR COMO ..."), prioriza a nova razão social
            m_constar = re.search(r"CONSTAR\s+COMO\s+([A-Z0-9À-Ú\s\.\-/&]+?)(?:,|\s+INSCRITA)", block_text, re.IGNORECASE)
            if m_constar:
                empresa = clean_spaces(m_constar.group(1))
            cnpjs = [c for c in CNPJ_RE.findall(block_text) if c not in public_cnpjs]
            m_proc = re.search(r"PROCESSO\s+(?:ADMINISTRATIVO\s+)?N[º°]\.?\s*([\d\./]+)", block_text, re.IGNORECASE)
            vals = VALOR_RE.findall(block_text)
            if empresa and not any(
                r["pagina"] == pno and r["empresa"] == empresa and "APOSTILAMENTO" in r["tipo_ato"].upper()
                for r in results
            ):
                results.append(
                    {
                        "arquivo_pdf": meta["arquivo"],
                        "edicao": meta["edicao"],
                        "data_publicacao": meta["data_publicacao"],
                        "pagina": pno,
                        "tipo_ato": titulo,
                        "contrato_ou_arp": titulo,
                        "empresa": empresa,
                        "cnpj": cnpjs[0] if cnpjs else "",
                        "objeto": block_text[:280],
                        "valor": vals[-1] if vals else "",
                        "vigencia": "",
                        "modalidade": "Apostilamento",
                        "processo": m_proc.group(1) if m_proc else "",
                        "trecho": block_text[:600],
                    }
                )
            i = j
            continue

        # 3. Dispensa de Licitação inline ("Ratifico de contratação por Dispensa de Licitação...")
        if "RATIFICO DE CONTRATA" in line.upper() and "DISPENSA DE LICITA" in line.upper():
            block_lines = [line]
            j = i + 1
            while j < n and len(block_lines) < 16:
                _, nxt = stream[j]
                if re.match(r"^(Portaria|Secretaria|DECRETO|EDITAL)", nxt, re.IGNORECASE):
                    break
                block_lines.append(nxt)
                j += 1
            block_text = clean_spaces(" ".join(block_lines))
            m_emp = re.search(r"Contratad[ao]:\s*([^\.\“\"]+)", block_text, re.IGNORECASE)
            m_proc = re.search(r"Processo:\s*([\d\./]+)", block_text, re.IGNORECASE)
            m_obj = re.search(r"Objeto:\s*([^\”\"]+)", block_text, re.IGNORECASE)
            vals = VALOR_RE.findall(block_text)
            empresa = clean_spaces(m_emp.group(1)) if m_emp else ""
            if empresa:
                results.append(
                    {
                        "arquivo_pdf": meta["arquivo"],
                        "edicao": meta["edicao"],
                        "data_publicacao": meta["data_publicacao"],
                        "pagina": pno,
                        "tipo_ato": "Dispensa de Licitação",
                        "contrato_ou_arp": f"Dispensa - Proc. {m_proc.group(1) if m_proc else ''}",
                        "empresa": empresa,
                        "cnpj": "",
                        "objeto": clean_spaces(m_obj.group(1)) if m_obj else block_text[:220],
                        "valor": vals[0] if vals else "",
                        "vigencia": "",
                        "modalidade": "Dispensa de Licitação",
                        "processo": m_proc.group(1) if m_proc else "",
                        "trecho": block_text[:600],
                    }
                )
            i = j
            continue

        # 4. Editais de Interdição (Vigilância Sanitária)
        if "INTERDIÇÃO PARCIAL OU TOTAL DO ESTABELECIMENTO" in line.upper():
            block_lines = [line]
            j = i + 1
            while j < n and len(block_lines) < 12:
                _, nxt = stream[j]
                if nxt.upper().startswith("INTERDIÇÃO PARCIAL") or nxt.upper().startswith("TÍTULO DE REGISTRO"):
                    break
                block_lines.append(nxt)
                j += 1
            block_text = clean_spaces(" ".join(block_lines))
            # Atenção: no edital original, o CNPJ costuma aparecer rotulado como "Processo: XX.XXX.XXX/XXXX-XX"
            cnpjs = [c for c in CNPJ_RE.findall(block_text) if c not in public_cnpjs]
            m_proc = re.search(r"(?:CNPJ|Processo):\s*(\d+/\d{4})", block_text, re.IGNORECASE)
            cnpj_val = cnpjs[0] if cnpjs else ""
            results.append(
                {
                    "arquivo_pdf": meta["arquivo"],
                    "edicao": meta["edicao"],
                    "data_publicacao": meta["data_publicacao"],
                    "pagina": pno,
                    "tipo_ato": "Edital de Interdição (Vigilância Sanitária)",
                    "contrato_ou_arp": f"Edital de Interdição - Proc. {m_proc.group(1) if m_proc else 'S/N'}",
                    "empresa": f"Estabelecimento CNPJ {cnpj_val}" if cnpj_val else "Estabelecimento Interditado",
                    "cnpj": cnpj_val,
                    "objeto": "Interdição parcial ou total do estabelecimento (suspensão de atividades pela Vigilância Sanitária).",
                    "valor": "",
                    "vigencia": "",
                    "modalidade": "Vigilância Sanitária",
                    "processo": m_proc.group(1) if m_proc else "",
                    "trecho": block_text[:600],
                }
            )
            i = j
            continue

        # 5. Registro Sanitário SIM
        if line.upper().startswith("TÍTULO DE REGISTRO NO SERVIÇO DE INSPEÇÃO MUNICIPAL"):
            block_lines = [line]
            j = i + 1
            while j < n and len(block_lines) < 12:
                _, nxt = stream[j]
                if re.match(r"^(Secretaria|Portaria|DECRETO|EDITAL)", nxt, re.IGNORECASE):
                    break
                block_lines.append(nxt)
                j += 1
            block_text = clean_spaces(" ".join(block_lines))
            m_emp = re.search(r"Raz[ãa]o\s+Social:\s*(.+?)(?:\s+C\.?N\.?P\.?J\.?|\s+Data|$)", block_text, re.IGNORECASE)
            if not m_emp:
                i = j
                continue
            cnpjs = [c for c in CNPJ_RE.findall(block_text) if c not in public_cnpjs]
            m_proc = re.search(r"Processo:\s*([\d/]+)", block_text, re.IGNORECASE)
            empresa = clean_spaces(m_emp.group(1))
            results.append(
                {
                    "arquivo_pdf": meta["arquivo"],
                    "edicao": meta["edicao"],
                    "data_publicacao": meta["data_publicacao"],
                    "pagina": pno,
                    "tipo_ato": "Registro Sanitário (SIM)",
                    "contrato_ou_arp": f"Registro SIM - Proc. {m_proc.group(1) if m_proc else ''}",
                    "empresa": empresa,
                    "cnpj": cnpjs[0] if cnpjs else "",
                    "objeto": "Deferimento de Título de Registro no Serviço de Inspeção Municipal (SIM).",
                    "valor": "",
                    "vigencia": "",
                    "modalidade": "SIM",
                    "processo": m_proc.group(1) if m_proc else "",
                    "trecho": block_text[:600],
                }
            )
            i = j
            continue

        i += 1

    return results


def classify_occurrence(item: dict[str, Any]) -> tuple[str, str, str]:
    """
    Aplica os critérios da conversa Gemini:
    - Descarta estatais (URBAM, FUNDHAS, IPSM) e organizações sem fins lucrativos (OS, Associações).
    - Prioridade Alta: interdições, rescisões, novos contratos ou aditivos >= R$ 200.000.
    - Prioridade Média: aditivos de ARP/contratos, prorrogações, reajustes relevantes.
    - Prioridade Baixa: apostilamentos, reajustes pequenos, registros SIM.
    """
    emp_up = item["empresa"].upper()
    tipo_up = item["tipo_ato"].upper()
    obj_up = item["objeto"].upper()
    val_num = parse_valor_float(item["valor"])

    if any(k in emp_up for k in ["URBAM", "URBANIZADORA MUNICIPAL", "FUNDHAS", "IPSM"]):
        return "descartar", "Empresa pública / estatal municipal (não valida venda SaaS B2B).", ""
    if any(k in emp_up for k in ["ORGANIZACAO SOCIAL", "ORGANIZAÇÃO SOCIAL", "CENTRO DE DESENVOLVIMENTO", "ASSOCIACAO", "ASSOCIAÇÃO", "INSTITUTO "]) or "ORGANIZAÇÃO SOCIAL" in obj_up or "ORGANIZACAO SOCIAL" in obj_up:
        return "descartar", "Entidade sem fins lucrativos / Organização Social (decisão burocrática).", ""

    if "INTERDIÇÃO" in tipo_up or "INTERDICAO" in tipo_up:
        return "alta", "", f"Alerta urgente de interdição sanitária publicada na pág. {item['pagina']} (Edição nº {item['edicao']})."
    if "RESCIS" in tipo_up:
        return "alta", "", f"Publicação de rescisão unilateral de contrato na pág. {item['pagina']} (evento crítico para jurídico/diretoria)."
    if tipo_up.startswith("CONTRATO N") or val_num >= 200000:
        return "alta", "", f"Contrato/aditivo de alto valor ({item['valor'] or 'vigência estendida'}) publicado na pág. {item['pagina']}."
    if "ADITAMENTO" in tipo_up:
        return "media", "", f"Prorrogação de vigência / saldo contratual publicado na pág. {item['pagina']}."
    if "APOSTILAMENTO" in tipo_up:
        return "baixa", "", f"Apostilamento contratual (reajuste ou atualização cadastral) publicado na pág. {item['pagina']}."
    if "SIM" in tipo_up:
        return "baixa", "", f"Deferimento de registro sanitário (SIM) publicado na pág. {item['pagina']}."

    return "media", "", f"Publicação oficial envolvendo a empresa na pág. {item['pagina']}."


def load_conhecidas() -> dict[str, Any]:
    if CONHECIDAS_JSON.exists():
        return json.loads(CONHECIDAS_JSON.read_text(encoding="utf-8"))
    return {"by_cnpj": {}, "name_aliases": {}}


def lookup_brasilapi(cnpj: str) -> dict[str, Any]:
    digits = re.sub(r"\D", "", cnpj or "")
    if len(digits) != 14:
        return {}
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{digits}", timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def build_email_draft(item: dict[str, Any]) -> tuple[str, str]:
    emp = item.get("razao_social_oficial") or item["empresa"]
    ato = item["tipo_ato"]
    edicao = item["edicao"] or "recente"
    data_pub = item["data_publicacao"] or ""
    pagina = item["pagina"]
    objeto_curto = item["objeto"][:180].rstrip(".")
    valor_txt = f" (valor citado: {item['valor']})" if item.get("valor") else ""

    if "INTERDIÇÃO" in ato.upper() or "INTERDICAO" in ato.upper():
        assunto = f"Alerta urgente no Diário Oficial de SJC: {ato} — {emp}"
        corpo = (
            f"Olá, equipe da {emp},\n\n"
            f"Identificamos hoje uma publicação urgente envolvendo o CNPJ da empresa no Diário Oficial do Município de São José dos Campos "
            f"(Edição nº {edicao}, de {data_pub}, página {pagina}):\n\n"
            f"• Ato: {ato}\n"
            f"• Processo: {item.get('processo') or 'conforme edital'}\n"
            f"• Resumo: {objeto_curto}.\n\n"
            f"Estou lançando o Sentinela Diário, um sistema que monitora o CNPJ das empresas nos Diários Oficiais e envia um resumo imediato no WhatsApp e por e-mail "
            f"sempre que sai qualquer notificação, edital sanitário, contrato ou prazo — evitando que a empresa seja pega de surpresa.\n\n"
            f"Gostaria de testar gratuitamente por 15 dias para a {emp}?\n"
            f"Você pode conhecer mais e ativar o teste em: {LANDING_URL}\n\n"
            f"Fico à disposição!"
        )
    else:
        assunto = f"Publicação no Diário Oficial de SJC ({ato}) — {emp}"
        corpo = (
            f"Olá, equipe da {emp},\n\n"
            f"Vi que a {emp} teve uma publicação recente no Diário Oficial do Município de São José dos Campos "
            f"(Edição nº {edicao}{', de ' + data_pub if data_pub else ''}, página {pagina}):\n\n"
            f"• Ato: {ato}{valor_txt}\n"
            f"• Objeto: {objeto_curto}.\n\n"
            f"Estou lançando o Sentinela Diário, um sistema que monitora automaticamente o CNPJ da empresa nos Diários Oficiais e avisa no WhatsApp e e-mail "
            f"com um resumo objetivo sempre que sai algo novo (contratos, aditivos, reajustes, prazos de vigência ou notificações).\n\n"
            f"Gostaria de testar gratuitamente por 15 dias para acompanhar os contratos e publicações da {emp}?\n"
            f"Veja como funciona em: {LANDING_URL}\n\n"
            f"Um abraço!"
        )
    return assunto, corpo


def make_id(item: dict[str, Any]) -> str:
    raw = f"{item['arquivo_pdf']}|{item['pagina']}|{item['tipo_ato']}|{item['empresa']}|{item['cnpj']}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def analyze_all(enrich_api: bool = False) -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conhecidas = load_conhecidas()
    by_cnpj = conhecidas.get("by_cnpj", {})
    aliases = conhecidas.get("name_aliases", {})

    # Carrega ocorrências anteriores para preservar status, e-mails manuais e edições do usuário
    existing_map: dict[str, dict[str, Any]] = {}
    if OCORRENCIAS_JSON.exists():
        try:
            old_data = json.loads(OCORRENCIAS_JSON.read_text(encoding="utf-8"))
            for old in old_data.get("ocorrencias", []):
                existing_map[old["id"]] = old
        except Exception:
            pass

    pdf_files = sorted(DOU_DIR.glob("*.pdf"))
    all_items: list[dict[str, Any]] = []

    for pdf_path in pdf_files:
        meta, columns = extract_columns_from_pdf(pdf_path)
        items = parse_structured_blocks(columns, meta)
        for item in items:
            prioridade, motivo_descarte, gancho = classify_occurrence(item)
            item["prioridade"] = prioridade
            item["motivo_descarte"] = motivo_descarte
            item["gancho"] = gancho

            # Tenta casar CNPJ conhecido pelo nome ou CNPJ extraído
            cnpj_norm = format_cnpj(item["cnpj"]) if item["cnpj"] else ""
            if not cnpj_norm:
                emp_up = item["empresa"].upper()
                for alias, mapped_cnpj in aliases.items():
                    if alias in emp_up:
                        cnpj_norm = mapped_cnpj
                        break
            item["cnpj"] = cnpj_norm

            known = by_cnpj.get(cnpj_norm, {})
            item["razao_social_oficial"] = known.get("razao_social", "")
            item["situacao_cadastral"] = known.get("situacao", "")
            item["municipio"] = known.get("municipio", "")
            item["uf"] = known.get("uf", "")
            item["telefone"] = known.get("telefone", "")
            item["cnae"] = known.get("cnae", "")
            item["socios"] = known.get("socios", [])
            item["emails"] = list(known.get("emails", []))

            if enrich_api and cnpj_norm:
                api_data = lookup_brasilapi(cnpj_norm)
                if api_data:
                    item["razao_social_oficial"] = api_data.get("razao_social") or item["razao_social_oficial"]
                    item["situacao_cadastral"] = api_data.get("descricao_situacao_cadastral") or item["situacao_cadastral"]
                    item["municipio"] = api_data.get("municipio") or item["municipio"]
                    item["uf"] = api_data.get("uf") or item["uf"]
                    item["cnae"] = api_data.get("cnae_fiscal_descricao") or item["cnae"]
                    if api_data.get("ddd_telefone_1") and not item["telefone"]:
                        item["telefone"] = api_data["ddd_telefone_1"]
                    if api_data.get("qsa"):
                        item["socios"] = [s.get("nome_socio", "") for s in api_data["qsa"] if s.get("nome_socio")]
                    if api_data.get("email"):
                        em = api_data["email"].strip().lower()
                        if em and not any(e["email"].lower() == em for e in item["emails"]):
                            item["emails"].append({"email": em, "fonte": "Receita Federal / BrasilAPI"})

            item_id = make_id(item)
            item["id"] = item_id

            assunto, corpo = build_email_draft(item)
            item["assunto_email"] = assunto
            item["texto_email"] = corpo
            item["status"] = "descartado" if prioridade == "descartar" else "pendente"
            item["notas"] = ""
            item["emails_selecionados"] = [e["email"] for e in item["emails"]]

            # Preserva edições do usuário se já existia
            if item_id in existing_map:
                old = existing_map[item_id]
                for keep_key in ["status", "notas", "assunto_email", "texto_email", "emails_selecionados"]:
                    if old.get(keep_key) is not None and old.get(keep_key) != "":
                        item[keep_key] = old[keep_key]
                # Mescla e-mails adicionados manualmente
                known_set = {e["email"].lower() for e in item["emails"]}
                for old_e in old.get("emails", []):
                    if old_e["email"].lower() not in known_set:
                        item["emails"].append(old_e)
                        known_set.add(old_e["email"].lower())

            all_items.append(item)

    # Ordena: alta -> media -> baixa -> descartar
    order_map = {"alta": 0, "media": 1, "baixa": 2, "descartar": 3}
    all_items.sort(key=lambda x: (order_map.get(x["prioridade"], 9), x["arquivo_pdf"], x["pagina"]))

    payload = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "total": len(all_items),
        "arquivos_analisados": [p.name for p in pdf_files],
        "ocorrencias": all_items,
    }
    OCORRENCIAS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Exporta CSV também para facilitar uso em planilhas
    with OCORRENCIAS_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Prioridade", "Status", "Empresa", "CNPJ", "Situacao", "Cidade/UF",
            "Edicao", "Data", "Pagina", "Tipo de Ato", "Valor", "Emails", "Telefone", "Gancho"
        ])
        for it in all_items:
            writer.writerow([
                it["prioridade"],
                it["status"],
                it["razao_social_oficial"] or it["empresa"],
                it["cnpj"],
                it["situacao_cadastral"],
                f"{it['municipio']}/{it['uf']}" if it["municipio"] else "",
                it["edicao"],
                it["data_publicacao"],
                it["pagina"],
                it["tipo_ato"],
                it["valor"],
                ", ".join(e["email"] for e in it["emails"]),
                it["telefone"],
                it["gancho"],
            ])

    return all_items


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analisa os Diários Oficiais de SJC na pasta dou-sj/")
    parser.add_argument("--enrich", action="store_true", help="Consulta BrasilAPI para enriquecer CNPJs com CNAE e sócios")
    args = parser.parse_args()
    items = analyze_all(enrich_api=args.enrich)
    print(f"Analise concluida: {len(items)} ocorrencias extraidas em {OCORRENCIAS_JSON}")
    for it in items:
        emails_str = ", ".join(e["email"] for e in it["emails"]) or "sem email"
        print(f"  [{it['prioridade'].upper():9}] P.{it['pagina']:2} ({it['edicao']}) | {it['empresa'][:40]:40} | CNPJ: {it['cnpj'] or '-':18} | {emails_str}")
