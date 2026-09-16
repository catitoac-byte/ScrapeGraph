import { COOKIE } from "./_sessao.js";

export function GET(req) {
  return new Response(null, {
    status: 303,
    headers: {
      Location: new URL("/", req.url).toString(),
      "Set-Cookie": `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`,
      "Cache-Control": "no-store",
    },
  });
}
