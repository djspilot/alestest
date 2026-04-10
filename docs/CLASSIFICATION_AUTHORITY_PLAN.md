# Classification Authority Plan

Doel: leg vast hoe de manufacturing pipeline vanaf classificatie tot XML-export gecontroleerd wordt, zodat projectafspraken niet ongemerkt door fallbacks of late overrides kunnen worden overschreven.

Dit document is bedoeld als terugkomdocument voor de volgende fase:
- eerst bronautoriteit en validatie per stap vastleggen;
- daarna bestaande documentatie opschonen en harmoniseren;
- daarna pas bredere refactors doorvoeren.

---

## 1. Status en bedoeling

Dit plan is een audit- en uitvoeringsplan, geen implementatieverslag.

Het plan moet drie dingen borgen:
- per pipelinefase is duidelijk welke bron leidend is;
- per XML-veld is duidelijk welke fallback wel en niet mag ingrijpen;
- tests valideren niet alleen het eindresultaat, maar ook het pad en de bron van dat resultaat.

Dit document wordt de tijdelijke kapstok voor alle vervolgafspraken over:
- classificatie;
- plaat-featurevelden;
- profiel-featurevelden;
- unfold-velden;
- exportautoriteit.

Inventarisatie van de huidige documentset staat in:
- `docs/DOCUMENTATION_CLEANUP_MATRIX.md`

---

## 2. Kernprobleem

De huidige pipeline bevat op meerdere plaatsen geldige technische fallbacks. Die zijn functioneel nuttig, maar niet overal gekoppeld aan een expliciete bronrangorde.

Daardoor kan het volgende gebeuren:
- een semantisch correcte waarde wordt vroeg bepaald;
- een latere geometrische of exportfallback ziet een andere waarde;
- de latere waarde overschrijft de eerdere zonder dat duidelijk is of dat contractueel toegestaan was.

De concrete holecount-fix heeft dit probleem voor `Sheet_NrHoles` al zichtbaar gemaakt:
- semantische telling was correct;
- een latere DXF-route kon die alsnog verhogen;
- oorzaak was niet de detectieregel zelf, maar ontbrekende bronautoriteit in de exportlaag.

De conclusie voor het hele project is:

> Niet elke fallback is fout, maar elke fallback moet ondergeschikt zijn aan een expliciet gedefinieerde primaire bron.

---

## 3. Scope van dit plan

Deze volgorde is leidend voor de audit:

1. classificatie;
2. featuredetectie voor plaatdelen;
3. featuredetectie voor profielen;
4. unfold en afgeleide vlakke maatvoering;
5. XML-export als finale beslislaag.

De audit begint dus bewust vanaf stap 2 van de manufacturing pipeline en loopt door tot de uiteindelijke XML.

---

## 4. Hoofdprincipe: bronautoriteit per veld

Voor elk kritisch veld wordt vastgelegd:
- primaire bron;
- toegestane fallback-bronnen;
- verboden override-bronnen;
- test die dit afdwingt.

### 4.1 Veldtypen

We maken onderscheid tussen twee soorten velden:

### Semantische velden
- classificatie;
- subtype;
- `Sheet_NrHoles`;
- `Sheet_ThreadedHoles`;
- `Sheet_CountersunkHoles`;
- profiel-holecountvelden.

Regel:

> Een lagere geometrische of visual fallback mag een semantisch vastgesteld veld niet verbreden of verhogen.

### Geometrische velden
- `Sheet_BoxX`, `Sheet_BoxY`;
- `Sheet_OuterContour`;
- `Sheet_TotalContour`;
- `Sheet_AreaNoHoles`;
- unfold-dimensies;
- profielafmetingen.

Regel:

> Geometrische fallbacks mogen verfijnen, maar alleen als de bronhiërarchie en plausibility-regels dat toestaan.

### 4.2 Voorlopige autoriteitsvolgorde

Deze volgorde wordt gebruikt als werkmodel voor vervolgimplementatie en tests:

