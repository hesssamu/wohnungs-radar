const $ = id => document.getElementById(id);
const LNAME = {"baden-wuerttemberg":"Baden-Württemberg","bayern":"Bayern","berlin":"Berlin",
  "brandenburg":"Brandenburg","bremen":"Bremen","hamburg":"Hamburg","hessen":"Hessen",
  "mecklenburg-vorpommern":"Mecklenburg-Vorpommern","niedersachsen":"Niedersachsen",
  "nordrhein-westfalen":"Nordrhein-Westfalen","rheinland-pfalz":"Rheinland-Pfalz",
  "saarland":"Saarland","sachsen":"Sachsen","sachsen-anhalt":"Sachsen-Anhalt",
  "schleswig-holstein":"Schleswig-Holstein","thueringen":"Thüringen"};

const eur = n => (n==null?'—':Math.round(n).toLocaleString('de-DE'));
const pc  = (x,d=2) => x==null ? '—' : (x*100).toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d})+' %';
const dec = (x,d=1) => x==null ? '—' : x.toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d});

const RANGES = ['rmin','cfmin','ekmax'];
const ASS = ['ekq','zins','tilg','tax','hgf','hgn','ausf','geb'];
const NUMS = ['pmin','pmax','qmin','qmax','zmin','bjmin'];
const CHECKS = ['balcony','lift','cellar','ebk','nocourtage','nomulti','onlyrent'];

let page = 1, loading = false, lastTotal = 0;
let preset = {dad:0, star:0};

