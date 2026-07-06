# Obogatitev podatkov

## Cilj

Trenutni seznam jobov in podjetij zelimo obogatiti do te mere, da lahko hitro ocenimo:

- katera podjetja so zanimiva za nas
- kateri tip ponudbe je primeren za določeno podjetje
- kdo je kontaktna oseba znotraj podjetja

## Podatki, ki jih zelimo pripeljati

### Informacije o podjetjih

Kaj zelimo dobiti:

- kratek opis podjetja
- velikost podjetja
- starost podjetja
- tip podjetja: produktno podjetje / agencija-consulting / tradicionalno podjetje
- funding/investicije
- AI/tech-forward signal

Predvideni viri: LLM powered websearch

Zakaj rabimo:
- filtriranje in prioritizacija podjetij

### Informacije iz job descriptiona

Kaj zelimo dobiti:

- celoten opis vloge
- remote/hybrid/onsite signal
- ali gre za prvega AI cloveka ali del obstojece ekipe
- ali gre za interni razvoj ali delo za zunanje stranke

Predvideni viri: ATS/job pages, karierne strani, LinkedIn/search rezultati

Zakaj rabimo:

- razumevanje dejanske potrebe
- izbira prave ponudbe za podjetje


### Kontakti

Kaj zelimo dobiti:

- hiring manager, CTO, CEO/founder
- Head of AI/Data/Engineering
- email ali LinkedIn profil

Predvideni viri: Job description in LLM powered websearch

Zakaj rabimo:

- najti konkreten entry point za outreach

## Izhod

Za vsak zanimiv company/job par zelimo dobiti:

- prioriteto
- predlagan tip ponudbe
- kontaktno osebo
- razlog, zakaj jim pisemo

## Opombe

- Interni razvoj vs. delo za zunanje stranke je pomemben signal, ker loci potencialne stranke od potencialnih partnerjev.
- Remote/hybrid/onsite signal je zelo pomemben, ker mocno vpliva na moznost sodelovanja.
- Funding in starost podjetja sta dober proxy za rast, odprtost in verjetnost, da potrebujejo zunanjo pomoc.
- Po prvem krogu outreacha filtre izboljsamo glede na odzive in dejanske rezultate.
- Smiselno bi bilo narediti se (llm) reserach o tem kakšen tip podjetji je bolj odprt za sodelovanje z zunanjimi izvajalci.