1. `trusted_reference`
2. `semantic_contract`
3. `cut_features`
4. `unfold_verified`
5. `cross_section`
6. `dxf_geometry`
7. `part_analyzer`
8. `visual_debug`
9. `derived_fallback`

Werkregel:

> Een bron met lagere autoriteit mag een veld met hogere autoriteit niet overschrijven.

---

## 5. Auditvolgorde per fase

## Fase A - Classificatie

Doel:
- vastleggen welke bron `final_class`, `subtype` en `fallthrough` bepaalt;
- voorkomen dat export- of featurelogica achteraf impliciet een classificatiebeslissing herinterpreteert.

Te controleren:
- welke gate of regel de classificatie won;
- of `fallthrough` terecht was;
- of latere code alleen leest of ook inhoudelijk herbeslist.

Minimale velden:
- `final_class`
- `subtype`
- `fallthrough`
- trace van winnende regel

Acceptatie:
- niet alleen eindklasse klopt;
- ook het pad naar die eindklasse klopt.

## Fase B - Plaat-features

Doel:
- semantische plaatvelden contractueel vastzetten;
- voorkomen dat visual, DXF of part-analyzer later semantische waarden verbreedt.

Minimale velden:
- `Sheet_NrHoles`
- `Sheet_HoleRadii`
- `Sheet_ThreadedHoles`
- `Sheet_CountersunkHoles`
- `Sheet_CountersunkAngles`
- `Sheet_Thickness`
- `Sheet_BoxX`
- `Sheet_BoxY`
- `Sheet_OuterContour`
- `Sheet_TotalContour`
- `Sheet_AreaNoHoles`

Specifieke aandacht:
- DXF mag contour/area helpen bepalen;
- DXF mag semantische holecount niet verhogen als een semantische bron al heeft beslist.

## Fase C - Profiel-features

Doel:
- profielafmetingen en profielgaten aan een vaste bronrangorde koppelen.

Minimale velden:
- `Tube_Type`
- `Tube_Thickness`
- `Tube_Width`
- `Tube_Height`
- `Tube_Length`
- `Tube_NrHoles`
- `Tube_HoleContours`
- `Tube_HoleRadii`

Specifieke aandacht:
- profiel-holevelden mogen niet impliciet worden afgeleid uit alleen bbox of generieke profielherkenning;
- als `cut_features_for_profile` de bron is, moet die voor holetelling leidend zijn.

## Fase D - Unfold

Doel:
- onderscheid maken tussen echte, productieleidende unfold-data en technische fallbacks.

Minimale velden:
- `Sheet_UnfoldSuccess`
- `Sheet_BoxX`
- `Sheet_BoxY`
- `Sheet_FilePathDXF`
- bendvelden

Specifieke aandacht:
- theoretical of technische fallback mag niet dezelfde autoriteit krijgen als echte unfold;
- implausible unfold-dimensies mogen niet stil geaccepteerd worden.

## Fase E - XML-export

Doel:
- XML-export mag geen losse write-layer zijn, maar moet finale bronautoriteit afdwingen.

Werkregel:
- alle kritieke velden krijgen een centrale setter of beslislaag;
- alle geweigerde overrides worden gelogd;
- reference-values lopen uiteindelijk door dezelfde autoriteitsregels.

---

## 6. Minimale authority-matrix

| Veld | Primaire bron | Toegestane fallback | Mag niet overschreven worden door |
|---|---|---|---|
| `final_class` | classificatiebeslissing | fallback-gate in dezelfde beslisboom | export of featurelaag |
| `Sheet_NrHoles` | semantiek uit `cut_features` of VPS | alleen bij ontbrekende primaire bron | DXF, visual, part_analyzer |
| `Sheet_ThreadedHoles` | semantische holebron | `cut_features` | visual hole typing |
| `Sheet_CountersunkHoles` | semantische holebron | `cut_features` | visual hole typing |
| `Sheet_BoxX`, `Sheet_BoxY` vlak | referentie of hoofdgeometrie | DXF of cut-features | visual/debug |
| `Sheet_BoxX`, `Sheet_BoxY` gezet | unfold of trusted reference | cross-section | implausible unfold/theoretical fallback |
| `Sheet_UnfoldSuccess` | echte unfold-status | geen inhoudelijke fallback | afgeleide geometrische schatting |
| `Tube_Type` | profielclassificatie of profiel-featureextractie | BOM-description fallback als label | exportheuristiek |
| `Tube_Thickness` | profiel-featureextractie | trusted reference | bbox-only afleiding |
| `Tube_NrHoles` | profiel cut-features | alleen bij ontbrekende primaire bron | generieke profielheuristiek |

