// Feature showcase for a screen recording: opens the game in a Chrome window (tester1) and plays scripted scenes against a bot (tester2).
// Nothing is captured here; start your screen recorder, then run:
//   node tools/demo/showcase.mjs [--base http://127.0.0.1:8765] [--scenes lobby,conquest,...] [--lang tr|en]
// The page is driven over the Chrome DevTools protocol (window.game / window.ui / window.wtNet hooks in
// main.js / ui.js); the bot is a plain WebSocket client of the hub (realtime.py).
import { spawn } from 'node:child_process';
import { mkdtempSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i > 0 ? process.argv[i + 1] : def; };
const BASE = arg('base', 'http://127.0.0.1:8765');
const LANG = arg('lang', 'tr');
const ONLY = arg('scenes', '');
const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find((p) => existsSync(p));
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const T = (tr, en) => (LANG === 'en' ? en : tr);

// ---------------------------------------------------------------- accounts
async function login(username) {
  const r = await fetch(BASE + '/api/login', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username, password: 'test1234' }) });
  const j = await r.json();
  if (!j.token) throw new Error('login ' + username + ': ' + JSON.stringify(j));
  return j;
}

// ---------------------------------------------------------------- Chrome over CDP
async function openChrome() {
  const profile = mkdtempSync(join(tmpdir(), 'wt-demo-'));
  spawn(CHROME, [
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required', '--window-size=1280,760', '--window-position=40,40',
    '--disable-features=Translate', `--app=${BASE}/client/index.html`,
  ], { detached: true, stdio: 'ignore' }).unref();
  let target = null;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(500);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      target = list.find((t) => t.type === 'page' && t.url.includes('/client/'));
    } catch { /* not up yet */ }
  }
  if (!target) throw new Error('Chrome did not start');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => { ws.onopen = r; });
  let seq = 0;
  const pending = new Map();
  const errors = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails?.exception?.description?.split(String.fromCharCode(10))[0] || m.params.exceptionDetails?.text);
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args?.map((a) => a.value ?? a.description).join(' ').slice(0, 200));
  };
  const call = (method, params = {}) => new Promise((res) => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
  const run = async (expression) => {
    const r = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error('page: ' + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text));
    return r.result?.result?.value;
  };
  return { run, call, errors };
}

// ---------------------------------------------------------------- bot (tester2)
function makeBot(token, meId) {
  const ws = new WebSocket(BASE.replace('http', 'ws') + '/ws?token=' + token);
  const bot = { ws, msgs: [], id: meId, state: { p: [0, -500, 0], y: 0, k: 'human', w: 3041 }, alive: true, sending: false };
  bot.send = (o) => { if (ws.readyState === 1) ws.send(JSON.stringify(o)); };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    bot.msgs.push(m);
    if (m.t === 'kill' && m.victim === bot.id) {
      bot.alive = false;
      if (m.respawn != null) setTimeout(() => { bot.send({ t: 'spawn', kind: bot.state.k }); bot.alive = true; }, m.respawn + 200);
    }
    if ((m.t === 'round' && m.phase === 'ready') || (m.t === 'revive' && m.id === bot.id)) bot.alive = true;
    if (m.t === 'team' && m.id === bot.id) bot.state.k = m.kind;
    if (m.t === 'match.start') bot.send({ t: 'match.enter', loadout: { primary: 3041 } });
  };
  setInterval(() => {
    if (!bot.sending || !bot.alive) return;
    const s = bot.state;
    bot.send({ t: 'st', p: s.p, y: s.y, pi: 0, k: s.k, f: 64, w: s.k === 'wolf' ? null : s.w });
  }, 66);
  bot.ready = new Promise((r) => { ws.onopen = r; });
  bot.mark = () => bot.msgs.length;
  bot.wait = (pred, ms = 30000, from = bot.msgs.length) => new Promise((res, rej) => {
    const t0 = Date.now();
    const tick = () => {
      const hit = bot.msgs.slice(from).find(pred);
      if (hit) return res(hit);
      if (Date.now() - t0 > ms) return rej(new Error('bot wait timeout'));
      setTimeout(tick, 50);
    };
    tick();
  });
  return bot;
}

