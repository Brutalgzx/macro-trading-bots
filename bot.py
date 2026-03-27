import os
import logging
import asyncio
from datetime import datetime
from anthropic import Anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# ─────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
CHAT_ID        = os.environ.get("CHAT_ID")
TIMEZONE       = os.environ.get("TIMEZONE", "Europe/Paris")

client = Anthropic(api_key=ANTHROPIC_KEY)

# ─────────────────────────────────────────
#  PROMPT SYSTÈME INSTITUTIONNEL
# ─────────────────────────────────────────
SYSTEM_PROMPT = """Tu es un analyste macro-financier institutionnel spécialisé en trading (SMC, macro, flux de liquidité).
Tu penses comme un hedge fund, pas comme un retail.

RÈGLES ABSOLUES :
- Jamais de réponse vague ou générale — chaque affirmation doit être logique, sourcée, exploitable
- Format Markdown Telegram : **gras**, _italique_, `code`, tableaux avec | pipes |
- Rechercher les prix et données en temps réel avant de répondre
- CONSENSUS : uniquement sources publiques vérifiables (Goldman Sachs, JPMorgan, BNP Paribas, Crédit Agricole, ING, Deutsche Bank, FMI, CFTC, FactSet, Reuters, Bloomberg). Si non disponible → écrire exactement "Consensus non disponible publiquement" — JAMAIS inventer un chiffre
- Chaque analyse doit contenir : prix live, biais directionnel tranché, niveaux clés, consensus si disponible, timing optimal

FRAMEWORK 4 COUCHES (obligatoire dans chaque analyse) :
1. Fonda → direction (macro, banques centrales, géopolitique)
2. SMC → zones (niveaux de prix, liquidité, equal highs/lows, POI H4)
3. Psychologie → pièges (COT, sentiment, retail vs institutions)
4. Timing → exécution (avant/pendant/après news)

CORRÉLATIONS FONDAMENTALES :
- DXY ↑ → Or ↓, EUR/USD ↓, BTC tend ↓, Matières premières ↓
- DXY ↓ → Or ↑, EUR/USD ↑, BTC tend ↑, Risk-on global
- Taux réels US ↑ → Or ↓ fort (concurrent direct T-bonds)
- Taux réels US ↓ → Or ↑ fort (store of value supérieur)
- Risk-off → Or ↑, Dollar ↑, Yen ↑, Indices ↓, Crypto ↓
- Surprise hawkish (réel > forecast) → USD ↑, Or ↓, Indices pression
- Surprise dovish (réel < forecast) → USD ↓, Or ↑, Risk-on généralisé

RÈGLE TIMING (non négociable) :
- Avant news = préparation : zones H4, equal highs/lows, PAS d'exécution
- Pendant news = manipulation : faux breakouts, spreads larges, NE PAS entrer sur la première bougie
- Après news = opportunité : cassure structure confirmée + retracement + alignement fonda = entrée optimale

RÈGLE COT :
- Non-commerciaux > 75% longs = extrême haussier = danger de retournement imminent
- Non-commerciaux < 35% longs = extrême baissier = accumulation institutionnelle probable
- Retail FOMO + extrême COT = les institutions distribuent dans l'euphorie

ACTIFS TRADÉS (filtre strict calendrier) : XAU/USD, DXY, EUR/USD, S&P 500, BTC/ETH, Pétrole WTI/Brent

ANNONCES INCLUSES DANS LE FILTRE : CPI/Core CPI US, NFP + chômage, PCE Core/Headline, FOMC décision + minutes, PIB US (advance/prelim/final), ISM Manufacturier/Services, Jobless Claims hebdo, JOLTS, Ventes détail US, ADP Employment, Michigan Sentiment, Décision taux BCE, CPI Zone Euro, PIB Zone Euro, Discours Fed (Powell etc.), Discours BCE, EIA Stocks pétrole, Réunion OPEP.

ANNONCES EXCLUES : PMI Flash, données Canada/Australie, données UK sauf si impact EUR/USD significatif, indices régionaux Fed, commandes biens durables — impact insuffisant sur les actifs tradés."""


# ─────────────────────────────────────────
#  HELPERS DATE
# ─────────────────────────────────────────
def get_date():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz).strftime("%d %B %Y")

def get_month_year():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz).strftime("%B %Y")


