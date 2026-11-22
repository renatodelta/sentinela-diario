const DEFAULT_FROM = "Sentinela Diário <contato@sentineladiario.com>";
// Enquanto estiver testando, todos os envios vão para este e-mail.
// Para enviar para as empresas reais no futuro, mude para null.
const TEST_REDIRECT_EMAIL = "renatodelta@gmail.com";

const SIGNATURE_HTML = `
<br><br>
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
</table>`;

const SIGNATURE_TEXT =
  "\n\n--\nRenato\nMonitoramento Inteligente de CNPJ & Diários Oficiais\nWhatsApp: (12) 99153-0244 | https://sentineladiario.com/";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Sync-Secret",
};

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...CORS_HEADERS,
    },
  });
}

async function sendViaResend(apiKey, { from, to, subject, html, text }) {
  const realTo = Array.isArray(to) ? to : [to];
  const finalTo = TEST_REDIRECT_EMAIL ? [TEST_REDIRECT_EMAIL] : realTo;
  const finalSubject = TEST_REDIRECT_EMAIL
    ? `[TESTE -> ${realTo.join(", ")}] ${subject}`
    : subject;

  const payload = {
    from: from || DEFAULT_FROM,
    to: finalTo,
    subject: finalSubject,
  };
  if (html) payload.html = html + SIGNATURE_HTML;
  if (text) payload.text = text + SIGNATURE_TEXT;

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function extractRecipientEmail(occ) {
  if (occ.email_escolhido && occ.email_escolhido.includes("@")) return occ.email_escolhido.trim();
  if (Array.isArray(occ.emails) && occ.emails.length > 0) {
    const first = occ.emails[0];
    if (typeof first === "string" && first.includes("@")) return first.trim();
    if (first && typeof first.email === "string" && first.email.includes("@")) return first.email.trim();
  }
  if (occ.email_receita && occ.email_receita.includes("@")) return occ.email_receita.trim();
  return null;
}

function shortCompanyName(name, maxLen = 45) {
  const clean = String(name || "Sua Empresa").trim();
  return clean.length > maxLen ? clean.slice(0, maxLen - 1).trim() + "…" : clean;
}

function findMatchingSubscriber(occ, subscribers) {
  const occCnpj = String(occ.cnpj || "").replace(/\D/g, "");
  const occName = String(occ.empresa || "").toUpperCase();
  const now = Date.now();
  for (const sub of subscribers) {
    if (!sub.ativo) continue;
    if (sub.expira_em && Date.parse(sub.expira_em) < now) continue;
    if (occCnpj && sub.cnpj_digits && occCnpj === sub.cnpj_digits) return sub;
    if (occName && sub.empresa_upper && occName.includes(sub.empresa_upper)) return sub;
  }
  return null;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const action = url.searchParams.get("action") || "list";

    if (action === "list") {
      const stored = await env.SENTINELA_KV.get("ocorrencias_store", { type: "json" });
      return jsonResponse(
        stored || { gerado_em: null, total: 0, arquivos_analisados: [], ocorrencias: [] }
      );
    }

    if (action === "save" && request.method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body || !Array.isArray(body.ocorrencias)) {
        return jsonResponse({ error: "Payload inválido." }, 400);
      }
      body.atualizado_em = new Date().toISOString();
      await env.SENTINELA_KV.put("ocorrencias_store", JSON.stringify(body));
      return jsonResponse({ ok: true, total: body.ocorrencias.length });
    }

    if (action === "get_settings") {
      const settings = (await env.SENTINELA_KV.get("settings", { type: "json" })) || {};
      return jsonResponse({ email_auto_enabled: false, ...settings });
    }

    if (action === "set_settings" && request.method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body || typeof body.email_auto_enabled !== "boolean") {
        return jsonResponse({ error: "Payload inválido." }, 400);
      }
      const current = (await env.SENTINELA_KV.get("settings", { type: "json" })) || {};
      const next = {
        ...current,
        email_auto_enabled: body.email_auto_enabled,
        atualizado_em: new Date().toISOString(),
      };
      await env.SENTINELA_KV.put("settings", JSON.stringify(next));
      return jsonResponse(next);
    }

    if (action === "lookup_cnpj") {
      const digits = (url.searchParams.get("cnpj") || "").replace(/\D/g, "");
      if (digits.length !== 14) {
        return jsonResponse({ error: "CNPJ deve ter 14 dígitos." }, 400);
      }
      const res = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${digits}`, {
        headers: { "User-Agent": "SentinelaDiario/1.0" },
      });
      if (!res.ok) {
        return jsonResponse({ error: "Não foi possível consultar o CNPJ na BrasilAPI." }, 502);
      }
      const data = await res.json();
      return jsonResponse(data);
    }

    if (action === "list_leads") {
      const subscribers = (await env.SENTINELA_KV.get("subscribers", { type: "json" })) || [];
      return jsonResponse({ total: subscribers.length, subscribers });
    }

    if (action === "register_lead" && request.method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body || !body.empresa || !body.nome || !body.contato) {
        return jsonResponse({ error: "Preencha empresa/CNPJ, nome e contato." }, 400);
      }
      const subscribers = (await env.SENTINELA_KV.get("subscribers", { type: "json" })) || [];
      const now = new Date();
      const expires = new Date(now.getTime() + 15 * 24 * 60 * 60 * 1000);
      const contato = String(body.contato).trim();
      const emailMatch = contato.match(/[^\s@]+@[^\s@]+\.[^\s@]+/);
      const lead = {
        id: crypto.randomUUID(),
        empresa: String(body.empresa).trim(),
        empresa_upper: String(body.empresa).trim().toUpperCase(),
        cnpj_digits: String(body.empresa).replace(/\D/g, ""),
        nome: String(body.nome).trim(),
        contato,
        email_contato: emailMatch ? emailMatch[0] : null,
        ativo: true,
        criado_em: now.toISOString(),
        expira_em: expires.toISOString(),
      };
      subscribers.push(lead);
      await env.SENTINELA_KV.put("subscribers", JSON.stringify(subscribers));

      if (env.RESEND_API_KEY) {
        await sendViaResend(env.RESEND_API_KEY, {
          to: "renatodelta@gmail.com",
          subject: `Novo interessado no Sentinela Diário: ${shortCompanyName(lead.empresa, 40)}`,
          text: `Novo cadastro para teste grátis de 15 dias:\n\n• Empresa/CNPJ: ${lead.empresa}\n• Nome: ${lead.nome}\n• Contato: ${lead.contato}`,
          html: `<p><strong>Novo cadastro para teste grátis de 15 dias:</strong></p><ul><li><strong>Empresa/CNPJ:</strong> ${lead.empresa}</li><li><strong>Nome:</strong> ${lead.nome}</li><li><strong>Contato:</strong> ${lead.contato}</li></ul>`,
        }).catch(() => {});
      }

      return jsonResponse({ ok: true, lead });
    }

    if (action === "send_email" && request.method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body || !body.to || !body.subject || (!body.html && !body.text)) {
        return jsonResponse({ error: "Campos obrigatórios: to, subject e (html ou text)." }, 400);
      }
      if (body.dry_run) {
        return jsonResponse({ ok: true, dry_run: true, to: body.to, subject: body.subject });
      }
      if (!env.RESEND_API_KEY) {
        return jsonResponse({ error: "RESEND_API_KEY não configurada no Worker." }, 500);
      }
      const result = await sendViaResend(env.RESEND_API_KEY, body);
      return jsonResponse(result.data, result.status);
    }

    if (action === "sync_and_send" && request.method === "POST") {
      if (env.SYNC_SECRET) {
        const provided = request.headers.get("X-Sync-Secret");
        if (provided !== env.SYNC_SECRET) {
          return jsonResponse({ error: "Não autorizado." }, 401);
        }
      }
      const body = await request.json().catch(() => null);
      if (!body || !Array.isArray(body.ocorrencias)) {
        return jsonResponse({ error: "Payload inválido." }, 400);
      }

      const existing =
        (await env.SENTINELA_KV.get("ocorrencias_store", { type: "json" })) || {
          ocorrencias: [],
          arquivos_analisados: [],
        };
      const byId = new Map((existing.ocorrencias || []).map((o) => [o.id, o]));
      for (const occ of body.ocorrencias) {
        if (occ.id && !byId.has(occ.id)) {
          byId.set(occ.id, occ);
        }
      }

      const merged = Array.from(byId.values());
      const settings = (await env.SENTINELA_KV.get("settings", { type: "json" })) || {};
      const autoEnabled = Boolean(settings.email_auto_enabled);
      const sentLog = (await env.SENTINELA_KV.get("sent_emails", { type: "json" })) || {};
      const subscribers = (await env.SENTINELA_KV.get("subscribers", { type: "json" })) || [];

      let sentCount = 0;
      const errors = [];

      if (autoEnabled && env.RESEND_API_KEY) {
        for (const occ of merged) {
          if (occ.status && occ.status !== "pendente") continue;
          if (occ.prioridade === "descartar") continue;

          const subscriber = findMatchingSubscriber(occ, subscribers);
          const empresaCurta = shortCompanyName(occ.empresa);

          if (subscriber && subscriber.email_contato) {
            const alertKey = `sub:${subscriber.id}:${occ.id}`;
            if (sentLog[alertKey]) continue;

            const subject = `[Alerta Sentinela] Nova publicação de ${empresaCurta} no Diário Oficial de SJC`;
            const text =
              `Olá, ${subscriber.nome}!\n\n` +
              `Identificamos uma nova publicação envolvendo ${occ.empresa} no Diário Oficial de São José dos Campos (Edição nº ${occ.edicao || "-"}, ${occ.data_publicacao || "-"}, página ${occ.pagina || "-"}):\n\n` +
              `• Ato: ${occ.tipo_ato || "-"}\n` +
              `• Objeto: ${occ.objeto || "-"}\n` +
              (occ.valor ? `• Valor: ${occ.valor}\n` : "") +
              `\nQualquer dúvida, estamos à disposição.`;
            const html = text
              .split("\n")
              .map((line) => `<p style="margin:0 0 8px 0;">${line}</p>`)
              .join("");

            const res = await sendViaResend(env.RESEND_API_KEY, {
              to: subscriber.email_contato,
              subject,
              text,
              html,
            });
            if (res.ok) {
              if (!TEST_REDIRECT_EMAIL) {
                sentLog[alertKey] = { id: res.data.id || null, sent_at: new Date().toISOString(), occ_id: occ.id };
                occ.status = "enviado";
              }
              sentCount++;
              const maxPerRun = TEST_REDIRECT_EMAIL ? 3 : 50;
              if (sentCount >= maxPerRun) break;
            } else {
              errors.push({ to: subscriber.email_contato, status: res.status, error: res.data });
            }
            continue;
          }

          const to = extractRecipientEmail(occ);
          if (!to || sentLog[to]) continue;

          const subject = `Aviso de publicação no Diário Oficial de SJC — ${empresaCurta}`;
          const text = occ.texto_email || occ.corpo_email || "";
          if (!text) continue;
          const html = text
            .split("\n")
            .map((line) => `<p style="margin:0 0 8px 0;">${line}</p>`)
            .join("");

          const res = await sendViaResend(env.RESEND_API_KEY, {
            to,
            subject,
            text,
            html,
          });
          if (res.ok) {
            if (!TEST_REDIRECT_EMAIL) {
              sentLog[to] = { id: res.data.id || null, sent_at: new Date().toISOString(), occ_id: occ.id };
              occ.status = "enviado";
            }
            sentCount++;
            const maxPerRun = TEST_REDIRECT_EMAIL ? 3 : 50;
            if (sentCount >= maxPerRun) break;
          } else {
            errors.push({ to, status: res.status, error: res.data });
          }
        }
        await env.SENTINELA_KV.put("sent_emails", JSON.stringify(sentLog));
      }

      const updatedStore = {
        gerado_em: body.gerado_em || new Date().toISOString(),
        atualizado_em: new Date().toISOString(),
        total: merged.length,
        arquivos_analisados: Array.from(
          new Set([...(existing.arquivos_analisados || []), ...(body.arquivos_analisados || [])])
        ),
        ocorrencias: merged,
      };
      await env.SENTINELA_KV.put("ocorrencias_store", JSON.stringify(updatedStore));

      return jsonResponse({
        ok: true,
        total: merged.length,
        email_auto_enabled: autoEnabled,
        emails_enviados: sentCount,
        errors,
      });
    }

    return jsonResponse({ error: "Ação desconhecida." }, 404);
  },
};
