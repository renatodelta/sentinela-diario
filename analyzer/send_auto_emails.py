#!/usr/bin/env python3
"""
Disparador automático de e-mails via Resend para ocorrências pendentes.
Envia para todas as prioridades válidas (alta, media, baixa — exceto descartar)
que estejam com status == "pendente" e tenham ao menos 1 e-mail destinatário.
Atualiza status para "enviado" e registra enviado_em / enviado_para em data/ocorrencias.json.
"""

import argparse
import csv
import html
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OCORRENCIAS_JSON = DATA_DIR / "ocorrencias.json"
OCORRENCIAS_CSV = DATA_DIR / "ocorrencias.csv"
SETTINGS_JSON = DATA_DIR / "settings.json"
RESEND_CONFIG_JSON = DATA_DIR / "resend_config.json"

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "Sentinela Diário <contato@sentineladiario.com>"
COPY_TO_EMAIL = "renatodelta@gmail.com"

SIGNATURE_HTML = """<br><br>
<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, Helvetica, sans-serif; font-size: 13px; line-height: 1.4; color: #333333; max-width: 480px;">
  <tr>
    <td style="padding-right: 14px; border-right: 3px solid #0F172A; vertical-align: middle;">
      <div style="width: 44px; height: 44px; background-color: #0F172A; border-radius: 8px; text-align: center; line-height: 44px; color: #38BDF8; font-weight: bold; font-size: 18px;">
        SD
      </div>
    </td>
    <td style="padding-left: 14px; vertical-align: middle;">
      <div style="font-size: 15px; font-weight: bold; color: #0F172A;">
        Renato
      </div>
      <div style="font-size: 12px; color: #475569; margin-bottom: 6px;">
        Monitoramento Inteligente de CNPJ &amp; Diários Oficiais
      </div>
      <div style="font-size: 12px; color: #0F172A;">
        <a href="https://wa.me/5512991530244" target="_blank" rel="noopener noreferrer" style="color: #059669; text-decoration: none; font-weight: bold;">
          WhatsApp: (12) 99153-0244
        </a>
        <span style="color: #CBD5E1; margin: 0 6px;">|</span>
        <a href="https://sentineladiario.com/" target="_blank" rel="noopener noreferrer" style="color: #2563EB; text-decoration: none;">
          sentineladiario.com
        </a>
      </div>
    </td>
  </tr>
</table>"""

SIGNATURE_TEXT = (
    "\n\n--\nRenato\nMonitoramento Inteligente de CNPJ & Diários Oficiais\n"
    "WhatsApp: (12) 99153-0244 | https://sentineladiario.com/"
)


def load_resend_config() -> tuple[str, str]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM", "").strip() or DEFAULT_FROM
    if RESEND_CONFIG_JSON.exists():
        try:
            cfg = json.loads(RESEND_CONFIG_JSON.read_text(encoding="utf-8"))
            if not api_key:
                api_key = (cfg.get("api_key") or "").strip()
            if cfg.get("from"):
                sender = cfg["from"].strip()
        except Exception:
            pass
    return api_key, sender


def is_auto_enabled(default_when_missing: bool = True) -> bool:
    if SETTINGS_JSON.exists():
        try:
            st = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
            if "email_auto_enabled" in st:
                return bool(st["email_auto_enabled"])
        except Exception:
            pass
    return default_when_missing


def text_to_html(body_text: str) -> str:
    escaped = html.escape(body_text or "")
    return f'<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.55; color: #0f172a;">{escaped.replace(chr(10), "<br>")}</div>'


