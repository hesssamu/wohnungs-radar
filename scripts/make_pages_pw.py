#!/usr/bin/env python3
"""Erzeugt eine starke Passphrase fuer die oeffentliche Pages-Fassung."""
import os, secrets

WORDS = """anker birke blitz brunnen buche dachs delfin distel eiche eule falke feder
feuer fichte flieder forelle fuchs garten gipfel granit hafen hasel heide hirsch holunder
igel insel kastanie kiefer klee komet koralle kranich lerche libelle linde luchs
marder meise moewe nebel nelke otter pappel pfau quelle rabe reiher riff robbe
salbei schilf schwalbe segel silber specht stern storch strand tanne taube thymian
ulme wacholder waldkauz welle wiesel wolke zeder zinne anemone ahorn amsel bernstein
biber birne dohle drossel eibe elster erle espe farn finken flachs ginster granat
grille hummel iltis jasmin kiesel kolibri krokus kupfer lachs lavendel lupine malve
mohn moos muschel nerz nussbaum opal orchidee pilz platane primel quarz reh rose
salzsee sanddorn schiefer schwan seerose sperber spinell steinbock tulpe uhu veilchen
vogelbeere wachtel weide zaunkoenig zeisig zypresse""".split()

p = os.path.expanduser("~/.config/secrets/wohnungs-radar.env")
lines = []
if os.path.exists(p):
    lines = [l.rstrip("\n") for l in open(p) if not l.startswith("PAGES_PASS=")]

pw = "-".join(secrets.choice(WORDS) for _ in range(6)) + "-" + str(secrets.randbelow(90) + 10)
lines.append(f"PAGES_PASS={pw}")
with open(p, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(p, 0o600)

import math
bits = 6 * math.log2(len(WORDS)) + math.log2(90)
print(f"Passphrase erzeugt: {len(WORDS)} Woerter, 6 Stellen + Zahl -> {bits:.0f} Bit Entropie")
print(pw)
