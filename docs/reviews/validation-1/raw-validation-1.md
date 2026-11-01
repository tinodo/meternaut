> Saved as received on 2026-11-01, in Dutch: two reports from an independent AI reviewer, the first on the knowledge and learning and the testing and evaluation documents, the second on the rest of the design and the tools. The reviewer read a snapshot taken at 16:15 UTC, before commit `ad958b9` (17:02 UTC). Only the machine path prefix has been removed. What was done about each finding is in the [disposition](disposition.md).

Zes productkritische hiaten
Een “kleine trial” is onterecht per definitie R1.
docs\design\04-knowledge-and-learning.md:236: “a trial is always an R1 change: small and reversible”.
Tegenvoorbeeld: capaciteit van een productie-dienst omlaag schalen is technisch omkeerbaar, maar veroorzaakt al time-outs of dataverlies vóór rollback. Een kostenplafond begrenst geen bedrijfsimpact.
Gevolg: leren kan een te lichte goedkeuringsroute worden. Classificeer trials op blast radius, herstelbaarheid én guard-latency, niet op het label “trial”.
bill-observed kan te gemakkelijk een passend model verwarren met een juiste verklaring.
...\04-knowledge-and-learning.md:222-224: “Small, stable residuals on a closed billing period earn bill-observed”; dezelfde simulator mag waar nodig “trailing billed usage” gebruiken.
Tegenvoorbeeld: een profiel wordt op eerdere stabiele facturen passend gemaakt; de volgende maand lijkt te kloppen, maar een verborgen minimum, korting of gekoppelde meter is verkeerd gemodelleerd. Bij schaalverandering faalt het.
Gevolg: een foutieve claim krijgt een sterk evidencelabel. Vereis een vóór de validatiecyclus bevroren profiel, vooraf vastgelegde foutmarge en ten minste één out-of-time validatieperiode voordat promotie plaatsvindt.
Causaliteit is eerlijk erkend, maar nog niet operationeel gespecificeerd.
...\04-knowledge-and-learning.md:140: “Evidence is not causality”; :232 laat uitkomsten ranges per Action-familie bijstellen na normalisatie voor load of “untouched look-alikes”.
Tegenvoorbeeld: een resize, lagere vraag en een onderhandelde korting vallen samen. Een willekeurige vergelijkingsresource is geen valide controle. De besparing wordt dan aan de Action toegeschreven en toekomstige ranges worden te optimistisch.
Gevolg: kalibratie, regret en autonomie kunnen op selectieve, gunstige observaties rusten. Leg vooraf vast wanneer een controle vergelijkbaar is, welke confounders uitsluiten, wanneer de uitkomst slechts “onbepaald” is en wanneer zij nooit Action-familie-evidence mag worden.
Van één Case naar een estate-brede Detector is te grote generalisatie zonder promotiedrempel.
...\04-knowledge-and-learning.md:240: “One Case finds this in one estate, and the Detector looks in all of them”; :262 bevat goede mitigaties: back-test, shadow en blinde steekproeven.
Tegenvoorbeeld: een observatie komt door één organisatie-specifieke retentie- of migratiepraktijk. De Detector produceert elders veel plausibele maar irrelevante leads.
Gevolg: aandachtsschuld, vertekende feedback en minder vertrouwen, ook al voert de Detector zelf niets uit. Definieer vóór actieve promotie minimumaantallen onafhankelijke scopes, vereiste shadow-precisie, maximale decoy-rate en een expliciet criterium voor “alleen lokaal bruikbaar”.
Cold start is voorzichtig beschreven, maar het productgedrag en succescriterium ontbreken.
...\04-knowledge-and-learning.md:266-278 zegt terecht dat purpose inferentieel is, ritme een volledige cyclus vereist en onbekende spend op de Unexplained Spend list blijft.
Tegenvoorbeeld: een nieuw estate heeft dertig dagen historie, slechte tags en een jaarlijkse piek. Het systeem kan correct abstineren, maar er is geen meetbare grens voor wanneer het van observeren naar betrouwbaar adviseren mag.
Gevolg: de verwachte waarde in de eerste maanden is onduidelijk; druk om toch aanbevelingen te doen creëert precies de verkeerde richting. Definieer een cold-startmodus met expliciete dekking, ontbrekende-data-ratio, minimumritme en een verbod op besparingsclaims totdat die drempels gehaald zijn.
De evaluatie toetst geheugenverbetering degelijk, maar nog onvoldoende prospectief autonome ontdekking.
...\08-testing-and-evaluation.md:30-41 bouwt gold/sealed sets uit bekende, brongeverifieerde traps; :54-56 voert terecht frozen-versus-updated uit met leakage-audit. Dat bewijst verbetering ten opzichte van bevroren geheugen op die testwereld.
Tegenvoorbeeld: de basis-LLM kent het mechanisme al, of een retrievalverbetering vindt bestaande kennis beter. De test kan winnen zonder dat het systeem zelfstandig een nieuw kostmechanisme heeft geleerd.
Gevolg: “learning” kan feitelijk betere RAG op bekende patronen betekenen. Dit is geen bewezen fout; het huidige ontwerp erkent de beperkingen. Maar het ontbrekende proofpoint is essentieel.
Minimaal overtuigend demonstratiepad
Voer prospectief, volledig binnen de eigen tenant en zonder testresources, een vooraf geregistreerde proef uit met meerdere nieuwe Azure-servicewijzigingen of meters:

