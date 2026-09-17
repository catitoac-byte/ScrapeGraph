import { next } from "@vercel/functions";
import { validar, libera, lerCookie, COOKIE } from "./api/_sessao.js";

// /painel e a escolha de vertical; /v/<id>/ e o painel de cada vertical (pagina e data.js).
// Cada usuario so abre as verticais que estao na sessao dele.
export const config = { matcher: ["/painel", "/painel/:path*", "/v/:path*"] };

export default async function middleware(req) {
  const sessao = await validar(lerCookie(req, COOKIE), process.env.RIVAL_SEGREDO);
  if (!sessao) return Response.redirect(new URL("/?entrar=1#entrar", req.url), 307);
  const m = new URL(req.url).pathname.match(/^\/v\/([a-z0-9-]+)/);
  if (m && !libera(sessao, m[1])) return Response.redirect(new URL("/painel?sem=1", req.url), 307);
  return next();
}
