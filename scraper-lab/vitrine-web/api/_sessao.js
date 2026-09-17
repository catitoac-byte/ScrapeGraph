// Sessao assinada com HMAC (Web Crypto), usada pelo login, pelo middleware e por /api/eu.
// O token leva o usuario e as verticais liberadas para ele, entao o middleware
// decide o acesso sem consultar nada.
const enc = new TextEncoder();

async function chave(segredo) {
  return crypto.subtle.importKey("raw", enc.encode(segredo), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const b64 = (s) => btoa(unescape(encodeURIComponent(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const de64 = (s) => decodeURIComponent(escape(atob(s.replace(/-/g, "+").replace(/_/g, "/"))));

export async function assinar(usuario, verticais, validadeSeg, segredo) {
  const exp = Math.floor(Date.now() / 1000) + validadeSeg;
  const corpo = b64(JSON.stringify({ u: usuario, v: verticais, exp }));
  const sig = hex(await crypto.subtle.sign("HMAC", await chave(segredo), enc.encode(corpo)));
  return `${corpo}.${sig}`;
}

// Devolve {u, v, exp} ou null
export async function validar(token, segredo) {
  if (!token || !segredo) return null;
  const partes = token.split(".");
  if (partes.length !== 2) return null;
  const [corpo, sig] = partes;
  const esperado = hex(await crypto.subtle.sign("HMAC", await chave(segredo), enc.encode(corpo)));
  if (esperado.length !== sig.length) return null;
  let dif = 0;
  for (let i = 0; i < sig.length; i++) dif |= esperado.charCodeAt(i) ^ sig.charCodeAt(i);
  if (dif !== 0) return null;
  let dados;
  try { dados = JSON.parse(de64(corpo)); } catch { return null; }
  if (!dados || typeof dados.exp !== "number" || dados.exp < Date.now() / 1000) return null;
  return dados;
}

export function libera(sessao, vertical) {
  return !!sessao && Array.isArray(sessao.v) && (sessao.v.includes("*") || sessao.v.includes(vertical));
}

export function lerCookie(req, nome) {
  const c = req.headers.get("cookie") || "";
  const m = c.match(new RegExp(`(?:^|;\\s*)${nome}=([^;]+)`));
  return m ? decodeURIComponent(m[1]) : "";
}

export const COOKIE = "rival_sessao";
