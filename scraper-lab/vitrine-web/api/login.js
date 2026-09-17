import { scryptSync, timingSafeEqual } from "node:crypto";
import { assinar, COOKIE } from "./_sessao.js";

// Credenciais so por variavel de ambiente:
// RIVAL_USUARIOS = {"usuario": {"h": "salt:hex do scrypt", "v": ["moda", ...] ou ["*"]}}
// RIVAL_SEGREDO  = chave do HMAC da sessao
// Mantidos por vitrine-web/usuarios.py.
const SETE_DIAS = 7 * 24 * 3600;

function confere(senha, guardado) {
  const [salt, hash] = (guardado || "").split(":");
  if (!salt || !hash) return false;
  const calc = scryptSync(senha, salt, 32);
  const alvo = Buffer.from(hash, "hex");
  return alvo.length === calc.length && timingSafeEqual(alvo, calc);
}

function usuarios() {
  try { return JSON.parse(process.env.RIVAL_USUARIOS || "{}"); } catch { return {}; }
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
  const conta = Object.prototype.hasOwnProperty.call(usuarios(), usuario) ? usuarios()[usuario] : null;
  const verticais = Array.isArray(conta?.v) ? conta.v : [];
  if (!conta || !verticais.length || !confere(senha, conta.h)) {
    // Atraso fixo para dificultar tentativa em massa
    await new Promise((r) => setTimeout(r, 900));
    return volta(req, "/?erro=1#entrar");
  }
  const token = await assinar(usuario, verticais, SETE_DIAS, process.env.RIVAL_SEGREDO);
  const destino = verticais.length === 1 && verticais[0] !== "*" ? `/v/${verticais[0]}` : "/painel";
  return volta(req, destino, `${COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SETE_DIAS}`);
}

export function GET(req) {
  return volta(req, "/#entrar");
}
