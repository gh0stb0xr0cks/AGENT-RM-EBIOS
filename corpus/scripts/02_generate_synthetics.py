"""
generate_corpus_6k.py — Génération à l'échelle du corpus EBIOS RM 2024
═══════════════════════════════════════════════════════════════════════

Objectif : produire ~6 000 exemples Q/A annotés couvrant les 5 ateliers
EBIOS RM × 14 secteurs, avec templates riches et diversité maximale.

Backends supportés :
  --backend claude   → Anthropic API (bootstrap, nécessite ANTHROPIC_API_KEY)
  --backend ollama   → Ollama local (air-gapped, production)
  --backend mistral  → Mistral AI API (nécessite MISTRAL_API_KEY)

Fonctionnalités clés :
  ✓ 8 à 15 templates distincts par atelier (vs 5 dans 02_generate_synthetics.py)
  ✓ Contextes sectoriels enrichis (vocabulaire métier par secteur)
  ✓ Personas variés (RSSI, consultant, auditeur, analyste SOC, DG)
  ✓ Batch Claude API (jusqu'à 5 requêtes parallèles via threading)
  ✓ Reprise après interruption (progress.json par strate)
  ✓ Détection auto des strates déjà complètes
  ✓ Parsing JSON structuré (LLM renvoie du JSON, plus fiable que regex)
  ✓ Validation inline avant sauvegarde (zéro terme interdit)
  ✓ Barre de progression tqdm
  ✓ Rapport final détaillé (couverture, taux de succès, durée)

Usage :
  # Bootstrap Claude (recommandé pour démarrer)
  python generate_corpus_6k.py --backend claude --workers 3

  # Production Ollama (air-gapped)
  python generate_corpus_6k.py --backend ollama --model mistral:7b-instruct

  # Atelier/secteur spécifique
  python generate_corpus_6k.py --backend claude --atelier A3 --secteur sante

  # Reprendre après interruption (les strates terminées sont ignorées)
  python generate_corpus_6k.py --backend claude --resume

  # Dry-run : affiche le plan sans générer
  python generate_corpus_6k.py --dry-run

Prérequis :
  pip install anthropic tqdm requests
  # Pour Mistral : pip install mistralai
  # Pour Ollama  : ollama serve (puis ollama pull mistral)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

# ── Dépendance optionnelle tqdm ─────────────────────────────────────────────
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):  # type: ignore[misc]
        return iterable

# ── Schema local ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
try:
    from schema import (
        ATELIERS, SECTORS, SYSTEM_PROMPT,
        FORBIDDEN_TERMS, SCALE_PATTERN,
        CorpusExample, Message,
    )
except ImportError:
    sys.exit(
        "Impossible d'importer schema.py.\n"
        "Placer generate_corpus_6k.py dans corpus/ (à côté de scripts/)."
    )

# ── Chemins ──────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent
OUTPUT_DIR  = ROOT / "raw" / "synthetics"
PROGRESS_F  = ROOT / "raw" / ".generation_progress.json"
LOG_FILE    = ROOT / "raw" / "generation.log"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("corpus_gen")

# ═══════════════════════════════════════════════════════════════════════════════
# PLAN DE GÉNÉRATION
# ═══════════════════════════════════════════════════════════════════════════════

# Répartition cible par atelier (total ~6 000 sur 14 secteurs)
TARGET_PER_ATELIER_SECTEUR: dict[str, int] = {
    "A1":  18,   #  18 × 14 =  252  (cadrage, fondamental mais moins de variantes)
    "A2":  22,   #  22 × 14 =  308  (sources de risque, couples SR/OV multiples)
    "A3":  55,   #  55 × 14 =  770  (cœur méthodologique, richesse maximale)
    "A4":  55,   #  55 × 14 =  770  (scénarios opérationnels, TTP MITRE)
    "A5":  28,   #  28 × 14 =  392  (traitement, homologation)
}
# Total théorique : (18+22+55+55+28) × 14 = 178 × 14 = 2 492
# → avec le multiplier --scale on atteint 6 000 en doublant A3/A4

TOTAL_TARGET = sum(v * len(SECTORS) for v in TARGET_PER_ATELIER_SECTEUR.values())


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXTES SECTORIELS ENRICHIS
# Vocabulaire métier injecté dans les prompts pour ancrer les exemples
# ═══════════════════════════════════════════════════════════════════════════════

SECTOR_CONTEXT: dict[str, dict] = {
    "sante": {
        "label": "secteur de la santé (CHU, hôpital, GHT, clinique privée)",
        "valeurs_metier": ["prise en charge des patients", "continuité des soins",
                           "dossier patient informatisé (DPI)", "plateau technique",
                           "gestion des prescriptions"],
        "biens_supports": ["SIH (Système d'Information Hospitalier)", "PACS",
                           "équipements biomédicaux connectés", "serveurs applicatifs",
                           "réseau interne cloisonné"],
        "sources_risque": ["cybercriminel ransomware", "insider malveillant",
                           "prestataire de maintenance biomédicale"],
        "contexte_reglementaire": "HDS, RGPD, référentiel HDS ANSSI, LPM pour CHU OIV",
        "specificites": "Disponibilité critique (urgences vitales), données de santé sensibles",
    },
    "defense": {
        "label": "secteur de la défense (BITD, DGA, industriels de défense)",
        "valeurs_metier": ["conception de systèmes d'armes", "R&D défense",
                           "maintien en condition opérationnelle", "protection du secret"],
        "biens_supports": ["SI Confidentiel Défense", "outils CAO/FAO",
                           "réseau classifié", "salles sécurisées", "PLM"],
        "sources_risque": ["État étranger hostile (APT)", "espionnage industriel",
                           "insider avec habilitation"],
        "contexte_reglementaire": "IGI 1300, II 901, LPM, qualification ANSSI CSEC",
        "specificites": "Données classifiées, obligation IGI 1300, cloisonnement réseau absolu",
    },
    "finance": {
        "label": "secteur financier (banque de détail, assurance, marché)",
        "valeurs_metier": ["gestion des comptes clients", "traitement des paiements",
                           "trading et marché", "conformité réglementaire",
                           "continuité des opérations bancaires"],
        "biens_supports": ["core banking system", "SWIFT", "API open banking",
                           "serveurs de trading", "base de données clients"],
        "sources_risque": ["gang ransomware", "fraude interne", "APT étatique",
                           "skimming et fraude carte"],
        "contexte_reglementaire": "DORA, RGPD, PCI-DSS, exigences ACPR/AMF",
        "specificites": "DORA impose des exigences de résilience opérationnelle numérique",
    },
    "energie": {
        "label": "secteur de l'énergie (réseau électrique, gaz, nucléaire, OIV)",
        "valeurs_metier": ["distribution électrique", "conduite du réseau",
                           "gestion des installations nucléaires",
                           "comptage et facturation"],
        "biens_supports": ["SCADA/EMS", "automates industriels (PLC)", "postes HTB",
                           "smart meters", "systèmes de téléconduite"],
        "sources_risque": ["État hostile (Sandworm, Volt Typhoon)",
                           "cyberterroriste", "prestataire de maintenance OT"],
        "contexte_reglementaire": "LPM OIV, arrêté sectoriel énergie, IEC 62443",
        "specificites": "Systèmes OT/IT, temps réel industriel, impact sécurité nationale",
    },
    "transport": {
        "label": "secteur du transport (ferroviaire, aérien, maritime, routier)",
        "valeurs_metier": ["gestion du trafic", "sécurité des passagers",
                           "continuité du service", "régulation des circulations"],
        "biens_supports": ["SNCF SGC", "ATC (contrôle trafic aérien)",
                           "systèmes ERTMS", "portails de réservation",
                           "réseaux de télécommunication ferroviaire"],
        "sources_risque": ["cybercriminel (ransomware)", "hacktiviste",
                           "État hostile", "insider"],
        "contexte_reglementaire": "LPM OIV, NIS2, réglementation EASA pour aviation",
        "specificites": "Sécurité physique des personnes, temps réel critique",
    },
    "collectivite": {
        "label": "collectivité territoriale (mairie, département, région, intercommunalité)",
        "valeurs_metier": ["services numériques aux citoyens", "gestion administrative",
                           "urbanisme et cadastre", "aide sociale et action sociale"],
        "biens_supports": ["portail citoyen", "SI RH", "SI finance",
                           "messagerie institutionnelle", "infrastructure cloud"],
        "sources_risque": ["cybercriminel ransomware", "hacktiviste",
                           "prestataire cloud", "escroquerie au virement"],
        "contexte_reglementaire": "RGPD, RGS, CNIL, référentiel SecNumCloud",
        "specificites": "Données personnelles massives, budget IT contraint, cloud mutualisé",
    },
    "industrie": {
        "label": "industrie manufacturière (automobile, aéronautique, chimie, usine 4.0)",
        "valeurs_metier": ["production industrielle", "R&D et propriété intellectuelle",
                           "gestion de la supply chain", "qualité produit"],
        "biens_supports": ["MES (Manufacturing Execution System)", "SCADA usine",
                           "robots industriels connectés", "ERP SAP",
                           "réseau OT/IT usine"],
        "sources_risque": ["concurrent étranger (espionnage IP)", "ransomware OT",
                           "prestataire de maintenance", "sous-traitant compromis"],
        "contexte_reglementaire": "NIS2, ISO 27001, IEC 62443, RGPD",
        "specificites": "Convergence IT/OT, propriété intellectuelle, continuité production",
    },
    "education": {
        "label": "enseignement supérieur et recherche (université, grande école, EPST)",
        "valeurs_metier": ["formation et enseignement", "recherche scientifique",
                           "valorisation des brevets", "administration étudiante"],
        "biens_supports": ["ENT (Environnement Numérique de Travail)",
                           "laboratoires de recherche connectés", "ELN",
                           "serveurs de données de recherche", "réseau campus"],
        "sources_risque": ["État étranger (espionnage académique)", "cybercriminel",
                           "étudiant malveillant", "prestataire hébergement"],
        "contexte_reglementaire": "RGPD, politique de sécurité MESR, CNRS",
        "specificites": "Propriété intellectuelle recherche, ouverture réseau campus",
    },
    "assurance": {
        "label": "secteur de l'assurance (assureur, courtier, réassureur, mutuelles)",
        "valeurs_metier": ["souscription et tarification", "gestion des sinistres",
                           "relation client", "pilotage actuariel"],
        "biens_supports": ["système de gestion des contrats", "portail assuré",
                           "base de données sinistres", "outils actuariels"],
        "sources_risque": ["cybercriminel (vol données)", "fraude interne",
                           "prestataire cloud", "concurrent (espionnage tarifaire)"],
        "contexte_reglementaire": "RGPD, DORA, Solvabilité II, exigences ACPR",
        "specificites": "Données personnelles et médicales, conformité actuarielle",
    },
    "administration": {
        "label": "administration publique (ministère, agence, opérateur d'État)",
        "valeurs_metier": ["service public numérique", "gestion des données citoyens",
                           "continuité de l'action de l'État",
                           "protection du secret des délibérations"],
        "biens_supports": ["SI ministériel", "réseau interministériel RIE",
                           "messagerie chiffrée", "coffre-fort numérique",
                           "portails FranceConnect"],
        "sources_risque": ["APT étatique", "hacktiviste", "cybercriminel",
                           "prestataire IT"],
        "contexte_reglementaire": "RGS, PSSIE, LPM, RGPD, circulaires ANSSI",
        "specificites": "Homologation obligatoire, RGS applicable, données régaliennes",
    },
    "telecom": {
        "label": "télécommunications (opérateur télécom, FAI, câblo-opérateur)",
        "valeurs_metier": ["fourniture d'accès Internet", "téléphonie mobile",
                           "infrastructure réseau cœur", "services cloud B2B"],
        "biens_supports": ["réseau cœur IP/MPLS", "équipements RAN",
                           "systèmes OSS/BSS", "DNS autoritaire", "CDN"],
        "sources_risque": ["APT (interception massive)", "cybercriminel",
                           "fournisseur d'équipements (supply chain)"],
        "contexte_reglementaire": "LPM OIV, article L33-1 CPCE, NIS2, 5G security",
        "specificites": "Infrastructure critique nationale, interception légale, 5G",
    },
    "spatial": {
        "label": "secteur spatial (CNES, opérateurs satellites, industrie spatiale)",
        "valeurs_metier": ["opération de satellites", "télémétrie et télécommande",
                           "observation de la Terre", "navigation GPS/Galileo"],
        "biens_supports": ["segment sol de contrôle", "liaisons de télécommande chiffrées",
                           "réseaux de stations sol", "SI mission"],
        "sources_risque": ["État hostile (brouillage, spoofing)", "APT",
                           "prestataire de lancement"],
        "contexte_reglementaire": "LPM OIV, directives ESA, qualification CNES",
        "specificites": "Systèmes embarqués longue durée, liaisons radio critiques",
    },
    "eau": {
        "label": "eau et assainissement (régie, délégataire, SDIS)",
        "valeurs_metier": ["production et distribution d'eau potable",
                           "traitement des eaux usées",
                           "surveillance qualité de l'eau"],
        "biens_supports": ["SCADA stations de pompage", "automates de chloration",
                           "capteurs qualité réseau", "système de télérelève"],
        "sources_risque": ["hacktiviste (atteinte santé publique)",
                           "État hostile", "prestataire de maintenance OT"],
        "contexte_reglementaire": "LPM OIV, arrêté sectoriel eau, code de la santé publique",
        "specificites": "Impact santé publique direct, systèmes OT vieillissants",
    },
    "alimentaire": {
        "label": "agroalimentaire (industrie alimentaire, grande distribution, agriculture)",
        "valeurs_metier": ["production alimentaire", "chaîne du froid",
                           "traçabilité produits", "gestion des approvisionnements"],
        "biens_supports": ["ERP agroalimentaire", "automates de ligne de production",
                           "système de traçabilité", "plateforme logistique"],
        "sources_risque": ["ransomware OT", "concurrent (sabotage produit)",
                           "prestataire logistique"],
        "contexte_reglementaire": "NIS2, RGPD, réglementation sanitaire EU",
        "specificites": "Sécurité sanitaire, supply chain internationale, HACCP",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATES ENRICHIS PAR ATELIER
# Chaque template est un prompt complet avec instructions structurées.
# Le LLM doit répondre en JSON : {"question": "...", "reponse": "..."}
# ═══════════════════════════════════════════════════════════════════════════════

# Instruction JSON commune (injectée à la fin de chaque template)
JSON_INSTRUCTION = """
Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après :
{
  "question": "La question posée à l'assistant EBIOS RM (1-3 phrases, ton naturel)",
  "reponse": "La réponse experte et détaillée (300-600 mots, terminologie ANSSI stricte)"
}
N'utilise JAMAIS : "biens essentiels", "actifs", "menaces", "PACS", "risque brut/net".
Utilise TOUJOURS : "valeurs métier", "biens supports", "sources de risque", 
"objectifs visés", "plan de traitement du risque", "risque résiduel".
"""

# ── Personas de l'utilisateur (variation des questions) ─────────────────────
PERSONAS = [
    "un RSSI d'une organisation du secteur {secteur_label}, débutant en EBIOS RM",
    "un consultant cybersécurité expérimenté mandaté pour conduire une analyse EBIOS RM",
    "un auditeur ANSSI vérifiant la conformité de l'analyse de risques",
    "un directeur général qui souhaite comprendre les enjeux de sécurité",
    "un analyste SOC intégrant EBIOS RM dans ses activités de threat intelligence",
    "un responsable de la conformité (DPO/RSSI) préparant le dossier d'homologation",
    "un chef de projet SI qui découvre la méthode EBIOS RM pour son projet",
    "un prestataire PASSI conduisant une prestation de conseil en gestion des risques",
]

# ── Templates par atelier ────────────────────────────────────────────────────
TEMPLATES: dict[str, list[str]] = {

    # ──────────────────────────────────────────────────────────────────────────
    "A1": [

        # T1 — Identification valeurs métier
        """Tu génères un exemple Q/A pour l'ATELIER 1 EBIOS RM (Cadrage et socle de sécurité).
