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
const WF_MAC   = "mac.yml";
const WF_GOLGE = "golge.yml";

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
  ["/kuponkorner", { canli: "1", filtre: "korner" }, "sadece korner bahisleri"],
  ["/kuponkart",   { canli: "1", filtre: "kart"   }, "sadece kart bahisleri"],
  ["/kupon2oran", { canli: "1", filtre: "oran2" }, "sadece 2,00 ve üstü oranlar"],
  ["/kupon2li",   { canli: "1", filtre: "iki"   }, "2 maçlık kuponlar"],
  ["/kuponiy",    { canli: "1", filtre: "iy"    }, "sadece ilk yarı bahisleri"],
  ["/kuponau",    { canli: "1", filtre: "au"    }, "sadece alt/üst bahisleri"],
  ["/kuponaü",    { canli: "1", filtre: "au"    }, "sadece alt/üst bahisleri"],
  // Hacim sinirini BILEREK gecmek icin. Ayri komut olmasi bilincli:
  // siniri gecmek bir KARAR olmali, kazara olmamali.
  ["/kuponzorla", { canli: "1", filtre: "", zorla: "1" },
   "HACİM SINIRI BİLEREK AŞILDI"],
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

// /mac <takim> — o macin tum hesabini doker
async function dispatchMac(env, takim) {
  if (!ghToken(env)) return { ok: false, hata: "GH_TOKEN yok" };
  const r = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WF_MAC}/dispatches`, {
      method: "POST",
      headers: { Authorization: `Bearer ${ghToken(env)}`, Accept: "application/vnd.github+json",
                 "User-Agent": "nesine-bot-worker", "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs: { takim } }),
    });
  if (r.status === 204) return { ok: true };
  return { ok: false, hata: `GitHub HTTP ${r.status}: ${(await r.text()).slice(0, 150)}` };
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
  "/kuponkorner sadece korner bahisleri",
  "/kuponkart   sadece kart bahisleri",
  "/mac <ad>   o maçın TÜM hesabını dök (neden seçildi/seçilmedi)",
  "/rapor      önerilerin sonucu + kalibrasyon raporu",
  "/durum   aylik ciro + son oneri",
  "/tani    worker secret tanilama",
  "/yardim  bu liste",
  "",
  "Bot bahis OYNAMAZ. Kuponu sen elinle oynarsin.",
  "Her onerinin beklenen degeri mesajda yazilidir ve NEGATIFTIR.",
  "",
  "HACIM SINIRI YOK. Sayac calisiyor: kac tur ve kac kupon uretildigi",
  "her mesajin sonunda yaziyor. Negatif beklenen degerde kontrol",
  "edebildigin tek sey KAC kez oynadigindir.",
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
  // Cloudflare cron her 15 dakikada bir calisir. GitHub'in kendi schedule'i
  // GUVENILMEZ (arsiv 1+ saat hic tetiklenmedi, gunluk oneri HIC kosmadi),
  // bu yuzden tum zamanlanmis isler buradan tetiklenir.
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const ok = await dispatchArsiv(env);
      if (!ok) await tg(env, "NESINE · arsiv tetiklenemedi (GH_TOKEN?)");
      const d = new Date();
      const s = d.getUTCHours() * 60 + d.getUTCMinutes();
      const pencere = (hh, mm) => {
        const h = hh * 60 + mm;
        return s >= h && s < h + 15;          // 15 dk'lik tek pencere
      };
      const isler = [
        [pencere(5, 20), "istatistik.yml", {}],
        [pencere(6, 0), "golge.yml", {}],
        [pencere(9, 0), "gunluk.yml", {}],
      ];
      for (const [zamani, wf, inputs] of isler) {
        if (!zamani) continue;
        const r = await fetch(
          `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${wf}/dispatches`, {
            method: "POST",
            headers: { Authorization: `Bearer ${ghToken(env)}`,
                       Accept: "application/vnd.github+json",
                       "User-Agent": "nesine-bot-worker",
                       "Content-Type": "application/json" },
            body: JSON.stringify({ ref: "main", inputs }),
          });
        if (r.status !== 204) {
          await tg(env, `NESINE · ${wf} tetiklenemedi (HTTP ${r.status})`);
        }
      }
    })());
  },

  async fetch(request, env) {
    const yol = new URL(request.url).pathname;

    // ── SOFASCORE KOPRUSU ──────────────────────────────────────────────
    // Sofascore veri merkezi IP'lerini engelliyor: GitHub Actions 403,
    // Cloudflare Worker agi da 403 ({"reason":"challenge"}) -- OLCULDU.
    // Gecen tek yer ev IP'si. Bu yuzden Mac'teki toplayici veriyi cekip
    // buraya YAZAR, /kupon (Actions) buradan OKUR. Bot Sofascore'a
    // hicbir zaman dogrudan gitmez.
    //
    // POST /sofa/yaz  (Bearer SOFA_TOKEN)  -> KV'ye yaz
    // GET  /sofa/oku  (serbest)          -> KV.den oku
    if (yol === "/sofa/yaz" || yol === "/sofa/oku") {
      // OKUMA serbest, YAZMA token ister.
      // Gerekce: icerik kamuya acik spor verisi (2-3 KB) ve okuma serbest
      // olunca Actions'a secret dagitmaya gerek kalmiyor. Yazma korumali
      // cunku bozuk veri enjekte edilmesi botu YANLIS bilgiyle besler.
      if (yol === "/sofa/yaz") {
        const bekle = `Bearer ${env.SOFA_TOKEN}`;
        if (!env.SOFA_TOKEN || request.headers.get("Authorization") !== bekle) {
          return new Response("yetkisiz", { status: 401 });
        }
        if (request.method !== "POST") return new Response("POST gerekli", { status: 405 });
        const govde = await request.text();
        if (govde.length > 2_000_000) return new Response("cok buyuk", { status: 413 });
        // 20 dk TTL: toplayici durursa veri KENDILIGINDEN kaybolur.
        // Bayat canli veri, veri YOKLUGUNDAN tehlikelidir -- dolu gorunur.
        await env.SOFA.put("canli", govde, { expirationTtl: 1200 });
        return new Response(JSON.stringify({ ok: true, boyut: govde.length }),
                            { headers: { "Content-Type": "application/json" } });
      }
      const v = await env.SOFA.get("canli");
      if (!v) return new Response(JSON.stringify({ ok: false, sebep: "veri yok veya bayat" }),
                                  { status: 404, headers: { "Content-Type": "application/json" } });
      return new Response(v, { headers: { "Content-Type": "application/json" } });
    }

    if (request.method !== "POST") return new Response("ok");
    let u;
    try { u = await request.json(); } catch (e) { return new Response("ok"); }
    const text = ((u.message && u.message.text) || "").trim().toLowerCase();
    if (!text) return new Response("ok");

    let gh = null, gonderim = null;
    if (text.startsWith("/rapor")) {
      const r = await fetch(
        `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WF_GOLGE}/dispatches`, {
          method: "POST",
          headers: { Authorization: `Bearer ${ghToken(env)}`, Accept: "application/vnd.github+json",
                     "User-Agent": "nesine-bot-worker", "Content-Type": "application/json" },
          body: JSON.stringify({ ref: "main" }),
        });
      gh = { ok: r.status === 204, hata: r.status === 204 ? null : `HTTP ${r.status}` };
      gonderim = await tg(env, gh.ok
        ? "📊 Sonuçlar çözülüyor, rapor ~1 dk içinde gelecek."
        : `TETIKLENEMEDI\n${gh.hata}`);
      return new Response(JSON.stringify({ komut: text, github: gh, telegram: gonderim },
                                         null, 1), { headers: { "Content-Type": "application/json" } });
    }
    if (text.startsWith("/mac")) {
      const takim = text.slice(4).trim();
      if (!takim) {
        gonderim = await tg(env, "Kullanım: /mac <takım adı>\nörn: /mac Fenerbahçe");
      } else {
        gh = await dispatchMac(env, takim);
        gonderim = await tg(env, gh.ok
          ? `🔍 "${takim}" analiz ediliyor... ~1 dk`
          : `TETIKLENEMEDI\n${gh.hata}`);
      }
      return new Response(JSON.stringify({ komut: text, github: gh, telegram: gonderim },
                                         null, 1), { headers: { "Content-Type": "application/json" } });
    }
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
