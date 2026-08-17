/* Wohnungs-Radar — statische Fassung für GitHub Pages.
   Alles rechnet im Browser; die Daten kommen aus data.json. */

const $ = id => document.getElementById(id);
const LNAME = {"baden-wuerttemberg":"Baden-Württemberg","bayern":"Bayern","berlin":"Berlin",
  "brandenburg":"Brandenburg","bremen":"Bremen","hamburg":"Hamburg","hessen":"Hessen",
  "mecklenburg-vorpommern":"Mecklenburg-Vorpommern","niedersachsen":"Niedersachsen",
  "nordrhein-westfalen":"Nordrhein-Westfalen","rheinland-pfalz":"Rheinland-Pfalz",
  "saarland":"Saarland","sachsen":"Sachsen","sachsen-anhalt":"Sachsen-Anhalt",
  "schleswig-holstein":"Schleswig-Holstein","thueringen":"Thüringen"};
const GREST = {"baden-wuerttemberg":.05,"bayern":.035,"berlin":.06,"brandenburg":.065,
  "bremen":.05,"hamburg":.055,"hessen":.06,"mecklenburg-vorpommern":.06,"niedersachsen":.05,
  "nordrhein-westfalen":.065,"rheinland-pfalz":.05,"saarland":.065,"sachsen":.055,
  "sachsen-anhalt":.05,"schleswig-holstein":.065,"thueringen":.05};

const eur = n => (n==null||isNaN(n)) ? '—' : Math.round(n).toLocaleString('de-DE');
const pc  = (x,d=2) => x==null ? '—' : (x*100).toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d})+' %';
const dec = (x,d=1) => x==null ? '—' : x.toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d});

const ASS = ['ekq','zins','tilg','tax','hgf','hgn','ausf','geb'];
const NUMS = ['pmin','pmax','qmin','qmax','zmin','bjmin'];
const CHECKS = ['balcony','lift','cellar','ebk','nocourtage','nomulti','onlyrent'];

let DATA = [], STATS = {}, shown = 25, preset = {dad:0, star:0};
let stars = new Set(JSON.parse(localStorage.getItem('wr_stars') || '[]'));

/* ---- Kennwort: bewusst nur eine Türklinke, kein Schloss. Die Daten sind
       öffentliche Inserate; echten Schutz bietet nur die Server-Fassung. ---- */
const GATE = 'radar2026';
function unlock(){ $('gate').remove(); $('app').classList.remove('hide'); start(); }
$('gateForm').addEventListener('submit', e => {
  e.preventDefault();
  if ($('gatePw').value.trim().toLowerCase() === GATE){
    sessionStorage.setItem('wr_ok','1'); unlock();
  } else {
    $('gateErr').textContent = 'Kennwort stimmt nicht.';
    $('gatePw').select();
  }
});
if (sessionStorage.getItem('wr_ok') === '1') unlock();

function ass(){ return Object.fromEntries(ASS.map(k => [k, +$(k).value])); }

function calc(o, a){
  const grest = GREST[o.l] ?? .055, mk = o.ct ?? .0357;
  const nk = o.p*(grest+.015+.005+mk);
  const ek = o.p*a.ekq, fin = o.p-ek, ekb = ek+nk;
  const rate = fin*(a.zins+a.tilg)/12;
  const bj = o.bj || 1970;
  const afa = bj>=2023 ? .03 : (bj<1925 ? .025 : .02);
  const afaE = o.p*a.geb*afa/12*a.tax, zinsE = fin*a.zins*a.tax/12;
  const hgT = o.hg ?? o.m2*a.hgf;
  const cf = o.r ? o.r - rate - hgT*a.hgn - a.ausf + afaE + zinsE : null;
  return {nk, ekb, rate, hgT, afa, cf,
    brutto: o.r ? o.r*12/o.p : null,
    faktor: o.r ? o.p/(o.r*12) : null,
    ekr: (o.r && ekb>0) ? cf*12/ekb : null,
    pqm: o.p/o.m2};
}