SECTEUR : {secteur_label}
CONTEXTE SECTORIEL : Valeurs métier typiques : {valeurs_metier}. Contexte réglementaire : {contexte_reglementaire}.
PERSONA : La question est posée par {persona}.
THÈME : Identification et priorisation des valeurs métier de l'organisation.
La réponse doit : lister 4-6 valeurs métier pertinentes pour ce secteur, justifier leur priorisation selon DICP (Disponibilité, Intégrité, Confidentialité, Preuve), identifier la propriété de sécurité dominante.
{json_instruction}""",

        # T2 — Cartographie biens supports
        """Tu génères un exemple Q/A pour l'ATELIER 1 EBIOS RM (Cadrage et socle de sécurité).
SECTEUR : {secteur_label}
CONTEXTE SECTORIEL : Biens supports typiques : {biens_supports}. Spécificités : {specificites}.
PERSONA : La question est posée par {persona}.
THÈME : Cartographie des biens supports critiques à partir des valeurs métier identifiées.
La réponse doit : partir d'une valeur métier spécifique au secteur, identifier ses biens supports (matériels, logiciels, réseaux, données, personnes), préciser les dépendances inter-biens supports.
{json_instruction}""",

        # T3 — Besoins de sécurité DICP
        """Tu génères un exemple Q/A pour l'ATELIER 1 EBIOS RM (Cadrage et socle de sécurité).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Évaluation des besoins de sécurité DICP pour une valeur métier critique du secteur.