// ---------------------------------------------------------------- page helpers (injected once)
const PAGE_HELPERS = `
window.__demo = { aimId: null };
(function loop() {
  const d = window.__demo, g = window.game;
  if (g && d.aimId != null) {
    const r = g.remotes.players.get(d.aimId);
    if (r && r.seen) {
      const p = g.player.pos;
      const dx = r.pos.x - p.x, dz = r.pos.z - p.z, dy = (r.pos.y + 0.7) - (p.y + 1.0);
      g.player.yaw = Math.atan2(-dx, -dz);
      g.player.pitch = Math.atan2(dy, Math.hypot(dx, dz));
    }
  }
  requestAnimationFrame(loop);
})();
window.__caption = (title, sub) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;left:28px;top:150px;z-index:99999;pointer-events:none;font-family:Tahoma,sans-serif;' +
      'text-shadow:2px 2px 0 #000,-1px -1px 0 #000;transition:opacity .4s;';
    document.body.appendChild(el);
  }
  el.innerHTML = title ? '<div style="font-size:34px;font-weight:bold;color:#ffc003;letter-spacing:1px">' + title + '</div>' +
    (sub ? '<div style="font-size:17px;color:#fff;margin-top:4px;max-width:520px">' + sub + '</div>' : '') : '';
  el.style.opacity = title ? 1 : 0;
};
window.__key = (code, up) => dispatchEvent(new KeyboardEvent(up ? 'keyup' : 'keydown', { code, bubbles: true }));
true;`;