# ─────────────────────────────────────────
#  PROMPTS MODULES
# ─────────────────────────────────────────
PROMPTS = {

"bilan": lambda: f"""Génère le module **BILAN N-1 + ARC DE TENDANCE** au {get_date()}.

Recherche en temps réel les performances des actifs et données macro de la semaine passée.

**BILAN SEMAINE N-1**
Pour chaque actif (XAU, DXY, EUR/USD, S&P, BTC, Pétrole) :
| Actif | Performance | Biais prévu | Biais réalisé | Écart |

Questions clés :
- Les biais identifiés la semaine précédente étaient-ils justes ?
- Les setups identifiés se sont-ils déclenchés ?
- Ce qui a divergé par rapport aux prévisions et pourquoi ?

**CONTINUITÉ DE TENDANCE**
- Surprises économiques sur les 4 dernières semaines (direction : hawkish ou dovish ?)
- Structures de prix en développement (plusieurs semaines)
- Évolution du discours Fed/BCE sur 2-3 mois (hawkish drift ou dovish pivot ?)
- Cinétique des événements géopolitiques en cours
- Ce qui a été pricé vs ce qui reste à pricer depuis le début du trimestre

**BIAIS HÉRITÉ POUR CETTE SEMAINE :**
Par actif — directionnel et justifié.""",

"calendrier": lambda: f"""Génère le **CALENDRIER ÉCONOMIQUE SEMAINE** du {get_date()}.

Recherche en temps réel le calendrier économique complet de la semaine.

FILTRE STRICT : uniquement les annonces impactant XAU/USD, DXY, EUR/USD, S&P 500, BTC/ETH, Pétrole.

Pour chaque annonce importante :
| Jour | Heure CET | Annonce | Impact | Précédent | Forecast | Réel | Delta |

**CALCUL DELTA pour les données déjà sorties :**
Delta = Réel - Forecast
- Delta positif sur inflation/emploi = surprise hawkish → USD ↑, Or ↓
- Delta négatif sur inflation/emploi = surprise dovish → USD ↓, Or ↑

**INTERPRÉTATION PAR ANNONCE :**
Pour chaque publication : comment le marché va-t-il interpréter cette donnée ?

**LES 3 JOURS LES PLUS VOLATILS :** identifiés et justifiés.

**LECTURE INSTITUTIONNELLE :**
Où est la liquidité cette semaine ? Où le retail va-t-il se faire piéger ?""",

"macro": lambda: f"""Génère l'analyse **MACRO & POLITIQUES MONÉTAIRES** au {get_date()}.

Recherche les dernières publications et discours des banques centrales en temps réel.

**FED (États-Unis)**
- Taux actuel · Dernier changement · Prochaine réunion FOMC
- Biais actuel : Hawkish / Dovish / Pause — justification précise
- Dernières données vs objectifs Fed (inflation cible 2%, emploi maximum)
- Ce que le marché a pricé en taux (futures Fed Funds) vs ce que Powell a dit réellement
- Dot plot actuel — combien de baisses pricées par les marchés vs ce que la Fed projette ?

**BCE (Zone Euro)**
- Taux actuel · Biais · Derniers discours
- Divergence Fed vs BCE → impact direct EUR/USD

**BoJ (Japon)**
- Politique en cours · Risque YCC/normalisation · Impact DXY/Yen

**PBoC (Chine)**
- Stimulus récents · Impact sur le risk-on global

**DÉCALAGE EXPLOITABLE :**
- Qu'est-ce que le marché a déjà pricé vs ce que les données montrent réellement ?
- Y a-t-il un écart exploitable entre les anticipations du marché et la réalité ?

**IMPACT DIRECTIONNEL PAR ACTIF :**
DXY · XAU/USD · S&P 500 · BTC · EUR/USD — biais pour la semaine.""",

"geopolitique": lambda: f"""Génère l'analyse **GÉOPOLITIQUE & FLUX MONDIAUX** au {get_date()}.

Recherche en temps réel les dernières actualités géopolitiques majeures.

**TENSIONS GÉOPOLITIQUES ACTIVES**
Pour chaque tension identifiée :
- Description · Durée · Niveau d'escalade actuel
- Impact direct sur les marchés (oil, or, dollar, indices)
- Trajectoire : aggravation ou détente ?

**LOGIQUE FLUX :**
Tensions → risk-off → Or ↑ / Dollar ↑ / Yen ↑ / Indices ↓ / Crypto ↓
Détente → risk-on → Indices ↑ / Cryptos ↑ / Or range / Dollar flat

**DIMENSION SMART MONEY :**
Les institutions utilisent-elles la peur pour accumuler discrètement ?
Ou la confiance pour distribuer dans l'euphorie ?

**BIAIS RISK-ON / RISK-OFF de la semaine :** Tranché, justifié, non ambigu.

**IMPACT PAR ACTIF :**
| Actif | Impact géopolitique actuel | Signal |
| XAU/USD | | |
| DXY | | |
| S&P 500 | | |
| BTC | | |
| Pétrole | | |""",

"xauusd": lambda: f"""Génère l'analyse complète **XAU/USD** au {get_date()}.

Recherche le prix live de l'or et toutes les données macro en temps réel.

**PRIX LIVE & CONTEXTE**
Prix actuel · ATH historique · Performance hebdo · Performance mensuelle · Performance YTD

**CONSENSUS BANQUES (si disponible)**
| Institution | Target 12 mois | Date publication |
(Si non disponible : "Consensus non disponible publiquement")

**BIAIS :** Haussier / Baissier / Neutre | **CONVICTION :** Forte / Moyenne / Faible

**JUSTIFICATION FONDAMENTALE (4 drivers) :**
1. Taux réels US = taux 10Y nominaux - inflation anticipée PCE → signal direct sur l'or
2. DXY direction → corrélation inverse or/dollar
3. Flux refuges géopolitiques → demande directionnelle
4. Positionnement Fed → baisses de taux = taux réels ↓ = or haussier

**NIVEAUX CLÉS :**
| Zone | Niveau | Type | Signification |
| Support 1 | | | |
| Support 2 | | | |
| Résistance 1 | | | |
| Résistance 2 | | | |
| ATH | | | |

**POSITIONNEMENT COT :**
Positions nets non-commerciaux · Extrême haussier/baissier/neutre ?
Signal contrarian si applicable.

**LECTURE INSTITUTIONNELLE :**
Où le retail vend-il à tort cette semaine ?
Où les institutions accumulent-elles réellement ?

**TIMING OPTIMAL :**
Jours les plus actifs · Fenêtres d'entrée · Pièges émotionnels à éviter""",

"eurusd": lambda: f"""Génère l'analyse complète **EUR/USD** au {get_date()}.

Recherche le prix live EUR/USD et les données Fed/BCE en temps réel.

**PRIX LIVE & CONTEXTE**
Prix actuel · Performance hebdo · Performance mensuelle · Niveaux clés récents

**CONSENSUS FX (si disponible)**
| Institution | Target EUR/USD | Horizon |

**BIAIS :** Haussier / Baissier / Neutre

**JUSTIFICATION FONDAMENTALE :**
- Différentiel de taux Fed vs BCE (qui est le plus hawkish ?)
- Impact DXY sur EUR/USD (corrélation inverse directe)
- Données Zone Euro récentes (croissance, inflation, emploi)
- Flux de capitaux : vers USD ou vers EUR ?

**NIVEAUX CLÉS :**
Supports · Résistances · Zones de liquidité H4 · Equal highs/lows

**COT EUR Futures :** Positionnement institutionnel net

**TIMING :** Jours les plus volatils · Fenêtres d'entrée · Annonces BCE à surveiller""",

"dxy": lambda: f"""Génère l'analyse complète **DXY (Dollar Index)** au {get_date()}.

Recherche le niveau live du DXY et toutes les données macro US en temps réel.

**PRIX LIVE & CONTEXTE**
DXY actuel · Performance hebdo · Performance mensuelle · Niveaux MA50/MA200

**CONSENSUS (si disponible)**
Projections taux Fed implicites (futures) · Targets FX grandes banques

**BIAIS :** Haussier / Baissier / Neutre

**MATRICE DE CORRÉLATIONS EN TEMPS RÉEL :**
| Actif | Si DXY ↑ | Si DXY ↓ | Niveau actuel |
| XAU/USD | ↓ | ↑ | |
| EUR/USD | ↓ | ↑ | |
| S&P 500 | Pression | Favorable | |
| BTC/USD | Tend ↓ | Tend ↑ | |
| Pétrole WTI | ↓ | ↑ | |

**IMPACT DES DONNÉES US CETTE SEMAINE :**
Calendrier filtré + impact attendu sur le DXY pour chaque publication.

**NIVEAUX CLÉS DXY :**
Supports · Résistances · Zones de liquidité institutionnelle

**ZONES DE PIÈGES :** Où les stops retail sont concentrés cette semaine

**PSYCHOLOGIE :** Le retail est-il en excès de confiance ou en peur sur le dollar ?""",

"btc": lambda: f"""Génère l'analyse complète **BTC/ETH** au {get_date()}.

Recherche les prix live BTC et ETH en temps réel.

**PRIX LIVE**
| Actif | Prix | Variation 24h | Variation hebdo |
| BTC/USD | | | |
| ETH/USD | | | |
| BTC Dominance | | | |
| Fear & Greed Index | | | |

**CONSENSUS INSTITUTIONNEL (si disponible)**
Targets institutions publiés (Bernstein, Standard Chartered, Galaxy Digital, Fidelity Digital Assets)
Si non disponible : "Consensus non disponible publiquement"

**BIAIS BTC :** Haussier / Baissier / Neutre
**BIAIS ETH :** Haussier / Baissier / Neutre

**CORRÉLATION MACRO DIRECTE :**
- DXY actuel → impact BTC (corrélation inverse)
- Risk-on/off de la semaine → biais crypto global
- Taux réels US → impact actifs spéculatifs
- S&P 500 → corrélation avec BTC en période de risk-off

**FLUX DE CAPITAUX :**
ETF Bitcoin BTC (BlackRock IBIT etc.) : flux entrants ou sortants cette semaine ?
Accumulation institutionnelle ou distribution dans les sommets ?

**NIVEAUX CLÉS BTC :**
Supports · Résistances · Zones de liquidité

**FOURCHETTE RÉALISTE DE LA SEMAINE :**
BTC : [X]$ - [Y]$
ETH : [X]$ - [Y]$

**PSYCHOLOGIE :** FOMO actif ou panique latente chez le retail ?""",

"sp500": lambda: f"""Génère l'analyse complète **S&P 500** au {get_date()}.

Recherche le niveau live du S&P 500, le VIX, le Fear & Greed en temps réel.

**PRIX LIVE & CONTEXTE**
S&P 500 actuel · VIX · Fear & Greed Index · Performance YTD · Écart depuis ATH

**CONSENSUS BANQUES (si disponible)**
| Banque | Target fin d'année | EPS 2026 consensus |
| Goldman Sachs | | |
| JPMorgan | | |
| Bank of America | | |
| Médiane FactSet | | |

**BIAIS :** Bullish / Bearish / Range | **CONVICTION :** Forte / Moyenne / Faible

**FACTEURS DÉTERMINANTS :**
1. Fed : taux et ton → impact valorisation P/E forward
2. Croissance US : PIB, emploi, consommation
3. Conditions de liquidité : taux réels, crédit
4. Géopolitique et risk premium

**NIVEAUX TECHNIQUES CLÉS :**
| Zone | Niveau | Signification |
| Support critique | | |
| 200 SMA | | |
| 50 SMA | | |
| Résistance 1 | | |
| ATH | | |

**PHASE DU MARCHÉ :** Accumulation / Distribution / Range
Justification basée sur volume + COT S&P futures.

**ROTATION SECTORIELLE :** Secteurs en force vs faiblesse — signal institutionnel

**PSYCHOLOGIE :** Retail euphorique, en panique, ou indécis ?""",

"petrole": lambda: f"""Génère l'analyse complète **Pétrole WTI/Brent** au {get_date()}.

Recherche les prix live WTI et Brent et les données OPEP/EIA en temps réel.

**PRIX LIVE**
WTI actuel · Brent actuel · Spread WTI/Brent · Performance mensuelle

**CONSENSUS (si disponible)**
| Institution | WTI Target | Brent Target | Horizon |
| Goldman Sachs | | | |
| JPMorgan | | | |
| EIA forecast | | | |

**BIAIS :** Haussier / Baissier / Neutre

**DRIVERS FONDAMENTAUX :**
1. OPEP+ : quotas actuels · Discipline · Prochaine réunion
2. EIA Stocks : dernière publication vs forecast (mercredi 16h30)
3. Géopolitique : tensions dans les pays producteurs actives
4. DXY direction → pétrole libellé en USD : corrélation inverse

**IMPACT MACRO CROISÉ :**
Pétrole > 90$/b → inflation ↑ → Fed hawkish → Or/S&P pression
Pétrole < 70$/b → désinflation → Fed peut couper → risk-on

**NIVEAUX CLÉS WTI :**
Supports · Résistances · Zone de défense OPEP · Zone stop production

**TRADE DE LA SEMAINE :** EIA Stocks mercredi 16h30 CET — setup à surveiller""",

"projections": lambda: f"""Génère les **PROJECTIONS BANCAIRES & INSTITUTIONNELS** au {get_date()}.

Recherche en temps réel UNIQUEMENT les projections publiquement disponibles.

**XAU/USD — Targets 12 mois**
| Institution | Target | Date publication |

**S&P 500 — Targets fin d'année**
| Institution | Target | EPS 2026 |

**DXY / EUR/USD — Projections FX**
| Institution | Target EUR/USD | Horizon |

**Pétrole — Projections prix**
| Institution | WTI | Brent | Horizon |

**TAUX & INFLATION**
Fed dot plot actuel : taux projeté fin 2026 · Nombre de baisses
BCE : projections taux
Inflation PCE pricée par le marché (breakevens)

**DÉCALAGE EXPLOITABLE :**
- Le marché est-il en ligne ou en décalage avec ces projections ?
- Les institutions sont-elles en avance ou en retard sur le pricing du marché ?
- Edge identifiable dans ce décalage ?

**RÈGLE ABSOLUE :** Si projection non trouvée dans une source publique vérifiable → "Information non disponible publiquement"
Jamais de chiffre inventé.""",

"cot": lambda: f"""Génère l'analyse **COT + SENTIMENT + FLUX** au {get_date()}.

Recherche en temps réel le dernier rapport COT CFTC et les données de sentiment.

**COT CFTC — DERNIER RAPPORT**
| Actif | Non-comm. nets | Signal | Évolution vs S-1 |
| XAU/USD | | | |
| EUR/USD | | | |
| S&P 500 futures | | | |
| WTI futures | | | |
| BTC futures CME | | | |

**LECTURE CONTRARIANTE :**
- > 75% longs non-commerciaux = danger retournement
- < 35% longs = accumulation institutionnelle probable
Extrêmes identifiés cette semaine ?

**SENTIMENT GLOBAL**
- Fear & Greed Index : [valeur] — [zone : Extreme Fear/Fear/Neutral/Greed/Extreme Greed]
- VIX actuel : [valeur] — lecture
- Retail : FOMO actif / panique latente / excès de confiance ?

**FLUX DE CAPITAUX**
Risk-on ou risk-off dominant ?
ETF Gold (GLD/IAU) : flux entrants ou sortants ?
ETF Bitcoin : flux entrants ou sortants ?
Treasuries : demande safe haven en hausse ou baisse ?

**ZONES DE PIÈGES**
Où sont concentrés les stops retail sur chaque actif ?
Comment les institutions vont-elles exploiter ces positions ?

**SIGNAL CONTRARIAN PRINCIPAL DE LA SEMAINE :**
L'opportunité la plus claire issue du positionnement extrême.""",

"timing": lambda: f"""Génère l'analyse **TIMING D'ENTRÉE** pour les publications majeures de la semaine du {get_date()}.

Recherche le calendrier éco en temps réel et identifie les 2-3 publications majeures.

**RÈGLE FONDAMENTALE :**
🔵 Avant news = Préparation (zones, niveaux, plan — pas d'exécution)
🟡 Pendant news = Manipulation (faux moves, spreads larges — observer uniquement)
🟢 Après news = Opportunité (vrai mouvement identifiable — exécution possible)

---

Pour CHAQUE publication majeure de la semaine :

**[ANNONCE] · [JOUR] · [HEURE CET]**
Précédent : [X] · Forecast : [Y]
Actifs : [liste]

🔵 PRÉ-POSITIONNEMENT (veille au soir / matin avant la publication)
- La news est-elle déjà pricée dans les prix actuels ?
- Biais retail majoritaire en ce moment (long ou short en excès ?)
- Zones de liquidité H4 : equal highs/lows, POI à identifier
- Action : cartographier, planifier, NE PAS exécuter

🟡 PENDANT LA NEWS (0-15 min post-release)
- Comportements institutionnels attendus : spike dans quel sens ?
- Les institutions vont déclencher les stops pour créer de la liquidité
- Action : OBSERVER SEULEMENT — ne jamais entrer sur la première bougie

🟢 APRÈS LA NEWS (15-60 min post-release)
- Signal d'entrée valide : cassure de structure + retour sur zone clé + alignement fonda
- Confirmation minimale : structure H1 cassée + retracement + volume
- Entrée optimale : premier retracement vers le POI après confirmation

**PIÈGES RETAIL CLASSIQUES :**
1. Entrer sur la première bougie post-news (80% des cas = faux move)
2. Confondre spike émotionnel et vraie direction
3. Suivre le retard du retail au lieu d'attendre la confirmation institutionnelle""",

"synthese": lambda: f"""Génère la **SYNTHÈSE & STRATÉGIE FINALE** pour la semaine du {get_date()}.

Recherche toutes les données macro et prix en temps réel.

**BIAIS GLOBAL DE LA SEMAINE :**
Risk-On / Risk-Off — justifié en 3 points maximum.

**LES 3 JOURS LES PLUS VOLATILS**
| Rang | Jour | Événement déclencheur | Actifs impactés |

**OPPORTUNITÉS MAJEURES IDENTIFIÉES**

| Actif | Biais | Setup | Condition d'entrée | Timing |
| XAU/USD | | | | |
| EUR/USD | | | | |
| S&P 500 | | | | |
| BTC/USD | | | | |

**LECTURE INSTITUTIONNELLE FINALE**
Où est la liquidité principale cette semaine ?
Où sont les pièges pour le retail ?
Ce que le smart money prépare vs ce que le retail anticipe.

**CONCLUSION :**
"Cette semaine, la clé sera [X]. La volatilité maximale est attendue autour de [jour]. Le marché est [biais global]. L'or est [tendance], le dollar est [tendance], les indices sont [tendance], les cryptos sont [tendance]." """,

"classement": lambda: f"""Génère le **CLASSEMENT DES ACTIFS À TRADER** pour la semaine du {get_date()}.

Recherche toutes les données en temps réel.

**TABLEAU DE CLASSEMENT FINAL :**
| Rang | Actif | Biais | Conviction | Catalyseur principal | Risque principal | Timing optimal |
| 🥇 1 | | | | | | |
| 🥈 2 | | | | | | |
| 🥉 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

**CRITÈRES DE PONDÉRATION APPLIQUÉS :**
- Clarté du biais fonda (30%) : direction macro claire et lisible ?
- Alignement SMC (25%) : structure de prix en accord avec le biais ?
- Catalyseur identifié (20%) : news ou événement précis déclenchant le move ?
- Rapport risque/opportunité (15%) : potentiel de gain vs risque de faux move ?
- Conviction institutionnelle COT (10%) : COT + flux dans le même sens ?

**JUSTIFICATION RANG PAR RANG :**
Pour chaque actif : pourquoi ce rang précis, en une phrase.

**ACTIFS À ÉVITER CETTE SEMAINE :**
[Actif] — raison précise (biais trop incertain / pas de setup propre)

**CONCLUSION :**
"Cette semaine, l'actif prioritaire est [X] car [justification en 1 phrase]. À éviter : [actif] en raison de [raison]." """,

"analyse_hebdo": lambda: f"""Génère l'**ANALYSE HEBDOMADAIRE COMPLÈTE** pour la semaine du {get_date()}.

Recherche TOUTES les données en temps réel : prix live, calendrier éco, COT, macro, géopolitique, consensus bancaires.

Produis tous les modules dans l'ordre suivant, chacun séparé par ━━━ :

━━━ 1. BILAN N-1 + ARC DE TENDANCE ━━━
(biais semaine passée justes ou non, continuité tendance 4 semaines, discours BC sur 2-3 mois)

━━━ 2. CALENDRIER ÉCONOMIQUE SEMAINE ━━━
(jour par jour, actifs filtrés uniquement, prev/forecast/réel/delta/impact)

━━━ 3. MACRO & POLITIQUES MONÉTAIRES ━━━
(Fed/BCE/BoJ/PBoC, biais, décalage marché vs réalité)

━━━ 4. GÉOPOLITIQUE & FLUX MONDIAUX ━━━
(tensions actives, risk-on/off, smart money)

━━━ 5. ANALYSE XAU/USD ━━━
(biais + niveaux + COT + consensus + timing)

━━━ 6. ANALYSE DXY ━━━
(biais + corrélations + zones liquidité)

━━━ 7. ANALYSE EUR/USD ━━━
(biais + niveaux + Fed vs BCE)

━━━ 8. ANALYSE BTC/ETH ━━━
(biais + fourchette semaine + flux ETF)

━━━ 9. ANALYSE S&P 500 ━━━
(biais + VIX + consensus banques + niveaux)

━━━ 10. ANALYSE PÉTROLE WTI/BRENT ━━━
(biais + OPEP + EIA + niveaux)

━━━ 11. PROJECTIONS BANCAIRES ━━━
(GS/JPM/BNP/ING — sources publiques uniquement)

━━━ 12. POSITIONING COT + SENTIMENT ━━━
(COT CFTC + Fear & Greed + flux ETF)

━━━ 13. TIMING D'ENTRÉE ━━━
(2-3 publications majeures : avant/pendant/après)

━━━ 14. SYNTHÈSE & STRATÉGIE FINALE ━━━
(biais global, 3 jours volatils, opportunités majeures)

━━━ 15. CLASSEMENT DES 5 ACTIFS ━━━
(tableau complet avec conviction/timing/risque)""",

"briefing_jour": lambda: f"""Génère le **BRIEFING MACRO DU JOUR** pour le {get_date()}.

Recherche en temps réel : prix live, calendrier du jour, headlines macro majeures.

**PRIX LIVE CE MATIN**
| Actif | Prix | Variation 24h | Signal |
| XAU/USD | | | |
| DXY | | | |
| EUR/USD | | | |
| S&P 500 futures | | | |
| BTC/USD | | | |
| WTI Pétrole | | | |

**BIAIS DU MATIN : Risk-On / Risk-Off**
Justification en 2-3 points concrets.

**ÉVÉNEMENTS DU JOUR**
(uniquement annonces impactant les actifs tradés)
| Heure CET | Annonce | Précédent | Forecast | Actifs | Impact attendu |

**TOP 3 HEADLINES MACRO**
News qui vont dominer la journée + impact direct sur chaque actif.

**POINTS DE VIGILANCE DU JOUR**
3 points maximum — concrets et actionnables.

**SETUP DU JOUR (si identifiable)**
Actif · Direction · Condition d'entrée · Timing · Invalidation""",

"bilan_jour": lambda: f"""Génère le **BILAN MACRO DE LA JOURNÉE** du {get_date()}.

Recherche en temps réel tous les chiffres publiés aujourd'hui.

**BILAN DES PUBLICATIONS DU JOUR**
| Annonce | Précédent | Forecast | Réel | Delta | Surprise | Réaction marché |

**CALCUL DELTAS :**
Delta = Réel - Forecast
Positif sur inflation = hawkish | Négatif sur inflation = dovish
Positif sur croissance = bullish | Négatif sur croissance = bearish

**PERFORMANCE ACTIFS DU JOUR**
| Actif | Variation journée | Plus haut/bas | Driver principal |
| XAU/USD | | | |
| DXY | | | |
| EUR/USD | | | |
| S&P 500 | | | |
| BTC/USD | | | |
| WTI | | | |

**NARRATIVE MACRO : AUJOURD'HUI → CE QUI VIENT**
Comment les données du jour s'enchaînent avec les événements à venir.
Liens de causalité entre ce qui s'est passé et ce qui va se passer.

**ÉVÉNEMENTS CLÉS À VENIR (prochains 3 jours)**
| Jour | Annonce | Forecast | Lien avec données du jour |

**BIAIS AJUSTÉ POUR DEMAIN**
Par actif — basé sur les données du jour.""",

"calendrier_mois": lambda: f"""Génère le **CALENDRIER ÉCONOMIQUE DU MOIS COMPLET** pour {get_month_year()}.

Recherche en temps réel le calendrier économique complet du mois.

FILTRE STRICT : inclure UNIQUEMENT les annonces impactant XAU/USD, DXY, EUR/USD, S&P 500, BTC/ETH, Pétrole avec volatilité forte ou modérée.

INCLUS : CPI/Core CPI US, NFP, PCE Core/Headline, FOMC, PIB US, ISM Manuf/Services, Jobless Claims, JOLTS, Ventes détail, ADP, Michigan Sentiment, BCE décision, CPI Zone Euro, PIB Zone Euro, Discours Fed/BCE, EIA Stocks pétrole, OPEP.
EXCLUS : PMI Flash, Canada/Australie, UK sauf impact EUR/USD majeur, indices régionaux Fed, commandes biens durables.

FORMAT PAR SEMAINE :
━━━━━━━━━━━━━━━━
📅 SEMAINE [N] · [dates]
━━━━━━━━━━━━━━━━

[Jour] [date] · [Heure CET]
🔴 [Annonce haute volatilité] / 🟠 [Modérée]
Précédent : [X] · Forecast : [Y] · Réel : [Z si disponible]
Actifs : [liste] · Volatilité : FORTE / MODÉRÉE

⚡ TRADE DE LA SEMAINE : [annonce la plus importante]

---

**RÉSUMÉ DU MOIS EN CLÔTURE :**
Top 5 publications les plus importantes avec date · actifs concernés · setup potentiel""",

"analyse_mensuelle": lambda: f"""Génère l'**ANALYSE MENSUELLE COMPLÈTE** pour {get_month_year()}.

Recherche en temps réel toutes les données du mois.

**1. BILAN DU MOIS ÉCOULÉ**

Performance mensuelle :
| Actif | Performance | Driver principal | Biais prévu | Biais réalisé |
| XAU/USD | | | | |
| DXY | | | | |
| EUR/USD | | | | |
| S&P 500 | | | | |
| BTC/USD | | | | |
| Pétrole WTI | | | | |

Surprises macro majeures du mois :
| Publication | Forecast | Réel | Delta | Impact marché |

**2. BANQUES CENTRALES DU MOIS**
Fed : évolution du discours · révisions SEP/dot plot vs mois précédent
BCE : changement de ton · prochaine décision
Ce qui a changé dans le discours des BC ce mois

**3. CONSENSUS BANQUES MIS À JOUR (si disponible)**
Nouvelles projections publiées ce mois :
| Institution | Actif | Ancien target | Nouveau target | Sens |

**4. GÉOPOLITIQUE DU MOIS**
Événements majeurs · Impact sur marchés · Ce qui reste à pricer

**5. ÉVOLUTION COT MENSUELLE**
| Actif | Position début de mois | Position fin de mois | Tendance |

**6. ARC DE TENDANCE TRIMESTRIEL**
Structures de prix en développement · Ce qui a été pricé · Ce qui reste à pricer au trimestre

**7. PROJECTION MOIS SUIVANT**
| Actif | Biais | Conviction | Catalyseur principal | Timing |

**8. CLASSEMENT MENSUEL**
| Rang | Actif | Biais | Conviction | Catalyseur | Timing optimal |
| 🥇 1 | | | | | |
| 🥈 2 | | | | | |
| 🥉 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

**CONCLUSION :**
"Ce mois, l'actif prioritaire est [X]. Le catalyseur principal sera [Y]. Le biais global reste [Z]." """,
}


