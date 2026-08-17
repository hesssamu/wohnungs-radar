# Wohnungs-Radar

Lokale Anwendung, die vermietete Eigentumswohnungen aus ganz Deutschland sammelt
und mit Papas Modell aus `vergleichsrechnungen_2.xlsx` durchrechnet.

## Starten

```bash
cd ~/wohnungs-radar
./run.sh                 # nur die Anwendung   -> http://localhost:8840
./run.sh --worker        # zusätzlich Mieten im Hintergrund nachladen
```

Port über `PORT=8850 ./run.sh` änderbar. Keine Abhängigkeiten — reines Python 3.

### Von anderen Geräten

Der Server lauscht auf `127.0.0.1` **und** auf der Tailscale-Adresse des Mac Studio.
Damit ist er von jedem Gerät im eigenen Tailnet erreichbar, aber nicht aus dem offenen Netz:

```
http://samuels-mac-studio.tail5383ed.ts.net:8840     # MacBook, iPhone
http://100.102.112.83:8840                            # dieselbe Maschine per IP
```

Voraussetzung: der Mac Studio läuft und Tailscale ist auf beiden Geräten an.
Nur-lokal erzwingen: `HOST=127.0.0.1 ./run.sh`.
Für Papa, der nicht im Tailnet ist, siehe „Teilen“ unten.

### Passwort

Der Server verlangt HTTP-Basic-Auth, sobald in `~/.config/secrets/wohnungs-radar.env`
ein `RADAR_PASS` steht (Vorlage: `wohnungs-radar.env.example`). Ohne Passwort läuft
die Anwendung ungeschützt — dann bitte nur auf localhost betreiben.

Geschützt ist **alles**, auch die API. Passwort ändern: Datei bearbeiten, Server neu starten.

### Deaktivierte Angebote

Ein zurückgezogenes Inserat liefert weiterhin die volle Seite mit Preis und
Beschreibung — es muss also ausdrücklich erkannt werden, sonst sieht ein totes
Angebot aus wie ein lebendiges Schnäppchen. `core.is_gone()` prüft auf
„Angebot wurde deaktiviert“; solche Objekte bekommen `rent_status='gone'` und
tauchen in der Suche nicht mehr auf (`?showgone=1` zeigt sie doch).

### Teilen mit jemandem außerhalb des Tailnets

Zwei saubere Wege, beide erst nach ausdrücklicher Freigabe:

1. **Tailscale-Einladung** — Papa installiert Tailscale, wird in den Tailnet eingeladen,
   fertig. Nichts liegt öffentlich.
2. **`tailscale funnel 8840`** — macht die Anwendung öffentlich im Netz erreichbar.
   Achtung: dann kann sie jeder mit der URL sehen. Nur bewusst einsetzen.

## Was drin ist

| Datei | Zweck |
|---|---|
| `core.py` | Datenbank, Parser, Renditemodell |
| `server.py` | HTTP-Server + JSON-API (`/api/search`, `/api/stats`, `/api/detail`) |
| `worker.py` | lädt Exposés nach und trägt die Ist-Miete ein; abbrechbar, macht beim nächsten Start weiter |
| `static/` | Oberfläche (HTML/CSS/JS, kein Framework) |
| `scripts/ingest.py` | liest zwischengespeicherte Seiten in die Datenbank |
| `scripts/add_dad.py` | trägt die 14 Wohnungen ein, die Papa am 06./08.08. geschickt hat |
| `scripts/pipeline.sh` | Erhebung abwarten → einlesen → Mieten nachladen |
| `data/wohnungen.db` | SQLite; überlebt jeden Neustart |

## Das Modell

Voreingestellt sind exakt Papas Annahmen: 20 % Eigenkapital, 4 % Zins + 2 % Tilgung,
42,5 % Steuersatz, 75 % Gebäudeanteil für die AfA, Notar 1,5 %, Grundbuch 0,5 %.
Ergänzt pro Objekt: Grunderwerbsteuer nach Bundesland (Bayern 3,5 %, Sachsen 5,5 %,
NRW 6,5 %), Courtage aus dem Inserat, AfA 2,5 % vor 1925 / 3 % ab 2023 / sonst 2 %.

Alle acht Annahmen sind in der Oberfläche unter **Annahmen** als Regler verstellbar
und rechnen sofort alles neu.

`Cashflow positiv = Geld bleibt bei dir.` In Papas Excel ist das Vorzeichen umgekehrt.

## Datenqualität

Eine Wohnung erscheint nur dann mit Rendite, wenn im Inserat eine **Kaltmiete
wörtlich ausgewiesen** ist. Der Beleg steht unter „Rechnung ansehen“ im Klartext.

Der Parser bevorzugt die am eindeutigsten als Kaltmiete bezeichnete Zahl — nicht die
größte. Das ist wichtig, weil bei „Mieteinnahmen 484 € (297 € Kaltmiete + 187 €
Nebenkosten)“ die größte Zahl die Warmmiete ist. Jahresangaben („Jahresnettokaltmiete
3.211,20 €“) werden durch 12 geteilt, egal ob der Hinweis vor oder hinter der Zahl steht.
Mieten außerhalb von 2–30 €/m² gelten als Parserfehler und werden verworfen.

Wo das Inserat kein Hausgeld nennt, wird mit 4 €/m² gerechnet; diese Objekte sind
mit `Hausgeld geschätzt` markiert. Instandhaltungsrücklage, Protokolle der
Eigentümerversammlung und Alter des Mietvertrags stehen nie im Inserat und müssen
beim Verwalter angefragt werden.

## Daten aktualisieren

```bash
python3 scripts/ingest.py     # zwischengespeicherte Seiten einlesen
python3 worker.py 500         # 500 Exposés nachladen
python3 worker.py             # alles Offene abarbeiten
```

Der Worker arbeitet Papas Objekte zuerst ab, danach die günstigsten je m² —
dort sitzt die Rendite. Wird ImmoScout langsamer, wartet er von selbst länger.
