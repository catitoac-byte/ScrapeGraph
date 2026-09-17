// Pedido de contato da pagina de entrada.
// Envia por e-mail via Resend quando RESEND_API_KEY existe.
// CONTATO_PARA (padrao cassiano@cassiai.com) e CONTATO_DE (remetente verificado no Resend).
const LIMITE = { nome: 120, empresa: 160, email: 160, telefone: 40, vertical: 80, idioma: 5 };

// Troca caracteres de controle por espaco (a mensagem mantem quebras de linha)
function limpa(v, n, linhas = false) {
  const s = String(v || "");
  let out = "";
  for (const ch of s) {
    const c = ch.charCodeAt(0);
    const controle = c < 32 || c === 127;
    out += controle && !(linhas && (c === 10 || c === 13)) ? " " : ch;
  }
  return out.trim().slice(0, n);
}

function json(corpo, status = 200) {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

export async function POST(req) {
  const d = await req.json().catch(() => null);
  if (!d) return json({ ok: false, erro: "formato" }, 400);
  // Campo escondido: robo costuma preencher
  if (d.site) return json({ ok: true });
  const c = Object.fromEntries(Object.entries(LIMITE).map(([k, n]) => [k, limpa(d[k], n)]));
  c.mensagem = limpa(d.mensagem, 2000, true);
  if (!c.nome || !c.vertical || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(c.email)) return json({ ok: false, erro: "campos" }, 422);

  const chave = process.env.RESEND_API_KEY;
  if (!chave) return json({ ok: false, erro: "sem_envio" }, 503);

  const texto = [
    `Nome: ${c.nome}`,
    `Empresa: ${c.empresa || "-"}`,
    `E-mail: ${c.email}`,
    `Telefone: ${c.telefone || "-"}`,
    `Vertical: ${c.vertical}`,
    `Idioma da pagina: ${c.idioma || "-"}`,
    "",
    c.mensagem || "(sem mensagem)",
  ].join("\n");
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${chave}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: process.env.CONTATO_DE || "Rival Pulse <onboarding@resend.dev>",
      to: [process.env.CONTATO_PARA || "cassiano@cassiai.com"],
      reply_to: c.email,
      subject: `Rival Pulse · pedido de acesso · ${c.vertical} · ${c.nome}`,
      text: texto,
    }),
  }).catch(() => null);
  if (!r || !r.ok) return json({ ok: false, erro: "envio" }, 502);
  return json({ ok: true });
}