def get_analyse_libre_prompt(actif: str) -> str:
    return f"""Génère une analyse institutionnelle complète sur **{actif.upper()}** au {get_date()}.

Recherche en temps réel : prix live, consensus analystes, données fondamentales récentes.

**PRIX & CONTEXTE LIVE**
Prix actuel · Performance 24h · Performance hebdo · Performance mensuelle

**CONSENSUS (si disponible)**
Targets banques / analystes sur {actif.upper()} — sources publiques uniquement.
Si non disponible : "Consensus non disponible publiquement"

**BIAIS :** Haussier / Baissier / Neutre | **CONVICTION :** Forte / Moyenne / Faible

**ANALYSE FONDAMENTALE**
Drivers macro actuels affectant {actif.upper()}
Catalyseurs à venir (news, publications, événements)
Ce que les institutions font vs ce que le retail anticipe

**CORRÉLATIONS MACRO (si applicable)**
DXY · Taux · Risk-on/off · Secteur · Actifs liés

**NIVEAUX CLÉS**
| Zone | Niveau | Signification |
| Support 1 | | |
| Support 2 | | |
| Résistance 1 | | |
| Résistance 2 | | |

**POSITIONNEMENT & SENTIMENT**
COT si disponible · Sentiment analystes · Flux institutionnels

**TIMING OPTIMAL**
Catalyseurs à surveiller · Fenêtre d'entrée · Condition de validation · Pièges à éviter

**CONCLUSION :**
Biais tranché · Setup si identifiable · Risque principal · Invalidation"""