def export_csv(all_items: list[dict[str, Any]]) -> None:
    with OCORRENCIAS_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Prioridade", "Status", "Empresa", "CNPJ", "Situacao", "Cidade/UF",
            "Edicao", "Data", "Pagina", "Tipo de Ato", "Valor", "Emails", "Telefone",
            "Enviado Em", "Enviado Para", "Gancho",
        ])
        for it in all_items:
            writer.writerow([
                it.get("prioridade", ""),
                it.get("status", ""),
                it.get("razao_social_oficial") or it.get("empresa", ""),
                it.get("cnpj", ""),
                it.get("situacao_cadastral", ""),
                f"{it.get('municipio', '')}/{it.get('uf', '')}" if it.get("municipio") else "",
                it.get("edicao", ""),
                it.get("data_publicacao", ""),
                it.get("pagina", ""),
                it.get("tipo_ato", ""),
                it.get("valor", ""),
                ", ".join(e.get("email", "") for e in it.get("emails", [])),
                it.get("telefone", ""),
                it.get("enviado_em", ""),
                ", ".join(it.get("enviado_para", [])),
                it.get("gancho", ""),
            ])


def send_pending_emails(dry_run: bool = False, respect_settings: bool = True) -> int:
    if not OCORRENCIAS_JSON.exists():
        print("[send_auto_emails] data/ocorrencias.json nao encontrado.")
        return 0

    if respect_settings and not is_auto_enabled(default_when_missing=True):
        print("[send_auto_emails] Envio automatico desativado em data/settings.json. Nada enviado.")
        return 0

    api_key, sender = load_resend_config()
    if not dry_run and (not api_key or "COLOQUE_SUA_API_KEY" in api_key):
        print("[send_auto_emails] RESEND_API_KEY nao configurada. Abortando envio.")
        return 0

    store = json.loads(OCORRENCIAS_JSON.read_text(encoding="utf-8"))
    ocorrencias = store.get("ocorrencias", [])

    sent_count = 0
    for it in ocorrencias:
        if it.get("prioridade") == "descartar":
            continue
        if it.get("status") != "pendente":
            continue

        recipients = [
            e.strip()
            for e in (it.get("emails_selecionados") or [x.get("email", "") for x in it.get("emails", [])])
            if e and "@" in e
        ]
        if not recipients:
            continue

        subject = (it.get("assunto_email") or "").strip()
        body_text = (it.get("texto_email") or "").strip()
        if not subject or not body_text:
            continue

        payload = {
            "from": sender,
            "to": recipients,
            "reply_to": COPY_TO_EMAIL,
            "subject": subject,
            "text": body_text + SIGNATURE_TEXT,
            "html": text_to_html(body_text) + SIGNATURE_HTML,
        }
        if COPY_TO_EMAIL.lower() not in [r.lower() for r in recipients]:
            payload["bcc"] = [COPY_TO_EMAIL]

        emp_name = it.get("razao_social_oficial") or it.get("empresa") or it.get("id")
        if dry_run:
            print(f"[send_auto_emails][DRY-RUN] Enviaria para {recipients} ({emp_name})")
            sent_count += 1
            continue

        try:
            resp = requests.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            if resp.status_code in (200, 201):
                res_data = resp.json()
                it["status"] = "enviado"
                it["enviado_em"] = datetime.now().isoformat(timespec="seconds")
                it["enviado_para"] = recipients
                it["resend_id"] = res_data.get("id", "")
                sent_count += 1
                print(f"[send_auto_emails] Enviado para {recipients} ({emp_name}) | id={it['resend_id']}")
            else:
                print(f"[send_auto_emails] Erro Resend ({resp.status_code}) para {emp_name}: {resp.text}")
        except Exception as exc:
            print(f"[send_auto_emails] Excecao ao enviar para {emp_name}: {exc}")

        # Respeita limite de requisicoes por segundo do Resend
        time.sleep(0.6)

    if not dry_run and sent_count > 0:
        store["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        OCORRENCIAS_JSON.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        export_csv(ocorrencias)
        print(f"[send_auto_emails] Total enviados: {sent_count}. JSON e CSV atualizados.")
    else:
        print(f"[send_auto_emails] Concluido. Total enviados: {sent_count}.")

    return sent_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envia e-mails automaticos via Resend para ocorrencias pendentes")
    parser.add_argument("--dry-run", action="store_true", help="Simula o envio sem chamar a API do Resend")
    parser.add_argument("--ignore-settings", action="store_true", help="Ignora data/settings.json e envia mesmo assim")
    args = parser.parse_args()
    send_pending_emails(dry_run=args.dry_run, respect_settings=not args.ignore_settings)
