const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json; charset=utf-8',
};

const COPY_EMAIL = 'renatodelta@gmail.com';
const DEFAULT_FROM = 'Sentinela Diário <contato@sentineladiario.com>';

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
  '\n\n--\nRenato\nMonitoramento Inteligente de CNPJ & Diários Oficiais\nWhatsApp: (12) 99153-0244 | https://sentineladiario.com/';

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: CORS_HEADERS });
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

export async function onRequestPost({ request, env }) {
  const apiKey = env.RESEND_API_KEY;
  if (!apiKey) {
    return jsonResponse({ error: 'RESEND_API_KEY não configurada no Cloudflare Pages.' }, 500);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'JSON inválido.' }, 400);
  }

  const toList = Array.isArray(body.to) ? body.to : body.to ? [body.to] : [];
  const subject = String(body.subject || '').trim();
  const text = String(body.text || '').trim();
  const html = String(body.html || '').trim();

  if (!toList.length || !subject || (!text && !html)) {
    return jsonResponse({ error: 'Campos obrigatórios: to, subject e (html ou text).' }, 400);
  }

  const payload = {
    from: body.from ? String(body.from) : DEFAULT_FROM,
    to: toList,
    reply_to: COPY_EMAIL,
    subject,
  };
  if (!toList.some((e) => String(e).toLowerCase() === COPY_EMAIL.toLowerCase())) {
    payload.bcc = [COPY_EMAIL];
  }
  if (html) payload.html = html + SIGNATURE_HTML;
  if (text) payload.text = text + SIGNATURE_TEXT;

  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const respText = await res.text();
  let respJson;
  try {
    respJson = JSON.parse(respText);
  } catch {
    respJson = { raw: respText };
  }

  if (!res.ok) {
    return jsonResponse(
      { error: respJson?.message || respJson?.error || `Erro Resend HTTP ${res.status}`, detail: respJson },
      res.status
    );
  }

  return jsonResponse(respJson, 200);
}