def get_consensus_prompt(actif: str) -> str:
    return f"""Recherche et compile TOUS les consensus disponibles publiquement sur **{actif.upper()}** au {get_date()}.

Sources à consulter : Goldman Sachs Research, JPMorgan, BNP Paribas, Crédit Agricole, ING Think, Deutsche Bank, Citigroup, UBS, Morgan Stanley, Bank of America, FactSet, Reuters poll, Bloomberg consensus, FMI, Banque Mondiale.

**CONSENSUS PRIX / TARGETS**
| Institution | Target | Horizon | Date publication | Biais (haussier/baissier) |

**CONSENSUS DONNÉES MACRO (si {actif} = donnée macro)**
| Institution | Forecast | Précédent | Source |

**STATISTIQUES DU CONSENSUS**
Médiane : [valeur]
Bull case (cible haute) : [valeur]
Bear case (cible basse) : [valeur]
Dispersion (écart type) : large / normal / étroit

**ANALYSE DU DÉCALAGE MARCHÉ vs CONSENSUS**
Prix actuel live : [X]
Consensus médian : [Y]
Écart : [Z%]
Interprétation : le marché est en avance ou en retard sur le consensus ?

**RÉVISIONS RÉCENTES**
Le consensus a-t-il été révisé à la hausse ou à la baisse ce dernier mois ?
Quelle institution a révisé en dernier et dans quel sens ?

**RÈGLE ABSOLUE :** Pour toute institution sans target pubiquement disponible → "Information non disponible publiquement"
Jamais de chiffre inventé."""


