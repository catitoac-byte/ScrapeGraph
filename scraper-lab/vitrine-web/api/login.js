import { scryptSync, timingSafeEqual } from "node:crypto";
import { assinar, COOKIE } from "./_sessao.js";

// Credenciais so por variavel de ambiente:
// VITRINE_USUARIO, VITRINE_SENHA_HASH ("salt:hex" do scrypt), VITRINE_SEGREDO
const SETE_DIAS = 7 * 24 * 3600;

function confere(senha, guardado) {
  const [salt, hash] = (guardado || "").split(":");
  if (!salt || !hash) return false;
  const calc = scryptSync(senha, salt, 32);
  const alvo = Buffer.from(hash, "hex");
  return alvo.length === calc.length && timingSafeEqual(alvo, calc);
}

function volta(req, destino, cookie) {
  const url = new URL(destino, req.url);
  const headers = { Location: url.toString(), "Cache-Control": "no-store" };
  if (cookie) headers["Set-Cookie"] = cookie;
  return new Response(null, { status: 303, headers });
}

export async function POST(req) {
  const form = await req.formData().catch(() => null);
  const usuario = String(form?.get("usuario") || "").trim().toLowerCase();
  // Copiar e colar costuma trazer espaco no fim; a senha gerada nunca tem espaco
  const senha = String(form?.get("senha") || "").trim();
  const ok =
    usuario === String(process.env.VITRINE_USUARIO || "").toLowerCase() &&
    confere(senha, process.env.VITRINE_SENHA_HASH);
  if (!ok) {
    // Atraso fixo para dificultar tentativa em massa
    await new Promise((r) => setTimeout(r, 900));
    return volta(req, "/?erro=1#entrar");
  }
  const token = await assinar(usuario, SETE_DIAS, process.env.VITRINE_SEGREDO);
  return volta(req, "/painel", `${COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SETE_DIAS}`);
}

export function GET(req) {
  return volta(req, "/#entrar");
}
