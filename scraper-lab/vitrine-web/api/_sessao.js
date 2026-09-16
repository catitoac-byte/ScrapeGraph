// Sessao assinada com HMAC (Web Crypto), usada pelo login e pelo middleware.
const enc = new TextEncoder();

async function chave(segredo) {
  return crypto.subtle.importKey("raw", enc.encode(segredo), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function assinar(usuario, validadeSeg, segredo) {
  const exp = Math.floor(Date.now() / 1000) + validadeSeg;
  const corpo = `${encodeURIComponent(usuario)}.${exp}`;
  const sig = hex(await crypto.subtle.sign("HMAC", await chave(segredo), enc.encode(corpo)));
  return `${corpo}.${sig}`;
}

export async function validar(token, segredo) {
  if (!token || !segredo) return false;
  const partes = token.split(".");
  if (partes.length !== 3) return false;
  const [usuario, exp, sig] = partes;
  if (!/^\d+$/.test(exp) || Number(exp) < Date.now() / 1000) return false;
  const esperado = hex(await crypto.subtle.sign("HMAC", await chave(segredo), enc.encode(`${usuario}.${exp}`)));
  if (esperado.length !== sig.length) return false;
  let dif = 0;
  for (let i = 0; i < sig.length; i++) dif |= esperado.charCodeAt(i) ^ sig.charCodeAt(i);
  return dif === 0;
}

export function lerCookie(req, nome) {
  const c = req.headers.get("cookie") || "";
  const m = c.match(new RegExp(`(?:^|;\\s*)${nome}=([^;]+)`));
  return m ? decodeURIComponent(m[1]) : "";
}

export const COOKIE = "vitrine_sessao";