function filtered(){
  const a = ass();
  const rmin = +$('rmin').value, cfmin = +$('cfmin').value, ekmax = +$('ekmax').value;
  const q = $('q').value.trim().toLowerCase(), land = $('land').value;
  const pmin = +$('pmin').value||0, pmax = +$('pmax').value||Infinity;
  const qmin = +$('qmin').value||0, qmax = +$('qmax').value||Infinity;
  const zmin = +$('zmin').value||0, bjmin = +$('bjmin').value||0;
  const out = [];
  for (const o of DATA){
    if (preset.dad && !o.dad) continue;
    if (preset.star && !stars.has(o.id)) continue;
    if ($('onlyrent').checked && !o.r) continue;
    if (land && o.l !== land) continue;
    if (o.p < pmin || o.p > pmax) continue;
    if (o.m2 < qmin || o.m2 > qmax) continue;
    if (zmin && (!o.zi || o.zi < zmin)) continue;
    if (bjmin && (!o.bj || o.bj < bjmin)) continue;
    if ($('balcony').checked && !o.bal) continue;
    if ($('lift').checked && !o.lif) continue;
    if ($('cellar').checked && !o.kel) continue;
    if ($('ebk').checked && !o.ebk) continue;
    if ($('nocourtage').checked && o.ct !== 0) continue;
    if ($('nomulti').checked && o.mu) continue;
    if (q && !((o.o+' '+o.q+' '+o.z+' '+o.t).toLowerCase().includes(q))) continue;
    const c = calc(o, a);
    if (rmin > 0 && (c.brutto == null || c.brutto*100 < rmin)) continue;
    if (cfmin > -500 && (c.cf == null || c.cf < cfmin)) continue;
    if (ekmax < 400000 && c.ekb > ekmax) continue;
    out.push({o, c});
  }
  const s = $('sort').value;
  const key = {
    brutto: x => -(x.c.brutto ?? -9), cf: x => -(x.c.cf ?? -9e9), ekr: x => -(x.c.ekr ?? -9),
    ek: x => x.c.ekb, faktor: x => (x.c.faktor ?? 9e9), pqm: x => x.c.pqm,
    price_asc: x => x.o.p, price_desc: x => -x.o.p, qm_desc: x => -x.o.m2,
  }[s] || (x => -(x.c.brutto ?? -9));
  out.sort((A,B) => key(A)-key(B));
  return out;
}

function tags(o){
  const t = [];
  if (o.dad) t.push('<span class="tag d">von Papa</span>');
  if (o.ct === 0) t.push('<span class="tag g">provisionsfrei</span>');
  if (o.dk) t.push('<span class="tag d">Denkmal</span>');
  if (o.hg == null) t.push('<span class="tag">Hausgeld geschätzt</span>');
  if (o.mu) t.push('<span class="tag w">Paket</span>');
  if (o.so) t.push('<span class="tag w">Soll-Miete</span>');
  return t.join('');
}

function card({o, c}){
  const img = o.img ? `<img src="${o.img}" loading="lazy" alt="" onerror="this.remove()">`
                    : `<div class="noimg">kein Bild</div>`;
  const ort = [o.q, o.o].filter(Boolean).join(', ') || o.o || '—';
  const yc = c.brutto == null ? '' : (c.brutto >= .06 ? 'y-hi' : (c.brutto >= .04 ? 'y-mid' : ''));
  return `<article class="item${o.dad?' dad':''}${stars.has(o.id)?' star':''}" data-id="${o.id}">
    <div class="ph">${img}
      <span class="badge">${eur(c.pqm)} €/m²</span>
      <button class="fav" data-star="${o.id}" title="Merken">${stars.has(o.id)?'★':'☆'}</button>
    </div>
    <div class="body">
      <div class="b-top">
        <div class="ttl" data-open="${o.id}">${o.t || 'Eigentumswohnung'}</div>
        <div class="price">${eur(o.p)} €<small>${o.r?eur(o.r)+' € Kaltmiete':'Kaufpreis'}</small></div>
      </div>
      <div class="addr">${ort}${o.l?' · '+(LNAME[o.l]||o.l):''}</div>
      <div class="facts">
        <span><b>${dec(o.m2)}</b> m²</span>
        <span><b>${o.zi?dec(o.zi):'—'}</b> Zimmer</span>
        <span>Baujahr <b>${o.bj||'—'}</b></span>
        ${o.hg?`<span>Hausgeld <b>${eur(o.hg)} €</b></span>`:''}
      </div>
      <div class="metrics">
        ${c.brutto!=null?`<span class="m ${yc}"><b>${pc(c.brutto)}</b> brutto</span>
        <span class="m">Faktor <b>${dec(c.faktor)}</b></span>`:'<span class="m">Miete unbekannt</span>'}
        ${c.cf!=null?`<span class="m ${c.cf>=0?'pos':'neg'}"><b>${c.cf>=0?'+':'−'}${eur(Math.abs(c.cf))} €</b>/Monat</span>`:''}
        ${c.ekr!=null?`<span class="m ${c.ekr>=0?'pos':'neg'}"><b>${pc(c.ekr,1)}</b> auf EK</span>`:''}
        <span class="m">EK <b>${eur(c.ekb)} €</b></span>
      </div>
      <div class="tags">${tags(o)}</div>
      <div class="b-foot">
        <button class="btn" data-open="${o.id}">Rechnung ansehen</button>
        <a class="btn" href="https://www.immobilienscout24.de/expose/${o.id}" target="_blank" rel="noopener">Inserat</a>
      </div>
    </div>
  </article>`;
}