# ─────────────────────────────────────────
#  UTILITAIRES
# ─────────────────────────────────────────
async def call_claude(prompt: str) -> str:
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Erreur Claude : {e}")
        return f"❌ *Erreur API Claude*\n\n{str(e)}\n\n_Réessaie dans quelques instants._"


async def send_long(bot_or_context, chat_id: int, text: str, is_bot=False):
    """Envoie un message, le découpe si > 4000 chars (limite Telegram)."""
    max_len = 4000
    bot = bot_or_context if is_bot else bot_or_context.bot

    if len(text) <= max_len:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception:
            await bot.send_message(chat_id=chat_id, text=text)
        return

    parts = []
    while len(text) > max_len:
        split = text.rfind("\n", 0, max_len)
        if split == -1:
            split = max_len
        parts.append(text[:split])
        text = text[split:].strip()
    if text:
        parts.append(text)

    for i, part in enumerate(parts):
        try:
            await bot.send_message(chat_id=chat_id, text=part, parse_mode="Markdown")
        except Exception:
            await bot.send_message(chat_id=chat_id, text=part)
        if i < len(parts) - 1:
            await asyncio.sleep(0.4)


async def run_module(update: Update, context: ContextTypes.DEFAULT_TYPE, module: str):
    """Handler générique — envoie le message d'attente, génère, répond."""
    titles = {
        "bilan": "Bilan N-1 + Arc de tendance",
        "calendrier": "Calendrier économique semaine",
        "macro": "Macro & Politiques monétaires",
        "geopolitique": "Géopolitique & Flux mondiaux",
        "xauusd": "Analyse XAU/USD",
        "eurusd": "Analyse EUR/USD",
        "dxy": "Analyse DXY",
        "btc": "Analyse BTC/ETH",
        "sp500": "Analyse S&P 500",
        "petrole": "Analyse Pétrole WTI/Brent",
        "projections": "Projections bancaires",
        "cot": "COT + Sentiment + Flux",
        "timing": "Timing d'entrée",
        "synthese": "Synthèse & Stratégie finale",
        "classement": "Classement des actifs",
        "analyse_hebdo": "Analyse hebdo complète",
        "briefing_jour": "Briefing du jour",
        "bilan_jour": "Bilan de la journée",
        "calendrier_mois": "Calendrier du mois",
        "analyse_mensuelle": "Analyse mensuelle complète",
    }
    chat_id = update.effective_chat.id
    title = titles.get(module, module)

    wait = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *{title}*\n_Recherche en temps réel et analyse en cours..._",
        parse_mode="Markdown"
    )
    result = await call_claude(PROMPTS[module]())
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=wait.message_id)
    except Exception:
        pass
    await send_long(context, chat_id, result)


