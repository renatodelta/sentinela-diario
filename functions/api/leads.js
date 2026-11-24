const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json; charset=utf-8',
};

const LEADS_KEY = 'leads_list';

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: CORS_HEADERS });
}

function extractCnpj(text) {
  const m = String(text || '').match(/\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}/);
  if (!m) return '';
  const digits = m[0].replace(/\D/g, '');
  if (digits.length !== 14) return '';
  return digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
}

async function readLeads(kv) {
  if (!kv) return [];
  const raw = await kv.get(LEADS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeLeads(kv, leads) {
  await kv.put(LEADS_KEY, JSON.stringify(leads));
}

async function notifyNewLead(env, lead) {
  const apiKey = env.RESEND_API_KEY;
  if (!apiKey) return;
  try {
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: 'Sentinela Diário <contato@sentineladiario.com>',
        to: ['renatodelta@gmail.com'],
        subject: `Novo cadastro no site: ${lead.empresa}`,
        text:
          `Nova empresa solicitou teste grátis de 15 dias em sentineladiario.com:\n\n` +
          `• Empresa / CNPJ: ${lead.empresa}\n` +
          `• CNPJ identificado: ${lead.cnpj || 'Não informado'}\n` +
          `• Responsável: ${lead.nome}\n` +
          `• Contato (WhatsApp / E-mail): ${lead.contato}\n` +
          `• Cidade / Diário de interesse: ${lead.regiao || 'São José dos Campos - SP'}\n` +
          `• Data: ${lead.criado_em}\n\n` +
          `Acesse o painel: https://sentineladiario.com/painel.html`,
      }),
    });
  } catch {
    // Não falha o cadastro se o aviso por e-mail falhar
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

export async function onRequestGet({ env }) {
  if (!env.SENTINELA_LEADS) {
    return jsonResponse(
      { error: 'KV namespace SENTINELA_LEADS não vinculado no Cloudflare Pages.', leads: [] },
      500
    );
  }
  const leads = await readLeads(env.SENTINELA_LEADS);
  return jsonResponse({ leads, total: leads.length });
}

export async function onRequestPost({ request, env }) {
  if (!env.SENTINELA_LEADS) {
    return jsonResponse(
      { error: 'KV namespace SENTINELA_LEADS não vinculado no Cloudflare Pages.' },
      500
    );
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'JSON inválido.' }, 400);
  }

  const empresa = String(body.empresa || '').trim();
  const nome = String(body.nome || '').trim();
  const contato = String(body.contato || '').trim();
  const regiao = String(body.regiao || 'São José dos Campos - SP').trim();

  if (!empresa || !nome || !contato) {
    return jsonResponse({ error: 'Preencha empresa/CNPJ, nome e contato.' }, 400);
  }

  const cnpj = extractCnpj(body.cnpj || empresa);
  const lead = {
    id: crypto.randomUUID().slice(0, 12),
    empresa,
    cnpj,
    nome,
    contato,
    regiao,
    status: body.status || 'ativo',
    origem: body.origem || 'landing_page',
    notas: String(body.notas || '').trim(),
    criado_em: new Date().toISOString(),
  };

  const leads = await readLeads(env.SENTINELA_LEADS);
  leads.unshift(lead);
  await writeLeads(env.SENTINELA_LEADS, leads);

  if (lead.origem === 'landing_page') {
    await notifyNewLead(env, lead);
  }

  return jsonResponse({ ok: true, lead }, 201);
}

export async function onRequestPatch({ request, env }) {
  if (!env.SENTINELA_LEADS) {
    return jsonResponse({ error: 'KV namespace SENTINELA_LEADS não vinculado.' }, 500);
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'JSON inválido.' }, 400);
  }

  const id = String(body.id || '').trim();
  if (!id) return jsonResponse({ error: 'ID obrigatório.' }, 400);

  const leads = await readLeads(env.SENTINELA_LEADS);
  const idx = leads.findIndex((l) => l.id === id);
  if (idx === -1) return jsonResponse({ error: 'Cadastro não encontrado.' }, 404);

  if (body.status !== undefined) leads[idx].status = String(body.status);
  if (body.notas !== undefined) leads[idx].notas = String(body.notas);
  if (body.cnpj !== undefined) leads[idx].cnpj = extractCnpj(body.cnpj) || String(body.cnpj).trim();
  leads[idx].atualizado_em = new Date().toISOString();

  await writeLeads(env.SENTINELA_LEADS, leads);
  return jsonResponse({ ok: true, lead: leads[idx] });
}

export async function onRequestDelete({ request, env }) {
  if (!env.SENTINELA_LEADS) {
    return jsonResponse({ error: 'KV namespace SENTINELA_LEADS não vinculado.' }, 500);
  }
  const url = new URL(request.url);
  const id = url.searchParams.get('id');
  if (!id) return jsonResponse({ error: 'ID obrigatório.' }, 400);

  const leads = await readLeads(env.SENTINELA_LEADS);
  const filtered = leads.filter((l) => l.id !== id);
  await writeLeads(env.SENTINELA_LEADS, filtered);
  return jsonResponse({ ok: true, total: filtered.length });
}