Isoleer vóór de aankondiging een tijdgestempelde snapshot van Atlas, prompts, tools en priors; houd de latere service/meter en onafhankelijke antwoordset buiten bereik.
Laat alleen de updated-arm publieke bronnen, prijsdiffs en later bestaande factuurdata verwerken; de frozen-arm krijgt niets nieuws. Gebruik exact gelijke modellen, tools en budgetten.
Beoordeel op geheime, later gesloten factuurperioden van reeds bestaande workloads of eigenaar-goedgekeurde reversibele wijzigingen: meterherkenning, scope, voorspelde range, juiste abstinentie en schadelijke decoys.
Laat een onafhankelijke menselijke reviewer bronketen en causale kwalificatie beoordelen; een factuurbeweg­ing alleen is geen oorzakelijk succes.
Vergelijk met retrieval-only, Advisor-only en frozen memory. Claim learning alleen bij vooraf bepaalde verbetering over meerdere onafhankelijke services, zonder slechtere decoy-/harm-score.
De ontwerpkoers is dus verdedigbaar, maar de learning-claim moet pas als bewezen gelden na dit soort prospectieve, causale en generaliseerbare demonstratie.


Used 25 tools
Onafhankelijke review (alleen-lezen): scope 01, 02, 05, 06, 09–14 en tools
Bronpaden zijn relatief aan de opname van 2026-11-01 16:15 UTC (de snapshot van de bronmap). tools/ bevat de live cost-model.py en fetch-prices.py; ik heb geen van beide uitgevoerd.

Kernoordeel: de richting is niet verkeerd, de volgorde en de meetbaarheid wel. Je vermoeden klopt gedeeltelijk. Het ontwerp is geoptimaliseerd voor veilig handelen en bedrijven, voordat bewezen is dat het iets vindt wat Advisor of vaste regels missen.

1. Wat goed is en trouw aan de brief
Het is geen Advisor-wrapper. 01-goals-and-scope.md:9: "the scarce thing is not detection. It is knowledge". Advisor is een lead en een baseline om te verslaan (01:53).
Veiligheid zit in de structuur. 06-security-and-governance.md:12: "An agent can be talked into anything, so assume it will be: no agent holds a write role." Daarnaast doen workflows de besturing (02-architecture.md:37), is de runner de enige schrijver, en is elke goedkeuring gebonden, eenmalig en fail-closed (06:129-141). Dat past bij human-in-the-loop en bij de inkoopformulering uit de brief (01:44).
De grens van het leren is eerlijk benoemd. 12-decisions.md:103: "a meter nobody has used cannot be discovered this way". Leren kost geen Azure-resources, wel tokens.
Agreement en access zijn feiten om te ontdekken. Het document zegt (14-agreements-and-access.md:7-11): "Probe, don't ask", "Label, don't pretend", "Hand over, don't fail". Er is een prijsvolgorde (14:51-55) en vier kopen-paden (14:112-117). De partnerclaim (14:19: retailtarieven, kostenzichtbaarheid standaard uit) heb ik vandaag tegen publieke Microsoft Learn gecontroleerd en die klopt.
Elke veiligheidsmaatregel noemt zijn eigen grens (06:268-279). Het prijsgereedschap is degelijk: exacte selectors die stoppen bij dubbelzinnigheid (tools/cost-model.py:5-7), een self-test, en seeds die als seeds zijn gelabeld (10-cost-and-finops.md:7).
De fasevolgorde in principe: lezen, aanbevelen, handelen, autonomie (13-roadmap.md:11-16). Elke proof point heeft een fallback.
2. Vijf werkelijke risico's
R1. Volgorde en profiel: de eerste echte waardetest staat niet in een gedefinieerd profiel (bewezen inconsistentie).