Deze tabel is niet definitief compleet. Zij vormt de eerste, werkbare baseline.

---

## 7. Teststrategie

Per testcase worden twee dingen gevalideerd:

1. welk pad werd genomen;
2. welke bron leverde de finale veldwaarde.

Dus:
- een test is niet groen als alleen de eindwaarde toevallig klopt;
- een test is pas groen als ook de juiste autoriteitsregel is gevolgd.

### 7.1 Testgroepen

1. classificatie-contracttests
2. plaatveld-authority-tests
3. profielveld-authority-tests
4. unfold-authority-tests
5. XML-regressietests op veldniveau

### 7.2 Minimale conflictcases

Voor semantische plaatvelden:
- semantische gaten < DXF-gaten;
- semantische gaten < visual-gaten;
- semantische gaten < part-analyzer-gaten;
- expected result: semantische bron blijft leidend.

Voor unfold:
- echte unfold success;
- cross-section fallback;
- failed unfold met technische fallback;
- expected result: technische fallback blijft herkenbaar als fallback en krijgt geen stille productiestatus.

Voor profielgaten:
- profiel zonder gaten;
- profiel met gaten;
- profiel met mismatch tussen cut-features en generieke profielinfo;
- expected result: primaire holebron wint.

---

## 8. Uitvoeringsvolgorde

Deze volgorde is bedoeld om zonder big-bang refactor te werken.

### Stap 1
- authority-regels formaliseren voor semantische plaat-holevelden.

### Stap 2
- tests toevoegen die expliciet bewijzen dat lagere bronnen deze velden niet meer kunnen overrulen.

### Stap 3
- unfold-status en unfold-dimensies onder dezelfde systematiek brengen.

### Stap 4
- profiel-holevelden onder dezelfde systematiek brengen.

### Stap 5
- reference-values opnemen in dezelfde centrale autoriteitslaag in plaats van als aparte bypass.

### Stap 6
- identity- en naamvelden meenemen.

---

## 9. Vervolg: documentatie opschonen

Zodra dit plan als basis is geaccepteerd, volgt een documentatiesanering.

Doel van die opschoning:
- één bron voor classificatieafspraken;
- één bron voor hole-semantiek;
- één bron voor unfold-betekenis en fallbackstatus;
- archiefdocumenten alleen nog als historische context, niet als levende norm.

Documentatie-opruimregels:
- actieve afspraken verplaatsen naar actuele docs;
- handovers markeren als historisch of migreren;
- tegenstrijdige afspraken expliciet samenvoegen of afvoeren;
- per afspraak vastleggen: eigenaar, datum, geldigheid, broncode-koppeling.

---

## 10. Beslispunten voor later

Deze punten worden later expliciet beslist, niet impliciet in code:
- welke reference XML als `trusted_reference` telt;
- welke fallback alleen technisch is en welke productieleidend mag zijn;
- welke XML-velden per fase hard verplicht zijn;
- welke tests release blockers zijn.

---

## 11. Werkafspraak

Totdat de documentatiesanering is afgerond, geldt dit document als werkdocument voor:
- bronautoriteit;
- auditvolgorde;
- teststrategie;
- interpretatie van fallbackconflicten.

Nieuwe afspraken over classificatie of veldautoriteit moeten eerst hier worden toegevoegd of hiernaar worden vertaald.