async function main() {
  if (!CHROME) throw new Error('Chrome / Edge not found');
  const me = await login('tester1');
  const b = await login('tester2');
  const page = await openChrome();
  log('Chrome open');
  // sign the page in (same token store as api.js) and reload into the game
  await page.run(`localStorage.setItem('wt-token', ${JSON.stringify(me.token)}); location.reload(); true`);
  for (let i = 0; i < 120; i++) {
    await sleep(500);
    try { if (await page.run('!!(window.ui && window.game && window.wtNet && window.ui.me)')) break; } catch { /* reloading */ }
  }
  await page.run(PAGE_HELPERS);
  await page.call('Runtime.enable');
  const modes = await (await fetch(BASE + '/client/ui/modes.json')).json();
  const servers = await (await fetch(BASE + '/api/servers', { headers: { Authorization: 'Bearer ' + me.token } })).json();
  const srv = (servers.servers || servers)[0] || { id: 1, name: 'WolfTeam' };
  const bot = makeBot(b.token, b.me?.id ?? b.me?.uid);
  await bot.ready;
  bot.id ??= (await new Promise((r) => { const t = setInterval(() => { const w = bot.msgs.find((m) => m.t === 'welcome'); if (w) { clearInterval(t); r(w.me.uid); } }, 50); }));
  const meId = await page.run('window.ui.me.id');

  const cap = (t, s) => page.run(`window.__caption(${JSON.stringify(t)}, ${JSON.stringify(s || '')})`);
  const key = async (code, holdMs = 80) => { await page.run(`window.__key('${code}')`); await sleep(holdMs); await page.run(`window.__key('${code}', true)`); };
  const fire = async (ms) => { await page.run('window.game.input.fire = true'); await sleep(ms); await page.run('window.game.input.fire = false'); };
  const tp = (p, yaw = 0) => page.run(`window.game.teleport(${p[0]}, ${p[1] + 0.4}, ${p[2]}, ${yaw})`);
  const aim = (id) => page.run(`window.__demo.aimId = ${id == null ? 'null' : id}`);
  const until = async (expr, ms = 40000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if (await page.run(expr).catch(() => false)) return true; await sleep(200); }
    log('timeout:', expr);
    return false;
  };
  const myPos = () => page.run('[window.game.player.pos.x, window.game.player.pos.y, window.game.player.pos.z]');
  const ahead = async (dist) => {   // a point `dist` in front of the player
    const [x, y, z] = await myPos();
    const yaw = await page.run('window.game.player.yaw');
    return [x - Math.sin(yaw) * dist, y, z - Math.cos(yaw) * dist];
  };

  // lobby + room handling: the page is always the host (red), the bot joins and goes blue
  await page.run(`window.ui.enterServer(${JSON.stringify(srv)}); true`);
  bot.send({ t: 'lobby.join', server: srv.id, channel: 0 });
  await sleep(1500);

  async function playRoom(mode, map, mission, time = '10 min') {
    const label = modes.modes[mode]?.label || mode;
    const m0 = bot.mark();
    await page.run(`window.wtNet.send({ t: 'room.create', room: { name: ${JSON.stringify('Demo ' + label)}, mode: '${mode}', map: '${map}', mission: '${mission}', time: '${time}', max: 8 } }); true`);
    await until('!!document.querySelector("#wt-ui") && window.wtNet.online');
    const room = await bot.wait((m) => m.t === 'rooms' && m.rooms.some((r) => r.mode === mode && r.status === 'wait'), 10000, m0)
      .then((m) => m.rooms.find((r) => r.mode === mode && r.status === 'wait'));
    bot.send({ t: 'room.join', id: room.id });
    await bot.wait((m) => m.t === 'room' && m.room.id === room.id);
    await sleep(1200);
    const m1 = bot.mark();
    await page.run(`window.wtNet.send({ t: 'room.start' }); true`);
    bot.sending = false;
    await bot.wait((m) => m.t === 'match.start', 30000, m1);
    await until('window.game.online.on && window.game.playing', 60000);
    bot.sending = true;
    bot.alive = true;
    return room;
  }
  async function leaveRoom() {
    bot.sending = false;
    await aim(null);
    await page.run('window.game.input.fire = false; window.game.leave(); true');
    await sleep(800);
    await page.run(`window.wtNet.send({ t: 'room.leave' }); true`);
    bot.send({ t: 'room.leave' });
    await sleep(1500);
    await page.run('document.querySelectorAll(".wt-msgbox").forEach((n) => n.remove()); true');
  }
  const live = () => until('window.game.online.round?.phase === "live"', 60000);
  const pick = (mode, prefer) => (prefer && modes.playable[prefer]?.includes(mode) ? prefer
    : Object.keys(modes.playable).find((k) => modes.playable[k].includes(mode)));

  const scenes = {
    async lobby() {
      await cap('WolfTeam Web', T('Tarayıcıda WolfTeam: orijinal harita, karakter ve arayüzle yeniden yazıldı', 'WolfTeam in your browser, rebuilt with the original maps, characters and UI'));
      bot.send({ t: 'room.create', room: { name: T('Gel kapışalım', "Let's fight"), mode: 'FM_BOMB', map: pick('FM_BOMB'), mission: '5 rounds', time: '10 min' } });
      await sleep(5000);
      bot.send({ t: 'room.leave' });
      await sleep(800);
    },
    async conquest() {
      const map = pick('FM_FLAG', 'castle');
      await cap('Conquest', T('A–E istasyonlarını ele geçir, hepsini alan raundu kazanır', 'Capture stations A–E; hold them all to win the round'));
      await playRoom('FM_FLAG', map, '3 rounds');
      const st = modes.maps[map].stations;
      bot.state.p = st[st.length - 1].pos;
      await live();
      for (const s of st.slice(0, 3)) {
        await tp(s.pos);
        // stay inside the radius until the hub reports the capture (or give up after a while)
        const m0 = bot.mark();
        await bot.wait((m) => m.t === 'obj' && m.ev?.e === 'capture' && m.ev.station === s.id, (s.time + 4) * 1000, m0)
          .catch(() => log('  no capture at', s.id));
        await sleep(700);
      }
      await cap(T('Büyük harita (M)', 'Full map (M)'), T('Sen, takımın ve hedefler', 'You, your team and the objectives'));
      await page.run(`window.__key('KeyM')`); await sleep(2500); await page.run(`window.__key('KeyM', true)`);
      await cap(T('Radyo (Z / X / C)', 'Radio (Z / X / C)'), T('Takıma karakterin kendi sesiyle mesaj', 'Team messages in your character\'s own voice'));
      await key('KeyZ'); await sleep(1200); await key('Digit1'); await sleep(1800);
      await leaveRoom();
    },
    async destruction() {
      const map = pick('FM_BOMB');
      const site = modes.maps[map].bombs[0];
      await cap('Destruction', T('Kırmızı bombayı kurar (5), mavi E ile çözer', 'Red plants the bomb (5), blue defuses it with E'));
      await playRoom('FM_BOMB', map, '3 rounds');
      bot.state.p = [site.pos[0] + 6, site.pos[1] + 0.3, site.pos[2]];
      await live();
      await tp(site.pos);
      await sleep(600);
      await key('Digit5');
      await sleep(1500);
      await fire(3800);
      await sleep(1500);
      await cap(T('Bomba kuruldu!', 'Bomb planted!'), T('Mavi takım 40 sn içinde çözmeli', 'Blue has 40 s to defuse it'));
      const obj = await bot.wait((m) => m.t === 'obj' && m.bomb, 8000, 0).catch(() => null);
      if (obj?.bomb) {
        bot.state.p = [obj.bomb.pos[0] + 0.6, obj.bomb.pos[1], obj.bomb.pos[2]];
        await page.run(`window.__demo.aimId = null; true`);
        await sleep(1200);
        bot.send({ t: 'act', a: 'defuse' });
        await sleep(6500);
      }
      await sleep(2500);
      await leaveRoom();
    },
    async icehold() {
      const map = pick('FM_ICEHOLD');
      await cap('Ice Hold', T('Ölen donar, takım arkadaşı şırıngayla diriltir', 'The fallen freeze; team-mates thaw them with a syringe'));
      await playRoom('FM_ICEHOLD', map, '3 rounds');
      await live();
      bot.state.p = await ahead(3);
      await sleep(1200);
      await aim(bot.id);
      await sleep(500);
      for (let i = 0; i < 6 && bot.alive; i++) await fire(700);
      await aim(null);
      if (bot.alive) log('  icehold: bot still alive');
      await sleep(4000);
      await leaveRoom();
    },
    async wolfhunt() {
      const map = pick('FM_WOLFHUNT_COUNTERATTACK');
      await cap('Wolfhunt', T('Kurtlar avlar, ölen insan kurda dönüşür', 'Wolves hunt; every human they kill turns into a wolf'));
      await playRoom('FM_WOLFHUNT_COUNTERATTACK', map, '3 rounds');
      await live();
      const imWolf = await page.run('window.game.online.team === "blue"');
      const p = await ahead(1.2);
      bot.state.p = p;
      await sleep(900);
      if (imWolf) {
        await aim(bot.id);
        await fire(3000);
        await aim(null);
      } else {
        bot.state.k = 'wolf';
        for (let i = 0; i < 4; i++) { bot.send({ t: 'hit', to: meId, dmg: 120, w: 'wolf' }); await sleep(350); }
      }
      await sleep(5000);
      await leaveRoom();
    },
    async ctf() {
      const map = 'stronghold_ctf';
      if (!modes.maps[map]?.ctf) return;
      const base = Object.fromEntries(modes.maps[map].ctf.map((x) => [x.team, x.pos]));
      await cap('CTF', T('Kurtlarla bayrak kapmaca: al +1, üsse getir +8', 'Wolf capture the flag: take +1, bring it home +8'));
      await playRoom('FM_CTF', map, '48 pts');
      bot.state = { ...bot.state, k: 'wolf', p: [0, 6, 20] };
      await sleep(2500);
      await tp(base.blue, Math.PI / 2);
      await sleep(2500);
      await tp([base.red[0] - 3, base.red[1], base.red[2]], -Math.PI / 2);
      await sleep(400);
      await tp(base.red, -Math.PI / 2);
      await sleep(4000);
      await leaveRoom();
    },
    async combat() {
      const map = pick('FM_BATTLE', 'castle');
      await cap(T('Silahlar', 'Weapons'), T('Roketatar, mayın, kurulan makineli', 'Rocket launchers, mines, deployable machine guns'));
      await playRoom('FM_BATTLE', map, '80 pts');
      await sleep(1500);
      bot.state.p = await ahead(9);
      await page.run(`window.game.giveWeapon(8501, 'primary')`);
      await sleep(1600);
      await aim(bot.id); await sleep(300); await fire(250); await aim(null);
      await sleep(2500);
      await page.run(`window.game.giveWeapon(8001, 'primary')`);
      await sleep(1500);
      await page.run('window.game.input.alt = true'); await sleep(150); await page.run('window.game.input.alt = false');
      await sleep(1800);
      await aim(bot.id); await fire(1500); await aim(null);
      await sleep(1500);
      await page.run('window.game.input.alt = true'); await sleep(150); await page.run('window.game.input.alt = false');
      await sleep(1500);
      await cap(T('Mayın', 'Mines'), T('Yere kur, düşman yaklaşınca patlar', 'Lay it down; it goes off when an enemy steps close'));
      await page.run(`window.game.giveWeapon(9043, 'grenade')`);
      await sleep(1500);
      await fire(200);
      await sleep(2500);
      bot.state.p = await ahead(0.8);
      await sleep(2500);
      await cap(T('Silah bırak / al (G)', 'Drop / pick up weapons (G)'), T('Ölenlerin silahı yerde kalır', 'Fallen players leave their guns behind'));
      await page.run(`window.game.giveWeapon(3041, 'primary')`);
      await sleep(1500);
      await key('KeyG'); await sleep(1800); await key('KeyG'); await sleep(1800);
      await cap(T('Bıçakla karşı saldırı', 'Knife counter-attack'), T('Orta tık: üstüne atlayan kurdu geri püskürt', 'Middle click: turn a wolf\'s strike back on it'));
      await page.run(`window.game.switchGun('knife')`);
      bot.state = { ...bot.state, k: 'wolf', p: await ahead(1.3) };
      await sleep(1800);
      await page.run('window.game.input.counter = true'); await sleep(120); await page.run('window.game.input.counter = false');
      await sleep(150);
      bot.send({ t: 'hit', to: meId, dmg: 90, w: 'wolf' });
      await sleep(2500);
      await cap(T('Skor tablosu ve ping (Tab)', 'Scoreboard and ping (Tab)'), '');
      await page.run('window.game.showScores()'); await sleep(2500); await page.run('window.game.hideScores()');
      await leaveRoom();
    },
    async end() {
      await cap('WolfTeam Web', T('Fan yapımı, resmi değil · Three.js + Python', 'Fan-made, not affiliated with Softnyx · Three.js + Python'));
      await sleep(5000);
      await cap('');
    },
  };
  const order = ONLY ? ONLY.split(',') : Object.keys(scenes);
  const EVENTS = new Set(['kill', 'countered', 'drop.add', 'pickup', 'revive', 'team', 'radio']);
  for (const name of order) {
    log('scene', name);
    const m0 = bot.mark(), e0 = page.errors.length;
    try { await scenes[name](); } catch (e) { log('scene failed', name, e.message); await leaveRoom().catch(() => {}); }
    // what happened (as the bot saw it) and page errors, for checking a run without watching it
    const seen = bot.msgs.slice(m0).map((m) => (m.t === 'obj' && m.ev ? 'obj:' + m.ev.e : m.t === 'round' && m.phase === 'over' ? 'over:' + m.winner
      : m.t === 'fx' && m.k && m.k !== 'shot' ? 'fx:' + m.k : EVENTS.has(m.t) ? m.t : null)).filter(Boolean);
    if (seen.length) log('  events:', [...new Set(seen)].join(' '));
    for (const err of page.errors.slice(e0)) log('  page error:', err);
  }
  log('done: stop the recording');
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
