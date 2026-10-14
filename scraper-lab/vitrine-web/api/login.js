import { scryptSync, timingSafeEqual, createHmac } from "node:crypto";
import { assinar, COOKIE } from "./_sessao.js";

// Credenciais so por variavel de ambiente:
// RIVAL_USUARIOS = {"usuario": {"h": "salt:hex do scrypt", "v": ["moda", ...] ou ["*"]}}
// RIVAL_SEGREDO  = chave do HMAC da sessao (e do cookie de falhas, abaixo)
// Mantidos por vitrine-web/usuarios.py.
const SETE_DIAS = 7 * 24 * 3600;

// Limite de tentativas: 5 falhas em 15 minutos, por navegador, por IP e por usuario.
// Dispara o que estourar primeiro.
//
// Como cada funcao da Vercel roda em instancias separadas, sem memoria compartilhada,
// o contador vive em dois lugares:
//   1. cookie assinado (HMAC com RIVAL_SEGREDO), HttpOnly, so enviado a /api/login:
//      vale por navegador e funciona em qualquer instancia. Quem apaga o cookie
//      zera o proprio contador, por isso existe a segunda camada.
//   2. Map em memoria por IP e por usuario: vale so dentro da instancia que atendeu
//      o pedido. Entre instancias, ou depois de uma instancia dormir, o contador
//      recomeca. E o melhor esforco possivel sem um armazenamento externo (KV, Redis).
// O atraso fixo de 900 ms em cada falha continua valendo por cima disso.
const FALHAS_MAX = 5;
const JANELA_SEG = 15 * 60;
const COOKIE_FALHAS = "rival_falhas";
const memoria = new Map(); // chave "ip:<ip>" ou "u:<usuario>" -> {n, t}

function agora() { return Math.floor(Date.now() / 1000); }

function ipDe(req) {
  const xff = req.headers.get("x-forwarded-for") || "";
  const primeiro = xff.split(",")[0].trim();
  return primeiro || (req.headers.get("x-real-ip") || "").trim() || "desconhecido";
}

function hmac(corpo, segredo) {
  return createHmac("sha256", segredo).update(corpo).digest("hex");
}

// Cookie: base64url({n, t}) + "." + hmac. {n: falhas na janela, t: inicio da janela em segundos}
function lerFalhasCookie(req, segredo) {
  if (!segredo) return { n: 0, t: agora() };
  const c = req.headers.get("cookie") || "";
  const m = c.match(new RegExp(`(?:^|;\\s*)${COOKIE_FALHAS}=([^;]+)`));
  if (!m) return { n: 0, t: agora() };
  const [corpo, sig] = decodeURIComponent(m[1]).split(".");
  if (!corpo || !sig) return { n: 0, t: agora() };
  const esperado = hmac(corpo, segredo);
  const a = Buffer.from(esperado), b = Buffer.from(sig);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return { n: 0, t: agora() };
  let dados;
  try { dados = JSON.parse(Buffer.from(corpo, "base64url").toString("utf8")); } catch { return { n: 0, t: agora() }; }
  if (typeof dados?.n !== "number" || typeof dados?.t !== "number") return { n: 0, t: agora() };
  return dentroDaJanela(dados);
}

function cookieFalhas(dados, segredo) {
  if (!segredo) return null;
  const corpo = Buffer.from(JSON.stringify({ n: dados.n, t: dados.t })).toString("base64url");
  const valor = encodeURIComponent(`${corpo}.${hmac(corpo, segredo)}`);
  return `${COOKIE_FALHAS}=${valor}; Path=/api/login; HttpOnly; Secure; SameSite=Lax; Max-Age=${JANELA_SEG}`;
}

