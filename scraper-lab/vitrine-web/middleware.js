import { next } from "@vercel/functions";
import { validar, lerCookie, COOKIE } from "./api/_sessao.js";

// Tudo em /painel (pagina e data.js) exige sessao valida
export const config = { matcher: ["/painel", "/painel/:path*"] };

export default async function middleware(req) {
  const ok = await validar(lerCookie(req, COOKIE), process.env.VITRINE_SEGREDO);
  if (ok) return next();
  return Response.redirect(new URL("/?entrar=1#entrar", req.url), 307);
}