function params(){
  const p = new URLSearchParams();
  const rmin = +$('rmin').value, cfmin = +$('cfmin').value, ekmax = +$('ekmax').value;
  if (rmin > 0) p.set('rmin', rmin);
  if (cfmin > -500) p.set('cfmin', cfmin);
  if (ekmax < 400000) p.set('ekmax', ekmax);
  NUMS.forEach(k => { if ($(k).value) p.set(k, $(k).value); });
  CHECKS.forEach(k => { if ($(k).checked) p.set(k, 1); });
  ASS.forEach(k => p.set(k, $(k).value));
  if ($('q').value.trim()) p.set('q', $('q').value.trim());
  if ($('land').value) p.set('land', $('land').value);
  if (preset.dad) p.set('dad', 1);
  if (preset.star) p.set('starred', 1);
  p.set('sort', $('sort').value);
  p.set('page', page);
  p.set('per', 25);
  return p;
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

function metricPills(m, o){
  const out = [];
  if (m.brutto != null){
    const cls = m.brutto >= .06 ? 'y-hi' : (m.brutto >= .04 ? 'y-mid' : '');
    out.push(`<span class="m ${cls}"><b>${pc(m.brutto)}</b> brutto</span>`);
    out.push(`<span class="m">Faktor <b>${dec(m.faktor)}</b></span>`);
  } else {
    out.push(`<span class="m">Miete unbekannt</span>`);
  }
  if (m.cf != null)
    out.push(`<span class="m ${m.cf>=0?'pos':'neg'}"><b>${m.cf>=0?'+':'−'}${eur(Math.abs(m.cf))} €</b>/Monat</span>`);
  if (m.ekr != null)
    out.push(`<span class="m ${m.ekr>=0?'pos':'neg'}"><b>${pc(m.ekr,1)}</b> auf EK</span>`);
  out.push(`<span class="m">EK <b>${eur(m.ekb)} €</b></span>`);
  return out.join('');
}

function tagPills(o){
  const t = [];
  if (o.is_dad) t.push('<span class="tag d">von Papa</span>');
  if (o.courtage_pct === 0) t.push('<span class="tag g">provisionsfrei</span>');
  if (o.denkmal) t.push('<span class="tag d">Denkmal</span>');
  if (o.hausgeld == null) t.push('<span class="tag">Hausgeld geschätzt</span>');
  if (o.multi) t.push('<span class="tag w">Paket</span>');
  if (o.soll) t.push('<span class="tag w">Soll-Miete</span>');
  (o.taglist||[]).slice(0,3).forEach(x => t.push(`<span class="tag">${x}</span>`));
  return t.join('');
}

function card(o){
  const m = o.m;
  const img = o.img
    ? `<img src="${o.img}" loading="lazy" alt="" onerror="this.style.display='none'">`
    : `<div class="noimg">kein Bild</div>`;
  const ort = [o.quarter, o.ort].filter(Boolean).join(', ') || o.ort || '—';
  return `<article class="item${o.is_dad?' dad':''}${o.starred?' star':''}" data-id="${o.id}">
    <div class="ph">
      ${img}
      ${m.pqm!=null?`<span class="badge">${eur(m.pqm)} €/m²</span>`:''}
      <button class="fav" data-star="${o.id}" title="Merken">${o.starred?'★':'☆'}</button>
    </div>
    <div class="body">
      <div class="b-top">
        <div class="ttl" data-open="${o.id}">${o.title || 'Eigentumswohnung'}</div>
        <div class="price">${eur(o.price)} €<small>${o.rent?eur(o.rent)+' € Kaltmiete':'Kaufpreis'}</small></div>
      </div>
      <div class="addr">${ort}${o.land?' · '+(LNAME[o.land]||o.land):''}</div>
      <div class="facts">
        <span><b>${dec(o.qm,1)}</b> m²</span>
        <span><b>${o.rooms?dec(o.rooms,1):'—'}</b> Zimmer</span>
        <span>Baujahr <b>${o.bj||'—'}</b></span>
        ${o.hausgeld?`<span>Hausgeld <b>${eur(o.hausgeld)} €</b></span>`:''}
      </div>
      <div class="metrics">${metricPills(m,o)}</div>
      <div class="tags">${tagPills(o)}</div>
      <div class="b-foot">
        <button class="btn" data-open="${o.id}">Rechnung ansehen</button>
        <a class="btn" href="${o.url}" target="_blank" rel="noopener">Inserat</a>
      </div>
    </div>
  </article>`;
}

async function load(reset){
  if (loading) return;
  loading = true;
  if (reset){ page = 1; $('list').innerHTML = ''; }
  const r = await fetch('/api/search?' + params().toString());
  const d = await r.json();
  lastTotal = d.total;
  $('count').innerHTML = `<b>${d.total.toLocaleString('de-DE')}</b> Wohnungen`;
  $('list').insertAdjacentHTML('beforeend', d.items.map(card).join(''));
  $('empty').classList.toggle('hide', d.total > 0);
  $('more').classList.toggle('hide', page * d.per >= d.total);
  loading = false;
}

async function stats(){
  const s = await (await fetch('/api/stats')).json();
  $('tbStats').innerHTML =
    `<b>${s.total.toLocaleString('de-DE')}</b> Objekte · <b>${s.with_rent.toLocaleString('de-DE')}</b> mit belegter Miete · ` +
    `<b>${s.orte.toLocaleString('de-DE')}</b> Orte · <b>${s.dad}</b> von Papa`;
  $('worker').textContent = s.todo > 0
    ? `${s.todo.toLocaleString('de-DE')} Inserate werden noch im Hintergrund geladen`
    : 'alle Inserate ausgewertet';
  const sel = $('land');
  if (sel.options.length <= 1 && s.laender)
    sel.innerHTML = '<option value="">alle</option>' + s.laender
      .map(l => `<option value="${l.land}">${LNAME[l.land]||l.land} (${l.n.toLocaleString('de-DE')})</option>`).join('');
}

async function openDetail(id){
  const o = await (await fetch('/api/detail?id=' + id)).json();
  const p = params(); p.set('id', id);
  const s = await (await fetch('/api/search?' + new URLSearchParams({
    ...Object.fromEntries(ASS.map(k => [k, $(k).value])), q: '', per: 1
  }))).json();
  const a = Object.fromEntries(ASS.map(k => [k, +$(k).value]));
  const grest = {"baden-wuerttemberg":.05,"bayern":.035,"berlin":.06,"brandenburg":.065,
    "bremen":.05,"hamburg":.055,"hessen":.06,"mecklenburg-vorpommern":.06,"niedersachsen":.05,
    "nordrhein-westfalen":.065,"rheinland-pfalz":.05,"saarland":.065,"sachsen":.055,
    "sachsen-anhalt":.05,"schleswig-holstein":.065,"thueringen":.05}[o.land] ?? .055;
  const mk = o.courtage_pct ?? .0357;
  const nk = o.price*(grest+.015+.005+mk), ek = o.price*a.ekq, fin = o.price-ek;
  const ekb = ek+nk, rate = fin*(a.zins+a.tilg)/12;
  const bj = o.bj||1970, afa = bj>=2023?.03:(bj<1925?.025:.02);
  const afaE = o.price*a.geb*afa/12*a.tax, zinsE = fin*a.zins*a.tax/12;
  const hg = (o.hausgeld ?? o.qm*a.hgf)*a.hgn;
  const cf = o.rent ? o.rent-rate-hg-a.ausf+afaE+zinsE : null;
  const imgs = (o.imglist||[]).slice(0,6).map(u=>`<img src="${u}" loading="lazy" alt="">`).join('');
  $('sheetBody').innerHTML = `
    <h2>${o.title||'Eigentumswohnung'}</h2>
    <div class="addr">${[o.street,o.quarter,o.plz,o.ort].filter(Boolean).join(', ')}</div>
    ${imgs?`<div class="gallery">${imgs}</div>`:''}
    <table class="calc">
      <tr><td>Kaufpreis</td><td>${eur(o.price)} €</td></tr>
      <tr><td>Grunderwerbsteuer (${pc(grest,1)}), Notar 1,5 %, Grundbuch 0,5 %${mk?`, Courtage ${pc(mk,2)}`:''}</td><td>${eur(nk)} €</td></tr>
      <tr><td>Eigenkapital ${pc(a.ekq,0)} + Nebenkosten</td><td>${eur(ekb)} €</td></tr>
      <tr><td>Darlehen</td><td>${eur(fin)} €</td></tr>
      <tr><td>Rate (${pc(a.zins,1)} Zins + ${pc(a.tilg,1)} Tilgung)</td><td>− ${eur(rate)} €</td></tr>
      <tr><td>Kaltmiete</td><td>${o.rent?'+ '+eur(o.rent)+' €':'unbekannt'}</td></tr>
      <tr><td>Hausgeld nicht umlegbar (${pc(a.hgn,0)} von ${eur(o.hausgeld ?? o.qm*a.hgf)} €${o.hausgeld==null?', geschätzt':''})</td><td>− ${eur(hg)} €</td></tr>
      <tr><td>Mietausfall &amp; Reparatur</td><td>− ${eur(a.ausf)} €</td></tr>
      <tr><td>Steuerersparnis AfA (${pc(afa,1)} auf ${pc(a.geb,0)} Gebäudeanteil)</td><td>+ ${eur(afaE)} €</td></tr>
      <tr><td>Steuerersparnis Zinsen</td><td>+ ${eur(zinsE)} €</td></tr>
      <tr class="sum"><td><b>Cashflow pro Monat</b></td><td><b>${cf==null?'—':(cf>=0?'+ ':'− ')+eur(Math.abs(cf))+' €'}</b></td></tr>
      <tr><td>Bruttorendite / Faktor</td><td>${o.rent?pc(o.rent*12/o.price)+' / '+dec(o.price/(o.rent*12)):'—'}</td></tr>
      <tr><td>Eigenkapitalrendite</td><td>${cf==null?'—':pc(cf*12/ekb,1)}</td></tr>
    </table>
    ${o.rent_evidence?`<div class="beleg"><em>Mietbeleg aus dem Inserat</em>…${o.rent_evidence}…</div>`:''}
    <div class="b-foot" style="margin-top:16px">
      <a class="btn" href="${o.url}" target="_blank" rel="noopener">Inserat auf ImmoScout24 öffnen</a>
    </div>`;
  $('sheet').classList.remove('hide');
}

function bind(){
  [...RANGES, ...ASS].forEach(k => $(k).addEventListener('input', () => { labels(); clearTimeout(window._t); window._t = setTimeout(()=>load(true), 180); }));
  [...NUMS, 'q'].forEach(k => $(k).addEventListener('input', () => { clearTimeout(window._t); window._t = setTimeout(()=>load(true), 350); }));
  [...CHECKS, 'land', 'sort'].forEach(k => $(k).addEventListener('change', () => load(true)));

  document.querySelectorAll('.chip').forEach(ch => ch.addEventListener('click', () => {
    const p = ch.dataset.preset;
    if (p === 'rendite'){ $('rmin').value = ($('rmin').value == 6 ? 0 : 6); }
    if (p === 'cashflow'){ $('cfmin').value = ($('cfmin').value == 0 ? -500 : 0); }
    if (p === 'klein'){ $('ekmax').value = ($('ekmax').value == 30000 ? 400000 : 30000); }
    if (p === 'dad'){ preset.dad = preset.dad ? 0 : 1; if (preset.dad) $('onlyrent').checked = false; }
    if (p === 'star'){ preset.star = preset.star ? 0 : 1; if (preset.star) $('onlyrent').checked = false; }
    ch.classList.toggle('on');
    labels(); load(true);
  }));

  $('moreBtn').addEventListener('click', () => { page++; load(false); });
  $('reset').addEventListener('click', () => {
    NUMS.forEach(k => $(k).value = '');
    $('q').value = ''; $('land').value = '';
    $('rmin').value = 0; $('cfmin').value = -500; $('ekmax').value = 400000;
    $('ekq').value=.2; $('zins').value=.04; $('tilg').value=.02; $('tax').value=.425;
    $('hgf').value=4; $('hgn').value=.35; $('ausf').value=30; $('geb').value=.75;
    CHECKS.forEach(k => $(k).checked = (k === 'onlyrent'));
    preset = {dad:0, star:0};
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('on'));
    labels(); load(true);
  });

  document.body.addEventListener('click', async e => {
    const st = e.target.closest('[data-star]');
    if (st){
      const item = st.closest('.item');
      const on = !item.classList.contains('star');
      await fetch('/api/star', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id: st.dataset.star, on})});
      item.classList.toggle('star', on);
      st.textContent = on ? '★' : '☆';
      stats();
      return;
    }
    const op = e.target.closest('[data-open]');
    if (op){ openDetail(op.dataset.open); return; }
  });

  $('sheetX').addEventListener('click', () => $('sheet').classList.add('hide'));
  $('sheet').addEventListener('click', e => { if (e.target.id === 'sheet') $('sheet').classList.add('hide'); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') $('sheet').classList.add('hide'); });
  $('filterToggle').addEventListener('click', () => $('rail').classList.remove('hide'));
  $('filterClose').addEventListener('click', () => $('rail').classList.add('hide'));
  if (window.innerWidth <= 860) $('rail').classList.add('hide');
}

labels(); bind(); stats(); load(true);
setInterval(stats, 20000);
