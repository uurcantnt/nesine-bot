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
const WF_ARSIV = "arsiv.yml";

// Secret isimleri iki turlu de kabul edilir: Cloudflare'de CHAT_ID, GitHub
// secret'larinda TG_CHAT_ID kullaniliyor; isim uyusmazligi tum mesajlari
// SESSIZCE dusuruyordu (2026-08-20'de yasandi).
const chatId = (env) => env.CHAT_ID || env.TG_CHAT_ID;
const ghToken = (env) => env.GH_TOKEN || env.GITHUB_TOKEN || env.GH_PAT;

// Telegram gonderimi -- sonucu DONDURUR. Telegram calismiyorsa hatayi
// Telegram'dan ogrenemeyiz; bu yuzden HTTP yanitina da yazilir.
async function tg(env, text) {
  const tok = env.TG_BOT_TOKEN;
  if (!tok) return { ok: false, hata: "TG_BOT_TOKEN secret'i YOK" };
  if (!chatId(env)) return { ok: false, hata: "CHAT_ID / TG_CHAT_ID secret'i YOK" };
  try {
    const r = await fetch(`https://api.telegram.org/bot${tok}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId(env), text, disable_web_page_preview: true }),
    });
    if (r.ok) return { ok: true };
    return { ok: false, hata: `Telegram HTTP ${r.status}: ${(await r.text()).slice(0, 160)}` };
  } catch (e) {
    return { ok: false, hata: `Telegram aga cikilamadi: ${e.message}` };
  }
}

async function ghJSON(env, path) {
  const r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`, {
    headers: { Authorization: `Bearer ${ghToken(env)}`, Accept: "application/vnd.github+json",
               "User-Agent": "nesine-bot-worker" },
  });
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const j = await r.json();
  return JSON.parse(decodeURIComponent(escape(atob(j.content.replace(/\n/g, "")))));
}

// Dispatch — basarisizlikta SEBEBI dondurur. Sessiz hata YASAK:
// kripto botunda tum worker hatalari sessizdi ve "K/Z hep 0" diye
// fark edilene kadar gunlerce yanlis calisti.
// Zamanlayici: arsiv workflow'unu tetikler.
// NEDEN: GitHub'in kendi cron'u yeni repoda saatlerce tetiklenmedi ve */15
// cron'lari yogunlukta atlaniyor. Kacan oran geri gelmedigi icin arsiv
// tetiklemesi Cloudflare cron'una (cok daha dakik) devredildi.
// GitHub schedule'i da acik birakildi -- ikisi ayni anda gelirse oddVersion
// ayni oldugu icin ikinci cekim zaten yazmadan doner.
async function dispatchArsiv(env) {
  if (!ghToken(env)) return false;
  const r = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WF_ARSIV}/dispatches`, {
      method: "POST",
      headers: { Authorization: `Bearer ${ghToken(env)}`, Accept: "application/vnd.github+json",
                 "User-Agent": "nesine-bot-worker", "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    });
  return r.status === 204;
}

// Komut -> workflow girdisi. Sira ONEMLI: /kupon2oran ve /kupon2li ikisi de
// "/kupon2" ile basliyor, /kupon0 da "/kupon" ile.
const KUPON_KOMUTLARI = [
  ["/kupon2oran", { canli: "1", filtre: "oran2" }, "sadece 2,00 ve üstü oranlar"],
  ["/kupon2li",   { canli: "1", filtre: "iki"   }, "2 maçlık kuponlar"],
  ["/kuponiy",    { canli: "1", filtre: "iy"    }, "sadece ilk yarı bahisleri"],
  ["/kuponau",    { canli: "1", filtre: "au"    }, "sadece alt/üst bahisleri"],
  ["/kuponaü",    { canli: "1", filtre: "au"    }, "sadece alt/üst bahisleri"],
  ["/kupon0",     { canli: "0", filtre: ""      }, "canlı maçlar hariç"],
  ["/kupon",      { canli: "1", filtre: ""      }, ""],
];

async function dispatch(env, girdi) {
  if (!ghToken(env)) return { ok: false, hata: "GH_TOKEN secret'i TANIMSIZ (isim yanlis olabilir)" };
  let r;
  try {
    r = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WF}/dispatches`, {
        method: "POST",
        headers: { Authorization: `Bearer ${ghToken(env)}`, Accept: "application/vnd.github+json",
                   "User-Agent": "nesine-bot-worker", "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "main", inputs: girdi }),
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
  "/kupon      3 risk seviyesinde kupon (canlı dahil)",
  "/kupon0     aynısı, canlı maçlar HARİÇ",
  "/kuponiy    sadece İLK YARI bahisleri",
  "/kuponau    sadece ALT/ÜST bahisleri",
  "/kupon2oran sadece 2,00 ve üstü oranlar",
  "/kupon2li   2 maçlık kuponlar",
  "/durum   aylik ciro + son oneri",
  "/tani    worker secret tanilama",
  "/yardim  bu liste",
  "",
  "Bot bahis OYNAMAZ. Kuponu sen elinle oynarsin.",
  "Her onerinin beklenen degeri mesajda yazilidir ve NEGATIFTIR.",
].join("\n");

function tani(env) {
  const v = (x) => (x ? `var (${String(x).length} kr)` : "YOK");
  return ["Worker tanilama:",
    `GH_TOKEN     : ${v(env.GH_TOKEN)}`,
    `GITHUB_TOKEN : ${v(env.GITHUB_TOKEN)}`,
    `TG_BOT_TOKEN : ${v(env.TG_BOT_TOKEN)}`,
    `CHAT_ID      : ${v(env.CHAT_ID)}`,
    `TG_CHAT_ID   : ${v(env.TG_CHAT_ID)}`,
    `kullanilan token ilk 11: ${ghToken(env) ? String(ghToken(env)).slice(0, 11) : "-"}`,
    `kullanilan chat_id     : ${chatId(env) || "-"}`,
    `repo: ${OWNER}/${REPO} · workflow: ${WF}`].join("\n");
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const ok = await dispatchArsiv(env);
      if (!ok) await tg(env, "NESINE · arsiv tetiklenemedi (GH_TOKEN?)");
    })());
  },

  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    let u;
    try { u = await request.json(); } catch (e) { return new Response("ok"); }
    const text = ((u.message && u.message.text) || "").trim().toLowerCase();
    if (!text) return new Response("ok");

    let gh = null, gonderim = null;
    const kk = KUPON_KOMUTLARI.find(([ad]) => text.startsWith(ad));
    if (kk) {
      const [, girdi, aciklama] = kk;
      gh = await dispatch(env, girdi);
      gonderim = await tg(env, gh.ok
        ? `⏳ Kupon hesaplanıyor${aciklama ? " — " + aciklama : ""}...\n~1 dk içinde gelecek.`
        : `TETIKLENEMEDI\n${gh.hata}`);
    } else if (text.startsWith("/durum")) {
      gonderim = await tg(env, await durum(env));
    } else if (text.startsWith("/tani")) {
      gonderim = await tg(env, tani(env));
    } else if (text.startsWith("/yardim") || text.startsWith("/start")) {
      gonderim = await tg(env, YARDIM);
    }
    // Tanilama HTTP yanitina da yazilir: Telegram bozuksa hatayi Telegram'dan
    // ogrenemeyiz, curl ile gorulebilmesi gerekir.
    return new Response(JSON.stringify({ komut: text, github: gh, telegram: gonderim },
                                       null, 1), { headers: { "Content-Type": "application/json" } });
  },
};
