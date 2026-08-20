// Cloudflare Worker — Nesine botu Telegram komutlari.
//
// /kupon   -> uc risk seviyesinde kupon uretimini tetikler (GitHub Actions)
// /kupon0  -> canli maclar HARIC
// /durum   -> aylik ciro ve son oneriyi ANINDA okur (workflow beklemez)
// /yardim  -> komut listesi
//
// Neden Actions: mac oncesi bulten 8,5 MB. Worker ucretsiz katmani 10 ms CPU
// veriyor; bu boyutta JSON'u parse edemez. Canli bulten 43 KB ama tek basina
// yeterli degil. Bu yuzden hesap Actions'ta yapilir (~40-60 sn).
//
// Gereken Worker secrets: GH_TOKEN, TG_BOT_TOKEN, CHAT_ID
const OWNER = "uurcantnt";
const REPO  = "nesine-bot";
const WF    = "kupon.yml";

async function tg(env, text) {
  await fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.CHAT_ID, text, disable_web_page_preview: true }),
  });
}

async function ghJSON(env, path) {
  const r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`, {
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json",
               "User-Agent": "nesine-bot-worker" },
  });
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const j = await r.json();
  return JSON.parse(decodeURIComponent(escape(atob(j.content.replace(/\n/g, "")))));
}

// Dispatch — basarisizlikta SEBEBI dondurur. Sessiz hata YASAK:
// kripto botunda tum worker hatalari sessizdi ve "K/Z hep 0" diye
// fark edilene kadar gunlerce yanlis calisti.
async function dispatch(env, canli) {
  if (!env.GH_TOKEN) return { ok: false, hata: "GH_TOKEN secret'i TANIMSIZ (isim yanlis olabilir)" };
  let r;
  try {
    r = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WF}/dispatches`, {
        method: "POST",
        headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json",
                   "User-Agent": "nesine-bot-worker", "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "main", inputs: { canli } }),
      });
  } catch (e) {
    return { ok: false, hata: `aga cikilamadi: ${e.message}` };
  }
  if (r.status === 204) return { ok: true };
  let govde = "";
  try { govde = (await r.text()).slice(0, 200); } catch (e) {}
  const ipucu = r.status === 403 ? " -> token bu repoda Actions:Read+write yetkisine sahip degil"
              : r.status === 401 ? " -> token gecersiz/suresi dolmus"
              : r.status === 404 ? " -> repo veya workflow adi yanlis"
              : "";
  return { ok: false, hata: `GitHub HTTP ${r.status}${ipucu}\n${govde}` };
}

async function durum(env) {
  let st = null, son = null;
  try { st = await ghJSON(env, "data/state.json"); } catch (e) {}
  const L = ["NESINE · durum"];
  if (st) {
    L.push(`Ay: ${st.ay}`);
    L.push(`Aylik ciro: ${st.ay_ciro} TL`);
    L.push(`Bu ay gonderim: ${st.gonderim}`);
    L.push(`Son oneri gunu: ${st.son_gun || "-"}`);
  } else {
    L.push("Henuz durum dosyasi yok (ilk oneri gonderilmedi).");
  }
  L.push("");
  L.push("Hatirlatma: bu bot kazandirmaz. Nesine marji %21,1;");
  L.push("tek bahiste beklenen deger -%17,4, 3 macli kuponda -%43,6.");
  return L.join("\n");
}

const YARDIM = [
  "NESINE bot komutlari:",
  "",
  "/kupon   3 risk seviyesinde kupon uret (canli dahil)",
  "/kupon0  ayni, canli maclar HARIC",
  "/durum   aylik ciro + son oneri",
  "/tani    worker secret tanilama",
  "/yardim  bu liste",
  "",
  "Bot bahis OYNAMAZ. Kuponu sen elinle oynarsin.",
  "Her onerinin beklenen degeri mesajda yazilidir ve NEGATIFTIR.",
].join("\n");

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    let u;
    try { u = await request.json(); } catch (e) { return new Response("ok"); }
    const text = ((u.message && u.message.text) || "").trim().toLowerCase();
    if (!text) return new Response("ok");

    if (text.startsWith("/kupon")) {
      const canli = text.startsWith("/kupon0") ? "0" : "1";
      const r = await dispatch(env, canli);
      await tg(env, r.ok
        ? `Kupon hesaplaniyor${canli === "0" ? " (canli haric)" : ""}... ~1 dk icinde gelecek.`
        : `TETIKLENEMEDI\n${r.hata}`);
    } else if (text.startsWith("/durum")) {
      await tg(env, await durum(env));
    } else if (text.startsWith("/tani")) {
      const v = (x) => (x ? `var (${String(x).length} karakter)` : "YOK");
      await tg(env, ["Worker tanilama:",
        `GH_TOKEN     : ${v(env.GH_TOKEN)}`,
        `TG_BOT_TOKEN : ${v(env.TG_BOT_TOKEN)}`,
        `CHAT_ID      : ${v(env.CHAT_ID)}`,
        `GH_TOKEN ilk 11: ${env.GH_TOKEN ? String(env.GH_TOKEN).slice(0, 11) : "-"}`,
        `repo: ${OWNER}/${REPO} · workflow: ${WF}`].join("\n"));
    } else if (text.startsWith("/yardim") || text.startsWith("/start")) {
      await tg(env, YARDIM);
    }
    return new Response("ok");
  },
};