# ─────────────────────────────────────────
#  COMMANDES HANDLERS
# ─────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏦 *Macro Trading Analyst — Terminal Institutionnel*\n\n"
        "Bienvenue. Ce bot analyse les marchés comme un hedge fund.\n\n"
        "*Commandes principales :*\n"
        "• `/menu` — Interface complète avec boutons\n"
        "• `/analyse [actif]` — Analyse libre sur tout actif\n"
        "• `/consensus [actif]` — Consensus banques\n"
        "• `/aide` — Toutes les commandes\n\n"
        "*Alertes automatiques :*\n"
        "☀️ 07h00 — Briefing du jour\n"
        "🌙 22h00 — Bilan du jour\n"
        "📅 1er du mois — Analyse mensuelle\n\n"
        "_Tape /menu pour commencer._",
        parse_mode="Markdown"
    )

async def cmd_aide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *TOUTES LES COMMANDES*\n\n"
        "*Modules terminal :*\n"
        "`/bilan` · `/calendrier` · `/macro` · `/geopolitique`\n"
        "`/xauusd` · `/eurusd` · `/dxy` · `/btc`\n"
        "`/sp500` · `/petrole` · `/projections` · `/cot`\n"
        "`/timing` · `/synthese` · `/classement` · `/analyse_hebdo`\n\n"
        "*Nouvelles fonctions :*\n"
        "`/analyse [actif]` — Tout actif (NVIDIA, argent, CAC40...)\n"
        "`/consensus [actif]` — Consensus banques\n"
        "`/briefing` — Briefing macro du jour\n"
        "`/bilan_jour` — Bilan chiffres de la journée\n"
        "`/calendrier_mois` — Calendrier mois filtré\n"
        "`/analyse_mensuelle` — Analyse mensuelle complète\n\n"
        "*Alertes auto :* 07h00 · 22h00 · 1er du mois",
        parse_mode="Markdown"
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔁 Bilan N-1", callback_data="bilan"),
         InlineKeyboardButton("📅 Calendrier semaine", callback_data="calendrier")],
        [InlineKeyboardButton("🌍 Macro & BC", callback_data="macro"),
         InlineKeyboardButton("⚔️ Géopolitique", callback_data="geopolitique")],
        [InlineKeyboardButton("💰 XAU/USD", callback_data="xauusd"),
         InlineKeyboardButton("💶 EUR/USD", callback_data="eurusd"),
         InlineKeyboardButton("💵 DXY", callback_data="dxy")],
        [InlineKeyboardButton("🪙 BTC/ETH", callback_data="btc"),
         InlineKeyboardButton("📈 S&P 500", callback_data="sp500"),
         InlineKeyboardButton("🛢️ Pétrole", callback_data="petrole")],
        [InlineKeyboardButton("🏦 Projections", callback_data="projections"),
         InlineKeyboardButton("📊 COT & Sentiment", callback_data="cot")],
        [InlineKeyboardButton("⏱️ Timing", callback_data="timing"),
         InlineKeyboardButton("⚙️ Synthèse", callback_data="synthese")],
        [InlineKeyboardButton("🏆 Classement actifs", callback_data="classement"),
         InlineKeyboardButton("📋 Briefing du jour", callback_data="briefing_jour")],
        [InlineKeyboardButton("🌙 Bilan du jour", callback_data="bilan_jour"),
         InlineKeyboardButton("📅 Calendrier mois", callback_data="calendrier_mois")],
        [InlineKeyboardButton("📆 Analyse mensuelle", callback_data="analyse_mensuelle")],
        [InlineKeyboardButton("🗓️ ── ANALYSE HEBDO COMPLÈTE ──", callback_data="analyse_hebdo")],
    ]
    await update.message.reply_text(
        "📊 *Macro Trading Terminal*\nChoisis ton module :",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Commandes directes (alias run_module)
async def cmd_bilan(u, c): await run_module(u, c, "bilan")
async def cmd_calendrier(u, c): await run_module(u, c, "calendrier")
async def cmd_macro(u, c): await run_module(u, c, "macro")
async def cmd_geopolitique(u, c): await run_module(u, c, "geopolitique")
async def cmd_xauusd(u, c): await run_module(u, c, "xauusd")
async def cmd_eurusd(u, c): await run_module(u, c, "eurusd")
async def cmd_dxy(u, c): await run_module(u, c, "dxy")
async def cmd_btc(u, c): await run_module(u, c, "btc")
async def cmd_sp500(u, c): await run_module(u, c, "sp500")
async def cmd_petrole(u, c): await run_module(u, c, "petrole")
async def cmd_projections(u, c): await run_module(u, c, "projections")
async def cmd_cot(u, c): await run_module(u, c, "cot")
async def cmd_timing(u, c): await run_module(u, c, "timing")
async def cmd_synthese(u, c): await run_module(u, c, "synthese")
async def cmd_classement(u, c): await run_module(u, c, "classement")
async def cmd_analyse_hebdo(u, c): await run_module(u, c, "analyse_hebdo")
async def cmd_briefing(u, c): await run_module(u, c, "briefing_jour")
async def cmd_bilan_jour(u, c): await run_module(u, c, "bilan_jour")
async def cmd_calendrier_mois(u, c): await run_module(u, c, "calendrier_mois")
async def cmd_analyse_mensuelle(u, c): await run_module(u, c, "analyse_mensuelle")

async def cmd_analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❓ *Précise l'actif à analyser*\n\n"
            "Exemples :\n`/analyse EURUSD`\n`/analyse NVIDIA`\n"
            "`/analyse argent`\n`/analyse CAC40`\n`/analyse Bitcoin`",
            parse_mode="Markdown"
        )
        return
    actif = " ".join(context.args)
    chat_id = update.effective_chat.id
    wait = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *Analyse {actif.upper()}*\n_Recherche en temps réel..._",
        parse_mode="Markdown"
    )
    result = await call_claude(get_analyse_libre_prompt(actif))
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=wait.message_id)
    except Exception:
        pass
    await send_long(context, chat_id, result)