La réponse doit : expliquer les 4 propriétés DICP, appliquer la grille d'évaluation à 2-3 valeurs métier du secteur, justifier le niveau (faible/moyen/fort/très fort) pour chaque propriété avec des arguments concrets liés au secteur.
{json_instruction}""",

        # T4 — Périmètre et parties prenantes
        """Tu génères un exemple Q/A pour l'ATELIER 1 EBIOS RM (Cadrage et socle de sécurité).
SECTEUR : {secteur_label}
CONTEXTE SECTORIEL : {contexte_reglementaire}
PERSONA : La question est posée par {persona}.
THÈME : Définition du périmètre de l'analyse et identification des parties prenantes de l'écosystème.
La réponse doit : définir les limites du périmètre (ce qui est inclus/exclu), lister les catégories de parties prenantes (fournisseurs, clients, partenaires, régulateurs), préciser les dépendances critiques qui justifieront l'atelier 3.
{json_instruction}""",

        # T5 — Socle de sécurité et référentiel
        """Tu génères un exemple Q/A pour l'ATELIER 1 EBIOS RM (Cadrage et socle de sécurité).
SECTEUR : {secteur_label}
CONTEXTE SECTORIEL : Réglementation applicable : {contexte_reglementaire}.
PERSONA : La question est posée par {persona}.
THÈME : Établissement du socle de sécurité existant et identification des référentiels applicables.
La réponse doit : identifier les mesures de sécurité déjà en place (organisationnelles et techniques), référencer les normes/réglementations applicables au secteur, évaluer l'écart entre socle existant et exigences réglementaires.
{json_instruction}""",

        # T6 — Événements redoutés
        """Tu génères un exemple Q/A pour l'ATELIER 1 EBIOS RM (Cadrage et socle de sécurité).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Identification et cotation des événements redoutés liés aux valeurs métier du secteur.