function render(){
  const rows = filtered();
  window.__rows = rows;
  $('count').innerHTML = `<b>${rows.length.toLocaleString('de-DE')}</b> Wohnungen`;
  $('list').innerHTML = rows.slice(0, shown).map(card).join('');
  $('empty').classList.toggle('hide', rows.length > 0);
  $('more').classList.toggle('hide', shown >= rows.length);
}

function detail(id){
  const row = (window.__rows||[]).find(x => x.o.id === id) ||
              {o: DATA.find(x => x.id === id), c: null};
  const o = row.o; if (!o) return;
  const a = ass(), c = calc(o, a);
  const grest = GREST[o.l] ?? .055;
  $('sheetBody').innerHTML = `
    <h2>${o.t || 'Eigentumswohnung'}</h2>
    <div class="addr">${[o.q, o.z, o.o].filter(Boolean).join(', ')}</div>
    ${o.img?`<div class="gallery"><img src="${o.img}" alt=""></div>`:''}
    <table class="calc">
      <tr><td>Kaufpreis</td><td>${eur(o.p)} €</td></tr>
      <tr><td>Grunderwerbsteuer ${pc(grest,1)}, Notar 1,5 %, Grundbuch 0,5 %${o.ct?`, Courtage ${pc(o.ct,2)}`:''}</td><td>${eur(c.nk)} €</td></tr>
      <tr><td>Eigenkapital ${pc(a.ekq,0)} + Nebenkosten</td><td>${eur(c.ekb)} €</td></tr>
      <tr><td>Darlehen</td><td>${eur(o.p - o.p*a.ekq)} €</td></tr>
      <tr><td>Rate (${pc(a.zins,1)} Zins + ${pc(a.tilg,1)} Tilgung)</td><td>− ${eur(c.rate)} €</td></tr>
      <tr><td>Kaltmiete</td><td>${o.r?'+ '+eur(o.r)+' €':'unbekannt'}</td></tr>
      <tr><td>Hausgeld nicht umlegbar (${pc(a.hgn,0)} von ${eur(c.hgT)} €${o.hg==null?', geschätzt':''})</td><td>− ${eur(c.hgT*a.hgn)} €</td></tr>
      <tr><td>Mietausfall &amp; Reparatur</td><td>− ${eur(a.ausf)} €</td></tr>
      <tr><td>Steuerersparnis AfA (${pc(c.afa,1)})</td><td>+ ${eur(o.p*a.geb*c.afa/12*a.tax)} €</td></tr>
      <tr><td>Steuerersparnis Zinsen</td><td>+ ${eur((o.p-o.p*a.ekq)*a.zins*a.tax/12)} €</td></tr>
      <tr class="sum"><td><b>Cashflow pro Monat</b></td><td><b>${c.cf==null?'—':(c.cf>=0?'+ ':'− ')+eur(Math.abs(c.cf))+' €'}</b></td></tr>
      <tr><td>Bruttorendite / Faktor</td><td>${c.brutto!=null?pc(c.brutto)+' / '+dec(c.faktor):'—'}</td></tr>
      <tr><td>Eigenkapitalrendite</td><td>${c.ekr!=null?pc(c.ekr,1):'—'}</td></tr>
    </table>
    ${o.be?`<div class="beleg"><em>Mietbeleg aus dem Inserat</em>…${o.be}…</div>`:''}
    <div class="b-foot" style="margin-top:16px">
      <a class="btn" href="https://www.immobilienscout24.de/expose/${o.id}" target="_blank" rel="noopener">Inserat auf ImmoScout24 öffnen</a>
    </div>`;
  $('sheet').classList.remove('hide');
}