async def cmd_consensus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❓ *Précise l'actif*\n\n"
            "Exemples :\n`/consensus XAU/USD`\n`/consensus S&P 500`\n"
            "`/consensus pétrole`\n`/consensus EUR/USD`",
            parse_mode="Markdown"
        )
        return
    actif = " ".join(context.args)
    chat_id = update.effective_chat.id
    wait = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *Consensus {actif.upper()}*\n_Recherche des projections bancaires..._",
        parse_mode="Markdown"
    )
    result = await call_claude(get_consensus_prompt(actif))
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=wait.message_id)
    except Exception:
        pass
    await send_long(context, chat_id, result)


# ─────────────────────────────────────────
#  CALLBACK BOUTONS INLINE
# ─────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    module = query.data
    if module not in PROMPTS:
        await query.message.reply_text("❌ Module inconnu.")
        return
    await run_module(query, context, module)


# ─────────────────────────────────────────
#  ALERTES AUTOMATIQUES
# ─────────────────────────────────────────
async def auto_briefing(app: Application):
    if not CHAT_ID:
        return
    logger.info("⏰ Alerte automatique : Briefing 07h00")
    result = await call_claude(PROMPTS["briefing_jour"]())
    await send_long(app.bot, int(CHAT_ID), result, is_bot=True)