function limpaCookieFalhas() {
  return `${COOKIE_FALHAS}=; Path=/api/login; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

// Janela fixa: passado o prazo desde a primeira falha, o contador recomeca do zero.
function dentroDaJanela(dados) {
  if (!dados || agora() - dados.t >= JANELA_SEG) return { n: 0, t: agora() };
  return dados;
}

function lerMemoria(chave) {
  const dados = dentroDaJanela(memoria.get(chave));
  if (memoria.size > 5000) {
    for (const [k, v] of memoria) if (agora() - v.t >= JANELA_SEG) memoria.delete(k);
  }
  return dados;
}

function registrarFalha(chave) {
  const dados = lerMemoria(chave);
  memoria.set(chave, { n: dados.n + 1, t: dados.t });
}

function estourou(dados) { return dados.n >= FALHAS_MAX; }

function segundosRestantes(...varios) {
  return Math.max(1, ...varios.map((d) => d.t + JANELA_SEG - agora()));
}

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

function volta(req, destino, cookies) {
  const url = new URL(destino, req.url);
  const headers = new Headers({ Location: url.toString(), "Cache-Control": "no-store" });
  for (const c of [].concat(cookies || [])) if (c) headers.append("Set-Cookie", c);
  return new Response(null, { status: 303, headers });
}

// 429 nao e seguido como redirecionamento pelo navegador, entao a pagina de volta
// vai no corpo (meta refresh) e leva ao mesmo aviso da janela de login, com ?erro=limite.
function limite(req, segundos, cookie) {
  const url = new URL("/?erro=limite#entrar", req.url).toString();
  const headers = new Headers({
    "Retry-After": String(segundos),
    "Cache-Control": "no-store",
    "Content-Type": "text/html; charset=utf-8",
  });
  if (cookie) headers.append("Set-Cookie", cookie);
  const corpo = `<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=${url}"><title>429</title><a href="${url}">Continuar</a>`;
  return new Response(corpo, { status: 429, headers });
}

export async function POST(req) {
  const form = await req.formData().catch(() => null);
  const usuario = String(form?.get("usuario") || "").trim().toLowerCase();
  // Copiar e colar costuma trazer espaco no fim; a senha gerada nunca tem espaco
  const senha = String(form?.get("senha") || "").trim();
  const segredo = process.env.RIVAL_SEGREDO;

  const ip = ipDe(req);
  const chaveIp = `ip:${ip}`;
  const chaveUsuario = usuario ? `u:${usuario}` : null;
  const porNavegador = lerFalhasCookie(req, segredo);
  const porIp = lerMemoria(chaveIp);
  const porUsuario = chaveUsuario ? lerMemoria(chaveUsuario) : { n: 0, t: agora() };

  if (estourou(porNavegador) || estourou(porIp) || estourou(porUsuario)) {
    const bloqueados = [porNavegador, porIp, porUsuario].filter(estourou);
    return limite(req, segundosRestantes(...bloqueados), cookieFalhas(porNavegador, segredo));
  }

  const conta = Object.prototype.hasOwnProperty.call(usuarios(), usuario) ? usuarios()[usuario] : null;
  const verticais = Array.isArray(conta?.v) ? conta.v : [];
  if (!conta || !verticais.length || !confere(senha, conta.h)) {
    registrarFalha(chaveIp);
    if (chaveUsuario) registrarFalha(chaveUsuario);
    const falhas = { n: porNavegador.n + 1, t: porNavegador.t };
    // Atraso fixo para dificultar tentativa em massa
    await new Promise((r) => setTimeout(r, 900));
    return volta(req, "/?erro=1#entrar", cookieFalhas(falhas, segredo));
  }

  // Acerto zera os contadores do navegador, do IP e do usuario
  memoria.delete(chaveIp);
  if (chaveUsuario) memoria.delete(chaveUsuario);
  const token = await assinar(usuario, verticais, SETE_DIAS, segredo);
  const destino = verticais.length === 1 && verticais[0] !== "*" ? `/v/${verticais[0]}` : "/painel";
  return volta(req, destino, [
    `${COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SETE_DIAS}`,
    limpaCookieFalhas(),
  ]);
}

export function GET(req) {
  return volta(req, "/#entrar");
}