function labels(){
  const r = +$('rmin').value, cf = +$('cfmin').value, ek = +$('ekmax').value;
  $('rminV').textContent  = r > 0 ? dec(r,2)+' %' : 'alle';
  $('cfminV').textContent = cf > -500 ? (cf>=0?'+':'−')+eur(Math.abs(cf))+' €' : 'alle';
  $('ekmaxV').textContent = ek < 400000 ? eur(ek)+' €' : 'alle';
  $('ekqV').textContent  = pc(+$('ekq').value,0);
  $('zinsV').textContent = pc(+$('zins').value,1);
  $('tilgV').textContent = pc(+$('tilg').value,1);
  $('taxV').textContent  = pc(+$('tax').value,1);
  $('hgfV').textContent  = dec(+$('hgf').value,2)+' €/m²';
  $('hgnV').textContent  = pc(+$('hgn').value,0);
  $('ausfV').textContent = eur(+$('ausf').value)+' €';
  $('gebV').textContent  = pc(+$('geb').value,0);
}

function bind(){
  const redraw = () => { shown = 25; render(); };
  ['rmin','cfmin','ekmax',...ASS].forEach(k => $(k).addEventListener('input', () => { labels(); redraw(); }));
  [...NUMS,'q'].forEach(k => $(k).addEventListener('input', () => { clearTimeout(window._t); window._t = setTimeout(redraw, 250); }));
  [...CHECKS,'land','sort'].forEach(k => $(k).addEventListener('change', redraw));

  document.querySelectorAll('.chip').forEach(ch => ch.addEventListener('click', () => {
    const p = ch.dataset.preset;
    if (p==='rendite')  $('rmin').value = ($('rmin').value == 6 ? 0 : 6);
    if (p==='cashflow') $('cfmin').value = ($('cfmin').value == 0 ? -500 : 0);
    if (p==='klein')    $('ekmax').value = ($('ekmax').value == 30000 ? 400000 : 30000);
    if (p==='dad'){ preset.dad = preset.dad?0:1; if (preset.dad) $('onlyrent').checked = false; }
    if (p==='star'){ preset.star = preset.star?0:1; if (preset.star) $('onlyrent').checked = false; }
    ch.classList.toggle('on'); labels(); redraw();
  }));

  $('moreBtn').addEventListener('click', () => { shown += 25; render(); });
  $('reset').addEventListener('click', () => {
    NUMS.forEach(k => $(k).value = ''); $('q').value=''; $('land').value='';
    $('rmin').value=0; $('cfmin').value=-500; $('ekmax').value=400000;
    $('ekq').value=.2; $('zins').value=.04; $('tilg').value=.02; $('tax').value=.425;
    $('hgf').value=4; $('hgn').value=.35; $('ausf').value=30; $('geb').value=.75;
    CHECKS.forEach(k => $(k).checked = (k==='onlyrent'));
    preset = {dad:0, star:0};
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('on'));
    labels(); redraw();
  });

  document.body.addEventListener('click', e => {
    const st = e.target.closest('[data-star]');
    if (st){
      const id = st.dataset.star;
      stars.has(id) ? stars.delete(id) : stars.add(id);
      localStorage.setItem('wr_stars', JSON.stringify([...stars]));
      render(); return;
    }
    const op = e.target.closest('[data-open]');
    if (op) detail(op.dataset.open);
  });
  $('sheetX').addEventListener('click', () => $('sheet').classList.add('hide'));
  $('sheet').addEventListener('click', e => { if (e.target.id==='sheet') $('sheet').classList.add('hide'); });
  document.addEventListener('keydown', e => { if (e.key==='Escape') $('sheet').classList.add('hide'); });
  $('filterToggle').addEventListener('click', () => $('rail').classList.remove('hide'));
  $('filterClose').addEventListener('click', () => $('rail').classList.add('hide'));
  if (window.innerWidth <= 860) $('rail').classList.add('hide');
}

async function start(){
  const res = await fetch('data.json');
  const d = await res.json();
  DATA = d.items; STATS = d.stats;
  $('tbStats').innerHTML =
    `<b>${STATS.shown.toLocaleString('de-DE')}</b> mit belegter Miete · aus <b>${STATS.total.toLocaleString('de-DE')}</b> Objekten · ` +
    `<b>${STATS.orte.toLocaleString('de-DE')}</b> Orte · Stand ${STATS.stand}`;
  $('worker').textContent = STATS.todo > 0
    ? `${STATS.todo.toLocaleString('de-DE')} Inserate noch nicht ausgewertet`
    : 'alle Inserate ausgewertet';
  const ls = [...new Set(DATA.map(o => o.l))].filter(Boolean).sort((a,b)=>(LNAME[a]||a).localeCompare(LNAME[b]||b));
  $('land').innerHTML = '<option value="">alle</option>' +
    ls.map(l => `<option value="${l}">${LNAME[l]||l}</option>`).join('');
  labels(); bind(); render();
}