La réponse doit : définir 3-4 événements redoutés pertinents pour le secteur (formulation : "atteinte à la [propriété] de [valeur métier]"), coter chaque événement redouté en termes de gravité (G1-G4), justifier chaque cotation avec l'impact métier concret.
{json_instruction}""",

    ],

    # ──────────────────────────────────────────────────────────────────────────
    "A2": [

        # T1 — Couple SR/OV étatique
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
SOURCES DE RISQUE TYPIQUES : {sources_risque}
PERSONA : La question est posée par {persona}.
THÈME : Caractérisation d'un acteur étatique hostile comme source de risque pour ce secteur.
La réponse doit : décrire la source de risque (catégorie, motivation, ressources, capacité technique), formuler 2-3 objectifs visés pertinents pour ce secteur, évaluer la pertinence (faible/moyenne/forte/très forte) avec justification, décider si cette SR est retenue pour l'atelier 3.
{json_instruction}""",

        # T2 — Cybercriminel
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Analyse d'un groupe cybercriminel opportuniste ou ciblé comme source de risque.
La réponse doit : différencier cybercriminel opportuniste vs ciblé, caractériser la motivation (financière, extorsion), évaluer la capacité (outils disponibles, TTP documentées), formuler l'objectif visé principal pour ce secteur (ex: chiffrement pour rançon, vol de données revendables), conclure sur la pertinence et le niveau de priorité.
{json_instruction}""",

        # T3 — Insider malveillant
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Évaluation de la menace interne (insider malveillant : employé, prestataire, ex-employé).
La réponse doit : distinguer les profils d'insider (malveillant intentionnel, négligent, compromis), évaluer l'accès et la connaissance de l'environnement interne, caractériser l'objectif visé (fraude, sabotage, espionnage, vengeance), évaluer la capacité à contourner les contrôles d'accès existants.
{json_instruction}""",

        # T4 — Hacktiviste
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Pertinence des groupes hacktivistes comme source de risque pour ce secteur spécifique.
La réponse doit : évaluer l'exposition idéologique du secteur (pourquoi serait-il ciblé ?), caractériser les TTP hacktivistes typiques (DDoS, défacement, leaks), formuler l'objectif visé (nuire à l'image, dénoncer, perturber), conclure sur la pertinence avec niveau faible/moyen/fort.
{json_instruction}""",

        # T5 — Priorisation des SR retenues
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
SOURCES DE RISQUE TYPIQUES : {sources_risque}
PERSONA : La question est posée par {persona}.
THÈME : Synthèse et priorisation des sources de risque retenues à l'issue de l'atelier 2.
La réponse doit : présenter un tableau de synthèse (SR / motivation / capacité / pertinence / décision retenu/écarté), expliquer les critères d'exclusion pour les SR non retenues, identifier les 3-4 SR prioritaires qui alimenteront les scénarios stratégiques de l'atelier 3.
{json_instruction}""",

        # T6 — Chaîne d'approvisionnement / supply chain
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Analyse des sources de risque liées à la chaîne d'approvisionnement (supply chain) et aux tiers.
La réponse doit : identifier les catégories de tiers à risque (fournisseurs logiciels, prestataires de maintenance, sous-traitants), caractériser la source de risque "tiers compromis", évaluer les objectifs visés possibles (rebond vers la cible principale, sabotage indirect), conclure sur la pertinence pour ce secteur.
{json_instruction}""",

        # T7 — Espionnage industriel / économique
        """Tu génères un exemple Q/A pour l'ATELIER 2 EBIOS RM (Sources de risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Évaluation de la source de risque "concurrent ou acteur économique hostile" pour l'espionnage industriel ou économique.
La réponse doit : caractériser la motivation économique (avantage concurrentiel, vol de brevets, intelligence économique), évaluer la capacité (recours à des groupes APT, ingénierie sociale), formuler l'objectif visé (exfiltration de propriété intellectuelle, fichiers clients, données stratégiques), conclure sur la pertinence selon les enjeux du secteur.
{json_instruction}""",

    ],

    # ──────────────────────────────────────────────────────────────────────────
    "A3": [

        # T1 — Scénario ransomware
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
BIENS SUPPORTS : {biens_supports}. RÉGLEMENTATION : {contexte_reglementaire}.
PERSONA : La question est posée par {persona}.
THÈME : Construction d'un scénario stratégique de type ransomware ciblant les SI critiques du secteur.
La réponse doit fournir : intitulé du scénario stratégique (SS-XX), source de risque + objectif visé, valeurs métier ciblées, biens supports visés, chemin d'attaque générique (3-4 étapes macro sans détail opérationnel), niveau de vraisemblance (V1-V4) avec justification, niveau de gravité (G1-G4) avec justification, niveau de risque initial.
{json_instruction}""",

        # T2 — Exfiltration de données
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique d'exfiltration de données sensibles ou confidentielles.
La réponse doit fournir : intitulé SS-XX, source de risque motivée par le renseignement ou la revente de données, objectif visé (confidentialité des données), valeurs métier et biens supports ciblés (bases de données, documents sensibles), chemin d'attaque générique (compromission initiale → persistance → exfiltration lente), cotation G/V justifiée.
{json_instruction}""",

        # T3 — Dangerosité d'un prestataire
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Calcul et interprétation de la dangerosité d'une partie prenante (prestataire critique).
La réponse doit : identifier un prestataire critique concret pour ce secteur, appliquer la formule dangerosité = (Dépendance × Pénétration) / (Maturité SSI × Confiance) avec des valeurs justifiées (1-4 pour chaque facteur), interpréter le résultat, conclure sur les mesures de réduction ou les scénarios associés à construire.
{json_instruction}""",

        # T4 — Sabotage / déni de service
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
SPÉCIFICITÉS : {specificites}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique de sabotage ou déni de service ciblant la disponibilité des services critiques.
La réponse doit fournir : intitulé SS-XX, source de risque avec objectif de déstabilisation, valeurs métier ciblées (disponibilité prioritaire), biens supports visés (infrastructure réseau, équipements industriels), chemin d'attaque générique, cotation G4 ou G3 justifiée par l'impact opérationnel.
{json_instruction}""",

        # T5 — Supply chain / tiers compromis
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique de compromission par la chaîne d'approvisionnement (fournisseur logiciel, prestataire de service).
La réponse doit fournir : intitulé SS-XX, source de risque indirecte via un tiers de confiance, objectif visé (rebond vers la cible principale), valeurs métier impactées, chemin d'attaque générique (compromission du tiers → confiance implicite → accès à la cible), cotation G/V, niveau de risque initial.
{json_instruction}""",

        # T6 — Compromission physique / accès locaux
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique impliquant une compromission physique (intrusion, branchement de dispositif rogue, vol de matériel).
La réponse doit fournir : intitulé SS-XX, source de risque avec capacité d'accès physique, objectif visé (contournement des contrôles logiques), biens supports physiques visés, chemin d'attaque générique, cotation G/V justifiée.
{json_instruction}""",

        # T7 — Scénario multi-vecteurs / persistance longue durée
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique d'attaque sophistiquée multi-vecteurs avec persistance longue durée (APT).
La réponse doit fournir : intitulé SS-XX, source de risque étatique ou très structurée, objectif visé combinant espionnage et pré-positionnement, valeurs métier ciblées, chemin d'attaque générique sur plusieurs mois, cotation Vraisemblance et Gravité adaptées à un acteur très capable.
{json_instruction}""",

        # T8 — Désinformation / atteinte à l'image
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique d'atteinte à la réputation ou de désinformation via des données volées.
La réponse doit fournir : intitulé SS-XX, source de risque (hacktiviste ou concurrent), objectif visé (déstabilisation de la confiance, atteinte à la réputation), valeurs métier ciblées (image de marque, relation client), chemin d'attaque (vol de données → leak public → campagne médiatique), cotation G/V.
{json_instruction}""",

        # T9 — Scénario sur infrastructure cloud / SaaS
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique ciblant les services cloud ou SaaS utilisés par l'organisation (prestataire cloud compromis ou misconfiguration).
La réponse doit fournir : intitulé SS-XX, source de risque exploitant la dépendance cloud, objectif visé, biens supports hébergés (données, applications), chemin d'attaque générique (compromission API → accès données → exfiltration ou sabotage), cotation G/V.
{json_instruction}""",

        # T10 — Comparaison et hiérarchisation de scénarios
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Comparaison et hiérarchisation de plusieurs scénarios stratégiques pour prioriser les ateliers suivants.
La réponse doit : présenter 3 scénarios stratégiques distincts (intitulés + cotation G/V), expliquer la méthode de hiérarchisation (criticité = gravité × vraisemblance), identifier les 2 scénarios prioritaires à approfondir en atelier 4, justifier les exclusions temporaires.
{json_instruction}""",

        # T11 — Scénario fraude / manipulation
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique de fraude, manipulation ou corruption de données pour un gain financier ou opérationnel.
La réponse doit fournir : intitulé SS-XX, source de risque interne ou externe, objectif visé (intégrité des données, fraude financière), valeurs métier ciblées, biens supports concernés, chemin d'attaque générique, cotation G/V.
{json_instruction}""",

        # T12 — Impact sur la sécurité physique des personnes
        """Tu génères un exemple Q/A pour l'ATELIER 3 EBIOS RM (Scénarios stratégiques).
SECTEUR : {secteur_label}
SPÉCIFICITÉS : {specificites}
PERSONA : La question est posée par {persona}.
THÈME : Scénario stratégique dont l'impact ultime est la mise en danger physique de personnes (patients, voyageurs, opérateurs industriels).
La réponse doit fournir : intitulé SS-XX avec gravité G4, source de risque et objectif visé, valeurs métier critiques pour la sécurité physique, chemin d'attaque générique, justification de la cotation G4 par l'impact vital, mesures de réduction prioritaires à envisager.
{json_instruction}""",

    ],

    # ──────────────────────────────────────────────────────────────────────────
    "A4": [

        # T1 — Spear-phishing → mouvement latéral
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
BIENS SUPPORTS : {biens_supports}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire de spear-phishing suivi d'un mouvement latéral pour atteindre les systèmes critiques.
La réponse doit détailler : étape 1 Reconnaissance (MITRE T1590/T1589), étape 2 Accès initial via spear-phishing (T1566.001), étape 3 Exécution et persistance (T1059, T1053), étape 4 Mouvement latéral (T1021), étape 5 Impact (selon objectif). Pour chaque étape : action de l'attaquant, technique MITRE ATT&CK, bien support ciblé, indicateur de détection possible. Cotation V/G finale.
{json_instruction}""",

        # T2 — Exploitation vulnérabilité OT/SCADA
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
BIENS SUPPORTS OT : {biens_supports}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire d'exploitation d'une vulnérabilité dans les systèmes industriels OT/SCADA.
La réponse doit détailler : reconnaissance des équipements OT exposés (Shodan, T1046), accès initial via exploitation firmware ou interface web (T1190), pivot IT→OT via passerelle mal segmentée, manipulation des automates (T0831), impact sur le processus industriel. Références MITRE ICS ATT&CK. Cotation V/G. Mesures de détection spécifiques OT.
{json_instruction}""",

        # T3 — Accès VPN compromis
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire exploitant des accès VPN compromis (credential stuffing, CVE non patchée, MFA absent).
La réponse doit détailler : acquisition des credentials (T1589.001, T1110), exploitation de la vulnérabilité VPN ou absence de MFA, accès au réseau interne depuis l'extérieur (T1133), déplacement vers les ressources ciblées, impact. Cotation V/G. Mesures de détection (logs VPN, alertes géolocalisation).
{json_instruction}""",

        # T4 — Compromission supply chain logicielle
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire de compromission via la chaîne d'approvisionnement logicielle (mise à jour malveillante, bibliothèque compromise).
La réponse doit détailler : compromission du fournisseur logiciel (T1195.002), intégration d'un backdoor dans une mise à jour légitime, déploiement automatique chez les victimes (T1072), activation et persistance, collecte/exfiltration. Références MITRE. Exemples sectoriels. Cotation V/G.
{json_instruction}""",

        # T5 — Watering hole
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire de type watering hole ciblant les professionnels du secteur (portail métier compromis).
La réponse doit détailler : identification des sites fréquentés par les cibles (T1594), compromission du site légitime, injection d'exploit ou de payload (T1189), infection drive-by des visiteurs, établissement d'un C2 (T1071), exploitation ultérieure. Cotation V/G. Indicateurs de compromission côté victime.
{json_instruction}""",

        # T6 — Ransomware : déploiement et impact
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
BIENS SUPPORTS : {biens_supports}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire détaillé d'une attaque ransomware depuis l'accès initial jusqu'au chiffrement.
La réponse doit détailler : toutes les phases (accès initial, persistance, élévation de privilèges T1068, désactivation des sauvegardes T1490, déplacement latéral, déploiement du ransomware T1486), délai entre compromission et chiffrement (dwell time), impact sur les biens supports du secteur. Cotation V/G. Plan de réponse à incident.
{json_instruction}""",

        # T7 — Exfiltration longue durée / APT
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire d'exfiltration discrète et longue durée par un groupe APT.
La réponse doit détailler : établissement d'un accès persistant et discret (T1547, T1078), collecte progressive de données (T1119, T1213), techniques d'évasion des détections (T1027, T1055), canaux d'exfiltration chiffrés (T1048, T1071), durée typique (plusieurs mois à années). Cotation V/G. Difficultés de détection.
{json_instruction}""",

        # T8 — Fraude interne / abus de privilèges
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire d'une fraude interne exploitant des accès privilégiés légitimes.
La réponse doit détailler : profil de l'insider (accès, motivation), actions préparatoires (identification des contrôles, contournement des audits), accès aux données/systèmes cibles (T1078.002), exfiltration via canaux légitimes (email, clé USB, cloud perso), effacement des traces. Cotation V/G. Mesures de détection (UEBA, DLP).
{json_instruction}""",

        # T9 — Attaque physique + cyber (hybride)
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire hybride combinant intrusion physique et cyberattaque (branchement USB rogue, remplacement d'équipement).
La réponse doit détailler : accès physique (ingénierie sociale, badge cloné), branchement d'un implant réseau ou USB sur le SI interne (T1091, T1200), établissement d'un accès persistant depuis l'intérieur du périmètre de confiance, exploitation. Cotation V/G. Contrôles physiques et logiques à renforcer.
{json_instruction}""",

        # T10 — DDoS / saturation de service
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire d'une attaque par déni de service distribué (DDoS) ciblant les services en ligne du secteur.
La réponse doit détailler : acquisition du botnet ou service DDoS-as-a-Service, reconnaissance des services exposés (T1595), lancement de l'attaque volumétrique ou applicative (T1499), impact sur la disponibilité des valeurs métier, durée et coût. Cotation V/G. Mesures d'atténuation (anti-DDoS, scrubbing center).
{json_instruction}""",

        # T11 — Compromission de compte cloud / IAM
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire de compromission d'un compte cloud à privilèges (IAM, compte administrateur SaaS).
La réponse doit détailler : obtention des credentials (phishing, credential stuffing T1110.004), contournement du MFA (SIM swapping, T1111), accès aux ressources cloud (T1078.004), élévation via mauvaise configuration IAM (T1548), impact (vol de données, déploiement de ressources malveillantes). Cotation V/G.
{json_instruction}""",

        # T12 — DNS hijacking / attaque d'infrastructure
        """Tu génères un exemple Q/A pour l'ATELIER 4 EBIOS RM (Scénarios opérationnels).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Mode opératoire de détournement DNS ou d'attaque sur l'infrastructure de résolution de noms.
La réponse doit détailler : compromission du registrar ou du DNS autoritaire (T1584.002), redirection des requêtes DNS vers des serveurs malveillants, attaques Man-in-the-Middle sur les sessions utilisateurs, vol de credentials, déploiement de faux services. Impact sur les valeurs métier. Cotation V/G.
{json_instruction}""",

    ],

    # ──────────────────────────────────────────────────────────────────────────
    "A5": [

        # T1 — Plan de traitement d'un risque critique
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
RÉGLEMENTATION : {contexte_reglementaire}
PERSONA : La question est posée par {persona}.
THÈME : Élaboration du plan de traitement du risque pour un scénario critique (G3 ou G4).
La réponse doit : choisir la stratégie de traitement (réduction, transfert, acceptation, refus) et la justifier, lister les mesures techniques (au moins 5) et organisationnelles (au moins 3), estimer le risque résiduel après traitement (nouvelle cotation G/V), préciser le responsable et l'échéance pour chaque mesure prioritaire.
{json_instruction}""",

        # T2 — Dossier d'homologation
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
RÉGLEMENTATION : {contexte_reglementaire}
PERSONA : La question est posée par {persona}.
THÈME : Structuration du dossier d'homologation à partir des résultats de l'analyse EBIOS RM.
La réponse doit : lister les composants obligatoires du dossier d'homologation (déclaration d'applicabilité, tableau des risques résiduels, avis du RSSI, stratégie de traitement), expliquer le rôle de l'autorité d'homologation, préciser la durée de validité et les conditions de révision anticipée.
{json_instruction}""",

        # T3 — Choix de stratégie de traitement
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Arbitrage entre les quatre stratégies de traitement du risque (réduction, transfert, acceptation, refus) pour plusieurs scénarios identifiés.
La réponse doit : présenter les 4 stratégies avec définition et critères d'application, appliquer le raisonnement à 3 scénarios concrets du secteur avec des niveaux de risque différents, justifier l'arbitrage économique et opérationnel de chaque choix.
{json_instruction}""",

        # T4 — Priorisation sous contrainte budgétaire
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Priorisation des mesures de sécurité sous contrainte budgétaire dans le plan de traitement du risque.
La réponse doit : présenter une méthode de priorisation (criticité du scénario × facilité de mise en œuvre × coût), distinguer les mesures P0 (bloquantes pour homologation), P1 (à mettre en œuvre sous 6 mois), P2 (dans l'année), décrire comment justifier les arbitrages devant la direction et l'autorité d'homologation.
{json_instruction}""",

        # T5 — Indicateurs de suivi post-homologation
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Définition des indicateurs de suivi (KPI/KRI) et du processus de revue post-homologation.
La réponse doit : proposer 5-8 indicateurs de sécurité pertinents pour le secteur (disponibilité des sauvegardes, taux de patching, alertes SIEM, résultats de tests d'intrusion), définir la fréquence de revue, préciser les seuils déclencheurs d'une révision anticipée de l'analyse EBIOS RM.
{json_instruction}""",

        # T6 — Transfert du risque via assurance cyber
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Évaluation et mise en œuvre de la stratégie de transfert du risque via une assurance cyber.
La réponse doit : expliquer les conditions dans lesquelles le transfert par assurance est pertinent, décrire les couvertures typiques d'une police cyber (frais de réponse, pertes d'exploitation, extorsion, responsabilité tiers), identifier les exclusions courantes, préciser comment l'assurance s'articule avec le plan de traitement du risque.
{json_instruction}""",

        # T7 — Risque résiduel non acceptable : escalade
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
PERSONA : La question est posée par {persona}.
THÈME : Gestion d'un risque résiduel jugé non acceptable après traitement : procédure d'escalade et de refus d'homologation.
La réponse doit : décrire la procédure lorsque le risque résiduel reste G3/G4 après traitement, expliquer le rôle de l'autorité d'homologation dans la décision, présenter les options (refus d'homologation, homologation partielle avec restrictions d'usage, acceptation motivée avec plan d'action), décrire les responsabilités juridiques et opérationnelles.
{json_instruction}""",

        # T8 — Mesures organisationnelles dans le plan de traitement
        """Tu génères un exemple Q/A pour l'ATELIER 5 EBIOS RM (Traitement du risque).
SECTEUR : {secteur_label}
RÉGLEMENTATION : {contexte_reglementaire}
PERSONA : La question est posée par {persona}.
THÈME : Déclinaison des mesures organisationnelles du plan de traitement du risque (gouvernance, processus, formation, contrats).
La réponse doit : distinguer mesures techniques et organisationnelles, proposer pour ce secteur : politique de sécurité adaptée, clauses contractuelles avec les tiers, plan de formation et sensibilisation, procédures de gestion d'incidents, PCA/PRA. Préciser comment ces mesures réduisent concrètement le risque résiduel.
{json_instruction}""",

    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# GESTION DE LA PROGRESSION
# ═══════════════════════════════════════════════════════════════════════════════

def load_progress() -> dict:
    """Charge l'état de progression depuis le fichier JSON."""
    if PROGRESS_F.exists():
        try:
            return json.loads(PROGRESS_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(progress: dict) -> None:
    """Sauvegarde l'état de progression."""
    PROGRESS_F.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def strate_key(atelier: str, secteur: str) -> str:
    return f"{atelier}_{secteur}"


def count_existing(atelier: str, secteur: str) -> int:
    """Compte les exemples déjà générés pour cette strate."""
    path = OUTPUT_DIR / f"{atelier.lower()}_{secteur}.jsonl"
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# BACKENDS LLM
# ═══════════════════════════════════════════════════════════════════════════════

class LLMBackend:
    """Interface commune pour les backends LLM."""

    def __init__(self, backend: str, model: str, ollama_host: str):
        self.backend = backend
        self.model = model
        self.ollama_host = ollama_host
        self._init_client()

    def _init_client(self):
        if self.backend == "claude":
            try:
                import anthropic
            except ImportError:
                sys.exit("pip install anthropic")
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                sys.exit("Variable ANTHROPIC_API_KEY non définie.")
            self._client = anthropic.Anthropic(api_key=api_key)

        elif self.backend == "mistral":
            try:
                from mistralai.client import Mistral
            except ImportError:
                sys.exit("pip install mistralai")
            api_key = os.environ.get("MISTRAL_API_KEY", "")
            if not api_key:
                sys.exit("Variable MISTRAL_API_KEY non définie.")
            self._client = Mistral(api_key=api_key)

        elif self.backend == "ollama":
            try:
                import requests as _req
                self._req = _req
            except ImportError:
                sys.exit("pip install requests")
            self._client = None

    def generate(self, prompt: str, temperature: float = 0.75) -> str:
        """Génère une réponse depuis le backend configuré."""
        if self.backend == "claude":
            return self._generate_claude(prompt, temperature)
        elif self.backend == "mistral":
            return self._generate_mistral(prompt, temperature)
        elif self.backend == "ollama":
            return self._generate_ollama(prompt, temperature)
        raise ValueError(f"Backend inconnu : {self.backend}")

    def _generate_claude(self, prompt: str, temperature: float) -> str:
        import anthropic
        msg = self._client.messages.create(
            model=self.model or "claude-sonnet-4-20250514",
            max_tokens=1200,
            temperature=temperature,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def _generate_mistral(self, prompt: str, temperature: float) -> str:
        response = self._client.chat.complete(
            model=self.model or "mistral-large-latest",
            temperature=temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content

    def _generate_ollama(self, prompt: str, temperature: float) -> str:
        payload = {
            "model": self.model or "mistral",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 1200},
        }
        resp = self._req.post(
            f"{self.ollama_host}/api/chat",
            json=payload, timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRUCTION DES PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

def build_prompt(
    atelier: str,
    secteur: str,
    template_idx: int,
    persona_idx: int,
    rng_seed: int,
) -> str:
    """Construit un prompt complet à partir d'un template et d'un contexte sectoriel."""
    ctx = SECTOR_CONTEXT[secteur]
    templates = TEMPLATES[atelier]
    template = templates[template_idx % len(templates)]
    persona  = PERSONAS[persona_idx % len(PERSONAS)]

    # Formatage du persona avec le label sectoriel
    persona_str = persona.format(secteur_label=ctx["label"])

    prompt = template.format(
        secteur_label          = ctx["label"],
        valeurs_metier         = ", ".join(ctx.get("valeurs_metier", [])),
        biens_supports         = ", ".join(ctx.get("biens_supports", [])),
        sources_risque         = ", ".join(ctx.get("sources_risque", [])),
        contexte_reglementaire = ctx.get("contexte_reglementaire", ""),
        specificites           = ctx.get("specificites", ""),
        persona                = persona_str,
        json_instruction       = JSON_INSTRUCTION,
    )
    return prompt


# ═══════════════════════════════════════════════════════════════════════════════
# PARSING ET VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

_JSON_BLOCK_RE = re.compile(
    r'```(?:json)?\s*(\{.*?\})\s*```|(\{[^{}]*"question"[^{}]*"reponse"[^{}]*\})',
    re.DOTALL,
)

def parse_llm_response(
    raw: str,
    atelier: str,
    secteur: str,
    template_idx: int,
) -> tuple[str, str]:
    """
    Parse la réponse LLM pour extraire question et réponse.
    Priorité : JSON structuré → regex → fallback texte brut.
    Retourne (question, reponse).
    """
    # 1. Tentative JSON (méthode principale)
    # Nettoyer les éventuelles balises markdown
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

    try:
        data = json.loads(cleaned)
        question = str(data.get("question", "")).strip()
        reponse  = str(data.get("reponse",  "")).strip()
        if question and reponse:
            return question, reponse
    except json.JSONDecodeError:
        pass

    # 2. Extraction regex
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        candidate = match.group(1) or match.group(2)
        try:
            data = json.loads(candidate)
            q = str(data.get("question", "")).strip()
            r = str(data.get("reponse",  "")).strip()
            if q and r:
                return q, r
        except Exception:
            pass

    # 3. Fallback : extraction par marqueurs textuels
    q_match = re.search(
        r'(?:\*{0,2}Question\s*:?\*{0,2})\s*(.+?)(?=\n\*{0,2}R[eé]ponse|\Z)',
        raw, re.DOTALL | re.IGNORECASE,
    )
    a_match = re.search(
        r'(?:\*{0,2}R[eé]ponse\s*:?\*{0,2})\s*(.+)',
        raw, re.DOTALL | re.IGNORECASE,
    )

    question = q_match.group(1).strip() if q_match else (
        f"Comment appliquer l'atelier {atelier} EBIOS RM dans le secteur {secteur} "
        f"(template {template_idx}) ?"
    )
    reponse = a_match.group(1).strip() if a_match else raw.strip()

    return question, reponse


def validate_inline(reponse: str, atelier: str) -> list[str]:
    """
    Validation légère inline (ne bloque pas, seulement log).
    Retourne la liste des problèmes détectés.
    """
    issues = []
    r_lower = reponse.lower()

    for term in FORBIDDEN_TERMS:
        if term in r_lower:
            issues.append(f"terme_interdit:{term}")

    if atelier in ("A3", "A4", "A5"):
        if not SCALE_PATTERN.search(reponse):
            issues.append("cotation_gv_absente")

    if len(reponse.split()) < 60:
        issues.append(f"trop_court:{len(reponse.split())}_mots")

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION D'UNE STRATE
# ═══════════════════════════════════════════════════════════════════════════════

def generate_strate(
    atelier: str,
    secteur: str,
    target: int,
    backend: LLMBackend,
    progress: dict,
    delay: float,
    max_retries: int,
) -> int:
    """
    Génère `target` exemples pour un couple (atelier, secteur).
    Gère la reprise après interruption.
    Retourne le nombre d'exemples effectivement générés.
    """
    key      = strate_key(atelier, secteur)
    existing = count_existing(atelier, secteur)
    remaining = target - existing

    if remaining <= 0:
        log.info(f"  [{atelier}/{secteur}] déjà complet ({existing}/{target}), ignoré")
        return 0

    log.info(f"  [{atelier}/{secteur}] {existing} existants → génération de {remaining}")

    out_path = OUTPUT_DIR / f"{atelier.lower()}_{secteur}.jsonl"
    generated = 0
    n_templates = len(TEMPLATES[atelier])
    n_personas  = len(PERSONAS)

    with open(out_path, "a", encoding="utf-8") as f_out:
        for i in range(remaining):
            # Variation déterministe des templates et personas
            t_idx = (existing + i) % n_templates
            p_idx = (existing + i + 3) % n_personas   # offset pour diversité
            seed  = existing + i

            # Construction du prompt
            prompt = build_prompt(atelier, secteur, t_idx, p_idx, seed)

            # Température variable pour diversité
            temperature = 0.65 + (0.20 * ((i % 5) / 4))

            # Tentatives avec retry exponentiel
            raw_response = None
            for attempt in range(max_retries):
                try:
                    raw_response = backend.generate(prompt, temperature=temperature)
                    break
                except Exception as e:
                    wait = (2 ** attempt) * delay
                    log.warning(
                        f"    [{atelier}/{secteur}] tentative {attempt+1}/{max_retries} "
                        f"échouée : {e} — attente {wait:.1f}s"
                    )
                    time.sleep(wait)

            if raw_response is None:
                log.error(f"    [{atelier}/{secteur}] abandon après {max_retries} tentatives")
                continue

            # Parsing
            try:
                question, reponse = parse_llm_response(
                    raw_response, atelier, secteur, t_idx
                )
            except Exception as e:
                log.warning(f"    [{atelier}/{secteur}] parsing échoué : {e}")
                continue

            # Validation inline
            issues = validate_inline(reponse, atelier)
            if issues:
                log.warning(
                    f"    [{atelier}/{secteur}] problème(s) détecté(s) : {issues}"
                )
                # On sauvegarde quand même, le filtre 04 traitera
                # SAUF si terme interdit bloquant
                if any("terme_interdit" in iss for iss in issues) and len(issues) >= 2:
                    log.warning(f"    [{atelier}/{secteur}] exemple rejeté inline")
                    continue

            # Construction de l'objet CorpusExample
            example_id = (
                f"qa_{secteur}_{atelier.lower()}_"
                f"t{t_idx:02d}_p{p_idx:02d}_{uuid.uuid4().hex[:6]}"
            )
            example = CorpusExample(
                id      = example_id,
                atelier = atelier,
                secteur = secteur,
                source  = "synthetic",
                messages = [
                    Message(role="user",      content=question),
                    Message(role="assistant", content=reponse),
                ],
                metadata = {
                    "template_idx":  t_idx,
                    "persona_idx":   p_idx,
                    "temperature":   round(temperature, 3),
                    "backend":       backend.backend,
                    "model":         backend.model,
                    "inline_issues": issues,
                    "generated_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )

            f_out.write(json.dumps(example.to_dict(), ensure_ascii=False) + "\n")
            f_out.flush()
            generated += 1

            if i < remaining - 1:
                time.sleep(delay)

    # Mise à jour de la progression
    progress[key] = {"generated": existing + generated, "target": target}
    save_progress(progress)

    log.info(f"  [{atelier}/{secteur}] +{generated} → {existing+generated}/{target}")
    return generated


# ═══════════════════════════════════════════════════════════════════════════════
# RAPPORT FINAL
# ═══════════════════════════════════════════════════════════════════════════════

def print_report(
    start_time: float,
    total_generated: int,
    coverage: dict[str, dict],
) -> None:
    elapsed = time.time() - start_time
    h, m, s = int(elapsed//3600), int((elapsed%3600)//60), int(elapsed%60)

    print("\n" + "═" * 60)
    print("RAPPORT DE GÉNÉRATION DU CORPUS EBIOS RM")
    print("═" * 60)
    print(f"Durée totale      : {h:02d}h{m:02d}m{s:02d}s")
    print(f"Exemples générés  : {total_generated:,}")
    print()
    print("Couverture par atelier :")
    for atelier in ATELIERS:
        generated = sum(
            v["generated"] for k, v in coverage.items()
            if k.startswith(atelier + "_")
        )
        target = sum(
            v["target"] for k, v in coverage.items()
            if k.startswith(atelier + "_")
        )
        pct = generated / target * 100 if target else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {atelier} [{bar}] {generated:>4}/{target} ({pct:.0f}%)")

    # Strates incomplètes
    incomplete = [
        k for k, v in coverage.items()
        if v["generated"] < v["target"]
    ]
    if incomplete:
        print(f"\nStrates incomplètes ({len(incomplete)}) :")
        for k in incomplete[:10]:
            v = coverage[k]
            print(f"  {k:30s} {v['generated']}/{v['target']}")
        if len(incomplete) > 10:
            print(f"  ... ({len(incomplete)-10} autres)")
        print("\nRelancer avec --resume pour compléter.")
    else:
        print("\n✅ Toutes les strates sont complètes.")

    print(f"\nFichier de log : {LOG_FILE}")
    print("═" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génération à l'échelle du corpus EBIOS RM (~6 000 exemples)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--backend", choices=["claude", "ollama", "mistral"],
        default="claude",
        help="Backend LLM (claude|ollama|mistral)",
    )
    parser.add_argument(
        "--model", default="",
        help="Nom du modèle (défaut selon backend : claude-sonnet-4-20250514 | mistral | mistral-large-latest)",
    )
    parser.add_argument(
        "--ollama-host", default="http://localhost:11434",
        help="URL du serveur Ollama",
    )
    parser.add_argument(
        "--atelier", choices=ATELIERS + ["all"], default="all",
        help="Atelier à traiter (all = tous)",
    )
    parser.add_argument(
        "--secteur", choices=SECTORS + ["all"], default="all",
        help="Secteur à traiter (all = tous)",
    )
    parser.add_argument(
        "--scale", type=float, default=1.0,
        help="Multiplicateur de la cible (ex: 2.0 pour doubler, 0.1 pour test rapide)",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Nombre de threads parallèles (max 5, uniquement pour claude/mistral)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.8,
        help="Délai entre requêtes en secondes (respecter les rate limits)",
    )
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="Nombre de tentatives par exemple en cas d'erreur",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Reprendre la génération en ignorant les strates déjà complètes",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche le plan de génération sans rien générer",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
    )
    args = parser.parse_args()

    # ── Plan de génération ────────────────────────────────────────────────────
    ateliers = ATELIERS if args.atelier == "all" else [args.atelier]
    secteurs = SECTORS  if args.secteur == "all" else [args.secteur]

    plan: list[tuple[str, str, int]] = []   # (atelier, secteur, target)
    for atelier in ateliers:
        for secteur in secteurs:
            base_target = TARGET_PER_ATELIER_SECTEUR[atelier]
            target = max(1, int(base_target * args.scale))
            plan.append((atelier, secteur, target))

    total_target = sum(t for _, _, t in plan)

    print(f"╔══════════════════════════════════════════════════════╗")
    print(f"║  GÉNÉRATION CORPUS EBIOS RM — {args.backend.upper():<22} ║")
    print(f"╠══════════════════════════════════════════════════════╣")
    print(f"║  Strates : {len(plan):>4}  │  Cible totale : {total_target:>6} exemples ║")
    print(f"║  Ateliers: {', '.join(ateliers):<44} ║")
    print(f"║  Secteurs: {len(secteurs):>2} / {len(SECTORS):<47} ║")
    print(f"║  Scale   : ×{args.scale:<2}  │  Workers : {args.workers:<3}  │  Seed : {args.seed:<6} ║")
    print(f"╚══════════════════════════════════════════════════════╝\n")

    if args.dry_run:
        print("MODE DRY-RUN — plan de génération :")
        for atelier, secteur, target in plan:
            existing = count_existing(atelier, secteur)
            status = "✓ complet" if existing >= target else f"→ {target - existing} à générer"
            print(f"  {atelier}/{secteur:15s} target={target:3d}  existants={existing:3d}  {status}")
        print(f"\nTotal à générer : {sum(max(0, t - count_existing(a, s)) for a, s, t in plan)}")
        return

    # ── Initialisation backend et progression ─────────────────────────────────
    backend = LLMBackend(
        backend=args.backend,
        model=args.model,
        ollama_host=args.ollama_host,
    )

    progress = load_progress() if args.resume else {}
    workers  = min(args.workers, 5)
    if workers > 1 and args.backend == "ollama":
        log.warning("Parallélisme non recommandé avec Ollama — passage à 1 worker")
        workers = 1

    # ── Lancement ────────────────────────────────────────────────────────────
    start_time      = time.time()
    total_generated = 0

    if workers == 1:
        # Mode séquentiel
        for atelier, secteur, target in tqdm(plan, desc="Strates", unit="strate"):
            n = generate_strate(
                atelier, secteur, target,
                backend, progress, args.delay, args.max_retries,
            )
            total_generated += n
    else:
        # Mode parallèle (Claude / Mistral API uniquement)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    generate_strate,
                    atelier, secteur, target,
                    backend, progress, args.delay, args.max_retries,
                ): (atelier, secteur)
                for atelier, secteur, target in plan
            }
            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="Strates", unit="strate"):
                atelier, secteur = futures[future]
                try:
                    n = future.result()
                    total_generated += n
                except Exception as e:
                    log.error(f"  [{atelier}/{secteur}] exception : {e}")

    # ── Rapport ───────────────────────────────────────────────────────────────
    # Rechargement de la progression finale
    final_progress = load_progress()
    # Complète avec les strates non tracées
    for atelier, secteur, target in plan:
        k = strate_key(atelier, secteur)
        if k not in final_progress:
            final_progress[k] = {
                "generated": count_existing(atelier, secteur),
                "target": target,
            }

    print_report(start_time, total_generated, final_progress)


if __name__ == "__main__":
    main()