Fase 1 eist "explained spend measured on a first estate" en een "Monday digest to the FinOps lead" (13:12). P4 vergelijkt probes met het portal op pilotestates (13:27).
Evaluate is "synthetic data" met "No role on any production scope" (02:137,142). Echte estates lezen is Operate.
Operate komt pas in fase 2 (13:13: "the first estate runs in the Operate profile"), net als Diplomat, e-mail en Teams. Wisselen van profiel is "a new account" (02:145).
De fase-1-exit bundelt vier proof points, een injectiesuite, een sealed set en "updated memory beats frozen memory". Dat is een onderzoeksprotocol (08-testing-and-evaluation.md:54) als poortwachter van een hele fase.
Hypothese: de kernvraag ("ontdekt het systeem generaliserend waarde?") staat achter P1, P2, P9, een dev-deploy en een isolatietest, en dan nog in één grote bundel.
Gerelateerd: 13:20 zegt "a failed test changes a choice, not the project", maar de P6-fallback is "Narrower scope; more Detectors" (13:29). Dat is de regelboek-uitkomst die de brief afwijst. Een mislukte P6 is dus een northstar-beslissing, geen tuning.
R2. Componentenstapel op het kritieke pad (hypothese, onderbouwd met telling).

De telling: 5 hosted agents met 10 rollen, 7 workflows, 5 Function-apps in twee talen, 11 tools, 12 contracten (6 × dev/prod), 8 Cosmos-containers, 3 queues, 11 private endpoints (02:44-61,127,141; 05:27-36,56).
Dit is geen governance-bloat: de schrijfketen rechtvaardigt het. De vraag is wat vóór de eerste waarde nodig is, en dat is een fractie.
Symptoom van het kostenmodel zelf: de vaste kosten bij Pilot zijn 161 van 227 EUR (10:14), en "The plumbing costs more than the thinking at small scale." (10:119).
Er is nergens een dunne verticale slice of "time to first value" gedefinieerd; mijn grep door docs/design vindt het concept niet.
R3. Onboarding en bedrijfsinspanning zijn niet gemodelleerd (hypothese; één punt bewezen).

Vereist is "A platform team that can run Azure Functions and Foundry; a FinOps lead; … Atlas and security reviewers" (01:103). Verder zijn er vijf groepen, een rota met vijf out-of-hours-pagers (09-delivery-and-operations.md:116-124), kwartaalreviews (09:152) en zeven onboardingstappen (09:191-201).
Bewezen: het model telt alleen eigenaarminuten (5 per case) en Atlas-reviewminuten (tools/cost-model.py:95). Platform-, security- en FinOps-uren ontbreken, ook in uren (10:143).
De doelentabel (01:13-21) heeft geen doel voor onboardinginspanning of tijd tot eerste gevalideerde bevinding.
De Pilot-break-even van 0,62 % (10:14) is alleen cloudkosten. Eén platformdag kost waarschijnlijk meer dan de hele maandrekening van 311 EUR. Dit is mijn schatting, niet uit de repo.
R4. Betekenis van prijzen, billing en access (risico zit in de interpretatie, niet in de aanpak).

Een app-team met alleen subscription-toegang rekent vaak met lijst- of billed-prijzen, en bij een partner met retailtarieven. Daar zijn besparingen "estimates until the partner supplies its rates or an invoice settles them" (14:145).
"Verified net savings" (10:124) hangt af van EffectiveCost, BilledCost en reconciliatie. Maar "Reconciliation proves the lake matches the bill, not that the bill is right." (05:201).
De Strategy-workflow heeft reservation- en savings-plandata nodig die rollen op tenantniveau vragen (05:87). Fase 4 draait dus op data die de gewone reader-identiteit niet ziet. Dat is een hypothese.
Bewezen kleine overstatement: F11 zegt "every Azure agreement and every level of access" (01:77), terwijl 14:147-148 classic CSP en sponsorship uitsluit.
De probe toont wat de identiteit nu kan, niet wat de agreement toestaat (14:144). Dat staat er eerlijk in; het betekent dat een ontbrekende rol als ontbrekende functie leest.
R5. Schijnzekerheid in het kostenmodel (grotendeels bewezen).

