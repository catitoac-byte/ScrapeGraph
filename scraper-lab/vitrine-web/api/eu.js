import { validar, lerCookie, COOKIE } from "./_sessao.js";

// Quem esta logado e quais verticais pode abrir (a pagina de escolha e o painel usam)
export async function GET(req) {
  const s = await validar(lerCookie(req, COOKIE), process.env.RIVAL_SEGREDO);
  const headers = { "Content-Type": "application/json", "Cache-Control": "private, no-store" };
  if (!s) return new Response(JSON.stringify({ ok: false }), { status: 401, headers });
  return new Response(JSON.stringify({ ok: true, usuario: s.u, verticais: s.v }), { headers });
}