async def auto_bilan(app: Application):
    if not CHAT_ID:
        return
    logger.info("⏰ Alerte automatique : Bilan 22h00")
    result = await call_claude(PROMPTS["bilan_jour"]())
    await send_long(app.bot, int(CHAT_ID), result, is_bot=True)

async def auto_mensuel(app: Application):
    if not CHAT_ID:
        return
    logger.info("⏰ Alerte automatique : Analyse mensuelle 1er du mois")
    result = await call_claude(PROMPTS["analyse_mensuelle"]())
    await send_long(app.bot, int(CHAT_ID), result, is_bot=True)


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commandes de base
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("aide", cmd_aide))
    app.add_handler(CommandHandler("menu", cmd_menu))

    # Modules terminal
    app.add_handler(CommandHandler("bilan", cmd_bilan))
    app.add_handler(CommandHandler("calendrier", cmd_calendrier))
    app.add_handler(CommandHandler("macro", cmd_macro))
    app.add_handler(CommandHandler("geopolitique", cmd_geopolitique))
    app.add_handler(CommandHandler("xauusd", cmd_xauusd))
    app.add_handler(CommandHandler("eurusd", cmd_eurusd))
    app.add_handler(CommandHandler("dxy", cmd_dxy))
    app.add_handler(CommandHandler("btc", cmd_btc))
    app.add_handler(CommandHandler("sp500", cmd_sp500))
    app.add_handler(CommandHandler("petrole", cmd_petrole))
    app.add_handler(CommandHandler("projections", cmd_projections))
    app.add_handler(CommandHandler("cot", cmd_cot))
    app.add_handler(CommandHandler("timing", cmd_timing))
    app.add_handler(CommandHandler("synthese", cmd_synthese))
    app.add_handler(CommandHandler("classement", cmd_classement))
    app.add_handler(CommandHandler("analyse_hebdo", cmd_analyse_hebdo))

    # Nouvelles fonctions
    app.add_handler(CommandHandler("analyse", cmd_analyse))
    app.add_handler(CommandHandler("consensus", cmd_consensus))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("bilan_jour", cmd_bilan_jour))
    app.add_handler(CommandHandler("calendrier_mois", cmd_calendrier_mois))
    app.add_handler(CommandHandler("analyse_mensuelle", cmd_analyse_mensuelle))

    # Boutons inline
    app.add_handler(CallbackQueryHandler(button_handler))

    # Planificateur alertes automatiques
    tz = pytz.timezone(TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(
        auto_briefing,
        CronTrigger(hour=7, minute=0, timezone=tz),
        args=[app], id="briefing_matin"
    )
    scheduler.add_job(
        auto_bilan,
        CronTrigger(hour=22, minute=0, timezone=tz),
        args=[app], id="bilan_soir"
    )
    scheduler.add_job(
        auto_mensuel,
        CronTrigger(day=1, hour=8, minute=0, timezone=tz),
        args=[app], id="analyse_mensuelle_auto"
    )

    scheduler.start()
    logger.info("✅ Bot démarré | Alertes : 07h00 · 22h00 · 1er du mois")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