Funnel ontbreekt. Het model prijst "One case that reaches an owner" (10:34; tools/cost-model.py:50,222-236). Onderzoeken die sneuvelen of parkeren niet. Toch eindigt een weerlegde Case als Lesson (03-agents-and-workflows.md:140), en 3 mislukte pogingen parkeren een Case (03:50). Een grep naar attrition of funnel in het script geeft niets. De enige stress is "Investigations twice as long" (+26 EUR bij Pilot, 10:102).
Break-even is een vrije parameter gedeeld door een kostentotaal. breakeven_pct = total / spend (tools/cost-model.py:385), met spend als scenarioparameter van 10k, 20k en 25k EUR per subscription (:37-47) en zonder besparingskant. Het document erkent het zelf: "most of that spend cannot be saved" (10:124). De 0,62 / 0,08 / 0,02 % lijkt precies maar zegt niets over opbrengst.
Register en model wijken af. Het register zegt "Terra default, Sol to escalate" (11-technology-register.md:30). De headline prijst alle vier de reason-rollen op GPT-6.1 Sol (10:49). Het effect is klein (−15 / −129 / −1.274 EUR, 10:109).
Vier vaste bedragen zijn handmatig geschat (tools/cost-model.py:99-104), waarvan PII-detectie UNVERIFIED.
Cloudkosten zijn niet het projectrisico: Pilot is 311 EUR tegen 50.000 EUR beheerd. De technische precisie zit op de minst belangrijke onzekerheid. De echte onzekerheden zijn opbrengst, uitval en mensuren, en die ontbreken. Dit is een oordeel, geen meting.
3. Wat de eerstvolgende demonstratie moet bewijzen
Eén verticale slice op één referentie-toegangsniveau, bij voorkeur EA of MCA met billing-reader. Verminderde toegang moet als aangetoond gedrag worden getoond, niet als gelijkwaardig pad. De slice bewijst vijf dingen:

De hub-route werkt. Een hosted agent bereikt model en tool via de hub, een direct modelcall faalt en een agent zonder rollen kan de estate niet lezen (P1).
De capability profile klopt met het portal voor die scope, met een kostenlake via Cost Details of exports (een P4-segment).
Leren is aantoonbaar, op echte of replay-bills. Voor een dienst die na het geheugensnapshot is gelanceerd, moet "updated" beter scoren dan "frozen" en dan Advisor- of retrieval-baselines, met rustige decoys. Daarbij hoort de voorspelfout van de eerste factuur (P6, 13:29).
Eén aanbeveling is door een echte eigenaar als waar en waardevol bevestigd, geprijsd op een benoemde price basis.
Cost per case en cost per bevestigde bevinding komen uit hublogs, inclusief weerlegde onderzoeken en inclusief mensentijd (P10 uitgebreid).
Let op bij P6: het gold is "79 source-verified traps … none yet confirmed by a bill" (08:41), terwijl de bank zelf 78 van 145 noemt (docs/research/cost-trap-bank.md:5). Dat is een telverschil om door te geven aan de reviewer van 08. Belangrijker: P6 meet herontdekken van gedocumenteerde mechanismen, niet bewezen besparing. Een door de bill bevestigde bevinding is een aparte, latere meetlat.

Mag later, zonder de northstar te amputeren: approvals, runner, credentials, purchase-identiteit, Strategy en R3, Teams-bot (web of e-mail eerst), FinOps-hub-adapter, Durable-backend en Search-keuze (P5), opsplitsing van agents en contracten (begin met 2–3 contracten), tweede regio, voice en avatar, open contributies. Fase 3 meet "first savings verified" pas na de hele actiestack (13:14). Eigenaren kunnen eerder zelf handelen. Meet dus al in fase 2 of de Auditor bevestigde besparingen in de bill ziet.

Niet inleveren: frozen-versus-updated-leertest, menselijke Atlas-merge, hub-only, price-basis-label, "geen agent schrijft".

4. Richting: behouden, en vier dingen bijsturen
Behouden: de architectuurprincipes, de northstar en de governance. Ze zijn evenredig aan een systeem dat kan schrijven en kopen.

Bijsturen:

Voeg fase 1a toe met de slice hierboven als exit. Fase 1b volgt daarna. Definieer vóór Operate een expliciet leesprofiel voor een echte estate, of verplaats het wisselmoment. Los zo R1 op.
Leg een beslisregel vast voor mislukte P6: zie het als northstar-beslissing, niet als "meer Detectors".
Voeg doelen en metrics toe: tijd tot eerste gevalideerde bevinding, cost per bevestigde besparing, platformuren per maand.
Maak het kostenmodel eerlijker: funnel-parameter, mensenuren, break-even vervangen door een drempel op yield, en F11 plus de Terra/Sol-mismatch rechtzetten.
Verificatiestatus. Platformfeiten komen uit de repo-bronnen (datum 2026-11-01), behalve de partnerclaim, die ik tegen Learn heb gecontroleerd. De rest, zoals preview- en GA-statussen en de GPT-6.x-prijzen, heb ik niet onafhankelijk geverifieerd. Ik heb geen product-privé inhoud buiten de omgeving gestuurd. Dit zijn de bestanden die ik niet heb beoordeeld: 03, 04, 07, 08 (behalve de cross-references hierboven) en de ideation- en reviewbestanden.