"""
schema.py — Source de vérité unique du corpus EBIOS RM 2024.
Tous les scripts du pipeline importent exclusivement depuis ce module.

Contrat d'interface par script consommateur :
  02_generate_synthetics.py      -> SECTORS, GENERATION_TEMPLATES, GENERATION_THEMES,
                                    SYSTEM_PROMPT, CorpusExample, Message
  03_generate_counterexamples.py -> FORBIDDEN_TERMS, SECTORS, ATELIERS,
                                    CorpusExample, Message
  04_quality_filter.py           -> FORBIDDEN_TERMS, REQUIRED_TERMS_BY_ATELIER,
                                    SCALE_PATTERN, CorpusExample
  05_format_chatml.py            -> SYSTEM_PROMPT, CorpusExample
  07_validate_corpus.py          -> FORBIDDEN_TERMS, REQUIRED_TERMS_BY_ATELIER,
                                    SCALE_PATTERN, SECTORS, SYSTEM_PROMPT
  generate_corpus_6k.py          -> ATELIERS, SECTORS, SYSTEM_PROMPT, FORBIDDEN_TERMS,
                                    SCALE_PATTERN, CorpusExample, Message
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


# ============================================================================
# PERIMETRE DU CORPUS
# ============================================================================

ATELIERS: list[str] = ["A1", "A2", "A3", "A4", "A5"]

SECTORS: list[str] = [
    "sante", "defense", "finance", "energie", "transport",
    "collectivite", "industrie", "education", "assurance",
    "administration", "telecom", "spatial", "eau", "alimentaire",
]

# Labels lisibles — injectés dans les prompts de generate_corpus_6k.py
SECTOR_LABELS: dict[str, str] = {
    "sante":          "secteur de la santé (CHU, hôpital, GHT, clinique)",
    "defense":        "secteur de la défense (BITD, DGA, industriels de défense)",
    "finance":        "secteur financier (banque de détail, marché, paiement)",
    "energie":        "secteur de l'énergie (réseau électrique, gaz, nucléaire, OIV)",
    "transport":      "secteur du transport (ferroviaire, aérien, maritime, routier)",
    "collectivite":   "collectivité territoriale (mairie, département, région)",
    "industrie":      "industrie manufacturière (automobile, aéronautique, chimie, usine 4.0)",
    "education":      "enseignement supérieur et recherche (université, grande école, EPST)",
    "assurance":      "secteur de l'assurance (assureur, courtier, mutuelle, réassureur)",
    "administration": "administration publique (ministère, agence, opérateur d'État)",
    "telecom":        "télécommunications (opérateur télécom, FAI, câblo-opérateur)",
    "spatial":        "secteur spatial (CNES, opérateurs satellites, industrie spatiale)",
    "eau":            "eau et assainissement (régie, délégataire, collectivité)",
    "alimentaire":    "agroalimentaire (industrie alimentaire, grande distribution)",
}


# ============================================================================
# TERMINOLOGIE ANSSI
# ============================================================================

# Termes interdits -> correction officielle ANSSI.
# Clés en minuscules pour comparaison via str.lower().
# Importé par : 03, 04, 07 et generate_corpus_6k.py
FORBIDDEN_TERMS: dict[str, str] = {
    # Valeurs métier
    "biens essentiels":           "valeurs métier",
    "bien essentiel":             "valeur métier",
    "actifs métier":              "valeurs métier",
    "actif métier":               "valeur métier",
    # Biens supports
    "actifs":                     "biens supports",
    "actif":                      "bien support",
    "ressources":                 "biens supports",
    "composants":                 "biens supports",
    # Sources de risque
    "menaces":                    "sources de risque",
    "menace":                     "source de risque",
    "threat":                     "source de risque",
    "attaquant":                  "source de risque",
    # Plan de traitement
    "pacs":                       "plan de traitement du risque",
    "plan d'assurance sécurité": "plan de traitement du risque",
    "plan de sécurité":           "plan de traitement du risque",
    # Parties prenantes
    "partie prenante externe":    "partie prenante",
    # Niveaux de risque
    "risque brut":                "risque initial",
    "risque net":                 "risque résiduel",
    "risque inhérent":            "risque initial",
    "risque traité":              "risque résiduel",
    # Terminologie ISO 27005 / EBIOS 2010
    "criticité":                  "niveau de risque",
    "probabilité":                "vraisemblance",
    "likelihood":                 "vraisemblance",
    "severity":                   "gravité",
}

# Termes obligatoires par atelier — au moins UN doit apparaître dans la réponse.
# Importé par : 04_quality_filter.py, 07_validate_corpus.py
REQUIRED_TERMS_BY_ATELIER: dict[str, list[str]] = {
    "A1": [
        "valeur métier", "valeurs métier",
        "bien support", "biens supports",
        "DICP", "disponibilité", "intégrité", "confidentialité",
        "socle de sécurité", "périmètre",
    ],
    "A2": [
        "source de risque", "sources de risque",
        "objectif visé", "objectifs visés",
        "pertinence", "motivation", "capacité",
        "retenue", "écartée",
    ],
    "A3": [
        "scénario stratégique", "scénarios stratégiques",
        "chemin d'attaque", "vraisemblance", "gravité",
        "partie prenante", "parties prenantes",
        "dangerosité", "niveau de risque", "risque initial",
    ],
    "A4": [
        "scénario opérationnel", "scénarios opérationnels",
        "mode opératoire", "vraisemblance", "gravité",
        "bien support", "biens supports",
        "MITRE", "ATT&CK",
    ],
    "A5": [
        "plan de traitement du risque",
        "risque résiduel", "mesure de sécurité", "mesures de sécurité",
        "homologation", "autorité d'homologation",
        "traitement", "réduction", "acceptation",
    ],
}


# ============================================================================
# ECHELLES OFFICIELLES EBIOS RM 2024
# ============================================================================

class Gravite(str, Enum):
    G1 = "G1"   # Mineure
    G2 = "G2"   # Significative
    G3 = "G3"   # Grave
    G4 = "G4"   # Critique


class Vraisemblance(str, Enum):
    V1 = "V1"   # Peu vraisemblable
    V2 = "V2"   # Vraisemblable
    V3 = "V3"   # Très vraisemblable
    V4 = "V4"   # Quasi-certain


GRAVITE_LABELS: dict[str, str] = {
    "G1": "Mineure",
    "G2": "Significative",
    "G3": "Grave",
    "G4": "Critique",
}

VRAISEMBLANCE_LABELS: dict[str, str] = {
    "V1": "Peu vraisemblable",
    "V2": "Vraisemblable",
    "V3": "Très vraisemblable",
    "V4": "Quasi-certain",
}

# Regex de détection des cotations G/V dans les textes générés.
# Importé par : 04_quality_filter.py, 07_validate_corpus.py, generate_corpus_6k.py
SCALE_PATTERN: re.Pattern = re.compile(r'\b(G[1-4]|V[1-4])\b')

# Formule dangerosité (Atelier 3) :
# dangerosité = (Dépendance × Pénétration) / (Maturité SSI × Confiance), facteurs 1-4
DANGEROSITE_SCALE: range = range(1, 5)


# ============================================================================
# PROMPT SYSTEME CANONIQUE
# Importé par : 02_generate_synthetics.py, 05_format_chatml.py,
#               07_validate_corpus.py, generate_corpus_6k.py
# ============================================================================

SYSTEM_PROMPT: str = (
    "Tu es un assistant expert EBIOS RM 2024, certifié selon la méthodologie "
    "officielle de l'ANSSI. Tu conduis et guides les analyses de risques selon "
    "les cinq ateliers EBIOS RM.\n\n"
    "RÈGLES TERMINOLOGIQUES ABSOLUES (non négociables) :\n"
    "- Valeurs métier (jamais 'biens essentiels', 'actifs métier' ou 'actifs')\n"
    "- Biens supports (jamais 'actifs', 'ressources' ou 'composants')\n"
    "- Sources de risque + objectifs visés (jamais 'menaces' ou 'threat')\n"
    "- Plan de traitement du risque (jamais 'PACS' ou 'plan d'assurance sécurité')\n"
    "- Risque initial / résiduel (jamais 'risque brut/net/inhérent/traité')\n"
    "- Vraisemblance (jamais 'probabilité' ou 'likelihood')\n"
    "- Gravité (jamais 'severity' au sens EBIOS RM)\n\n"
    "ÉCHELLES OFFICIELLES :\n"
    "- Gravité       : G1 (Mineure) | G2 (Significative) | G3 (Grave) | G4 (Critique)\n"
    "- Vraisemblance : V1 (Peu vraisemblable) | V2 (Vraisemblable) | "
    "V3 (Très vraisemblable) | V4 (Quasi-certain)\n"
    "- Dangerosité PP : (Dépendance × Pénétration) / (Maturité SSI × Confiance), "
    "facteurs notés de 1 à 4\n\n"
    "STRUCTURE DES CINQ ATELIERS :\n"
    "- A1 : Cadrage et socle de sécurité (valeurs métier, biens supports, DICP)\n"
    "- A2 : Sources de risque (couples SR/OV, pertinence, sélection)\n"
    "- A3 : Scénarios stratégiques (chemins d'attaque, parties prenantes, dangerosité)\n"
    "- A4 : Scénarios opérationnels (modes opératoires, MITRE ATT&CK, cotation G/V)\n"
    "- A5 : Traitement du risque (plan de traitement, risque résiduel, homologation)\n\n"
    "Tu réponds toujours en français, avec précision et rigueur méthodologique. "
    "Tu cites systématiquement les cotations G/V pour les ateliers A3, A4 et A5."
)


# ============================================================================
# GENERATION_TEMPLATES
# ----------------------------------------------------------------------------
# CONTRAT D'INTERFACE STRICT avec 02_generate_synthetics.py :
#   template = GENERATION_TEMPLATES[atelier]
#   prompt   = template.format(secteur=secteur, theme=theme)
#
# Seuls placeholders autorisés : {secteur} et {theme}.
# Les accolades JSON dans les templates sont doublées {{ }} pour échappement.
# ============================================================================

GENERATION_TEMPLATES: dict[str, str] = {

    "A1": (
        "Tu es un expert EBIOS RM 2024. Génère un exemple Q/A pour l'ATELIER 1 "
        "(Cadrage et socle de sécurité) dans le {secteur}.\n\n"
        "THÈME : {theme}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide (sans texte avant ni après) :\n"
        '{{"question": "question naturelle posée à l\'assistant (1-2 phrases)", '
        '"reponse": "réponse experte de 200 à 500 mots qui identifie des valeurs métier, '
        'des biens supports, applique les critères DICP et utilise '
        'exclusivement la terminologie ANSSI officielle."}}'
    ),

    "A2": (
        "Tu es un expert EBIOS RM 2024. Génère un exemple Q/A pour l'ATELIER 2 "
        "(Sources de risque) dans le {secteur}.\n\n"
        "THÈME : {theme}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide (sans texte avant ni après) :\n"
        '{{"question": "question naturelle posée à l\'assistant (1-2 phrases)", '
        '"reponse": "réponse experte de 200 à 500 mots qui caractérise 2-3 couples '
        '(source de risque / objectif visé), évalue motivation, capacité et pertinence, '
        'et conclut sur les sources de risque retenues pour l\'atelier 3."}}'
    ),

    "A3": (
        "Tu es un expert EBIOS RM 2024. Génère un exemple Q/A pour l'ATELIER 3 "
        "(Scénarios stratégiques) dans le {secteur}.\n\n"
        "THÈME : {theme}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide (sans texte avant ni après) :\n"
        '{{"question": "question naturelle posée à l\'assistant (1-2 phrases)", '
        '"reponse": "réponse experte de 300 à 600 mots qui présente un scénario '
        'stratégique complet (SS-XX, source de risque, objectif visé, valeurs métier '
        'ciblées, biens supports visés, chemin d\'attaque générique), cote en '
        'vraisemblance (V1-V4) et gravité (G1-G4) avec justification, et calcule '
        'si pertinent la dangerosité d\'une partie prenante."}}'
    ),

    "A4": (
        "Tu es un expert EBIOS RM 2024. Génère un exemple Q/A pour l'ATELIER 4 "
        "(Scénarios opérationnels) dans le {secteur}.\n\n"
        "THÈME : {theme}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide (sans texte avant ni après) :\n"
        '{{"question": "question naturelle posée à l\'assistant (1-2 phrases)", '
        '"reponse": "réponse experte de 300 à 600 mots qui détaille le mode opératoire '
        'étape par étape (reconnaissance, accès initial, persistance, mouvement latéral, '
        'impact), référence les techniques MITRE ATT&CK (format Txxxx), identifie les '
        'biens supports ciblés, cote en vraisemblance (V1-V4) et gravité (G1-G4), '
        'et propose des indicateurs de détection."}}'
    ),

    "A5": (
        "Tu es un expert EBIOS RM 2024. Génère un exemple Q/A pour l'ATELIER 5 "
        "(Traitement du risque) dans le {secteur}.\n\n"
        "THÈME : {theme}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide (sans texte avant ni après) :\n"
        '{{"question": "question naturelle posée à l\'assistant (1-2 phrases)", '
        '"reponse": "réponse experte de 300 à 600 mots qui propose un plan de traitement '
        'du risque (stratégie choisie + justification, mesures techniques >= 4 et '
        'organisationnelles >= 3), calcule le risque résiduel (nouvelle cotation G/V), '
        'et présente les éléments du dossier d\'homologation."}}'
    ),
}


# ============================================================================
# GENERATION_THEMES
# ----------------------------------------------------------------------------
# Utilisé par 02_generate_synthetics.py :
#   themes = GENERATION_THEMES[atelier]
#   theme  = themes[i % len(themes)]    <- rotation circulaire
#
# Enrichi de 26 -> 130 thèmes pour couvrir les 6 000 exemples cibles
# avec un maximum de 46 répétitions par thème (pour A3/A4 : 32 thèmes × 14 secteurs).
# ============================================================================

GENERATION_THEMES: dict[str, list[str]] = {

    # A1 — Cadrage et socle de sécurité (26 thèmes)
    "A1": [
        # Valeurs métier
        "identification et priorisation des valeurs métier de l'organisation",
        "distinction entre valeurs métier primaires et de soutien",
        "lien entre missions organisationnelles et valeurs métier EBIOS RM",
        "valeurs métier dans un contexte de transformation numérique",
        "valeurs métier partagées entre plusieurs entités d'un groupe",
        # Biens supports
        "cartographie des biens supports critiques à partir des valeurs métier",
        "identification des biens supports matériels, logiciels et organisationnels",
        "dépendances inter-biens supports et points de défaillance uniques",
        "biens supports hébergés dans le cloud : spécificités et périmètre",
        "biens supports partagés avec des tiers (infogérance, SaaS, mutualisation)",
        # DICP
        "évaluation des besoins de sécurité selon les critères DICP",
        "détermination de la propriété de sécurité dominante par valeur métier",
        "cotation des besoins de sécurité : grille d'évaluation et niveaux",
        "impact d'une atteinte à la disponibilité sur les valeurs métier critiques",
        "exigences de preuve et de traçabilité pour les processus réglementés",
        # Périmètre et parties prenantes
        "définition du périmètre de l'analyse EBIOS RM et justification des exclusions",
        "identification des parties prenantes de l'écosystème organisationnel",
        "frontières du système d'information et interconnexions avec l'extérieur",
        "périmètre d'une analyse EBIOS RM sur un projet SI en cours",
        # Socle et référentiels
        "établissement du socle de sécurité existant et écarts avec les référentiels",
        "référentiels applicables selon le secteur (RGS, HDS, IEC 62443, ISO 27001)",
        "mesures de sécurité déjà en place et leur efficacité estimée",
        "gouvernance de la sécurité : rôles et responsabilités dans l'analyse",
        "intégration de l'analyse EBIOS RM dans un SMSI existant",
        # Cas particuliers
        "analyse EBIOS RM dans un contexte multi-sites ou multi-entités",
        "cadrage d'une analyse EBIOS RM pour un projet en phase de conception",
    ],

    # A2 — Sources de risque (26 thèmes)
    "A2": [
        # Acteurs étatiques
        "caractérisation d'un groupe APT étatique ciblant ce secteur",
        "évaluation de la pertinence d'un État hostile comme source de risque",
        "APT à motivation stratégique : espionnage et pré-positionnement",
        "attribuabilité et ciblage sectoriel des groupes APT documentés",
        # Cybercriminels
        "évaluation d'un groupe cybercriminel opportuniste (ransomware-as-a-service)",
        "cybercriminel ciblé vs opportuniste : différences et implications",
        "groupes spécialisés dans le vol de données à revendre",
        "fraude financière et escroqueries au virement comme source de risque",
        # Insiders
        "analyse de la menace interne : employé malveillant ou négligent",
        "prestataire de service comme source de risque interne",
        "ex-employé conservant des accès résiduels : évaluation et pertinence",
        "compromission involontaire d'un utilisateur légitime (victime de phishing)",
        # Hacktivistes
        "pertinence des groupes hacktivistes pour ce secteur",
        "hacktivisme idéologique vs hacktivisme commandité",
        "capacités réelles des groupes hacktivistes et TTP typiques",
        # Espionnage économique
        "concurrent ou acteur économique hostile : espionnage industriel",
        "intelligence économique offensive et vol de propriété intellectuelle",
        # Supply chain
        "fournisseur logiciel compromis comme source de risque indirecte",
        "prestataire de maintenance avec accès privilégiés : dangerosité",
        "risques liés aux logiciels open source dans la chaîne d'approvisionnement",
        # Méthode A2
        "sélection et priorisation des sources de risque retenues pour l'atelier 3",
        "justification documentée des sources de risque écartées",
        "combinaison de plusieurs sources de risque dans un même scénario",
        "sources de risque émergentes : groupes IA offensifs, deepfakes",
        "évaluation comparative de la capacité de plusieurs sources de risque",
        "sources de risque dans un contexte géopolitique tendu",
    ],

    # A3 — Scénarios stratégiques (32 thèmes)
    "A3": [
        # Ransomware
        "scénario de ransomware ciblant les SI administratifs et opérationnels",
        "double extorsion (chiffrement + exfiltration) comme scénario stratégique",
        "ransomware ciblant les sauvegardes pour maximiser l'impact",
        "scénario ransomware via un prestataire comme vecteur initial",
        # Exfiltration
        "scénario d'exfiltration de données personnelles à grande échelle",
        "espionnage industriel : exfiltration de propriété intellectuelle",
        "exfiltration de données stratégiques par un acteur étatique",
        "exfiltration lente et discrète sur plusieurs mois (APT)",
        # Sabotage et déni de service
        "scénario de sabotage ciblant la disponibilité des services critiques",
        "déni de service distribué (DDoS) sur les services numériques exposés",
        "perturbation des processus industriels via les systèmes OT",
        "scénario d'interruption d'activité prolongée suite à cyberattaque",
        # Supply chain
        "compromission via la chaîne d'approvisionnement logicielle",
        "fournisseur de services cloud compromis comme vecteur d'attaque",
        "scénario de dépendance critique à un tiers non sécurisé",
        # Accès physiques
        "scénario de compromission physique (branchement rogue, vol de matériel)",
        "attaque combinée physique et logique sur une infrastructure critique",
        # Fraude et manipulation
        "fraude interne via abus de droits d'accès privilégiés",
        "manipulation de données à des fins financières ou de désinformation",
        "usurpation d'identité numérique d'un administrateur système",
        # Dangerosité des parties prenantes
        "calcul de dangerosité d'un prestataire cloud hébergeant des données sensibles",
        "dangerosité d'un intégrateur avec accès root sur les infrastructures",
        "dangerosité d'un sous-traitant intervenant sur les systèmes OT",
        "comparaison de la dangerosité de plusieurs parties prenantes",
        # Atteinte à l'image
        "scénario d'atteinte à la réputation via leak de données internes",
        "désinformation et manipulation de l'opinion publique",
        # Cas complexes
        "scénario multi-vecteurs combinant phishing, supply chain et insider",
        "scénario d'attaque longue durée avec pré-positionnement",
        "scénario ciblant la continuité des services lors d'une période critique",
        "hiérarchisation et priorisation de plusieurs scénarios stratégiques",
        "scénario sur infrastructure cloud ou SaaS externalisée",
        "scénario impliquant une vulnérabilité zero-day non patchée",
    ],

    # A4 — Scénarios opérationnels (28 thèmes)
    "A4": [
        # Accès initiaux
        "mode opératoire de spear-phishing ciblé sur un profil à privilèges",
        "exploitation d'une vulnérabilité web exposée (injection SQL, CVE récente)",
        "accès initial via credential stuffing sur un portail d'authentification",
        "compromission via un lien malveillant dans un email de confiance",
        "accès initial par exploitation d'un accès VPN sans MFA",
        # Persistance et mouvement latéral
        "établissement d'une persistance discrète après compromission initiale",
        "mouvement latéral via protocoles d'administration (RDP, WMI, SMB)",
        "élévation de privilèges depuis un compte standard vers admin local",
        "attaques sur Active Directory (Kerberoasting, Pass-the-Hash)",
        "passage du réseau IT vers le réseau OT via une passerelle mal segmentée",
        # Modes opératoires complets
        "mode opératoire complet d'un groupe ransomware (du phishing au chiffrement)",
        "mode opératoire d'exfiltration APT sur plusieurs mois",
        "attaque via watering hole sur un portail sectoriel fréquenté",
        "compromission de la supply chain logicielle (mise à jour malveillante)",
        "mode opératoire d'un insider utilisant ses accès légitimes",
        # OT et systèmes industriels
        "exploitation de vulnérabilités sur équipements OT/SCADA exposés",
        "manipulation d'automates industriels (PLC) après compromission réseau",
        "attaque sur infrastructure de supervision industrielle (ICS/SCADA)",
        "perturbation de processus physiques via la couche cyber (MITRE ICS ATT&CK)",
        # Cloud et identités
        "compromission d'un compte cloud administrateur (IAM, Entra ID)",
        "exploitation d'une misconfiguration de bucket de stockage cloud",
        "attaque sur une API exposée sans authentification robuste",
        "détournement DNS et interception des sessions utilisateurs",
        # Fraude et ingénierie sociale
        "arnaque au président (FOVI) comme scénario opérationnel détaillé",
        "ingénierie sociale téléphonique ciblant le support IT (vishing)",
        "attaque par clé USB infectée déposée dans les locaux (baiting)",
        # Détection
        "indicateurs de compromission (IoC) et points de détection pour ce scénario",
        "chronologie type d'une attaque et fenêtres d'opportunité de détection",
    ],

    # A5 — Traitement du risque (18 thèmes)
    "A5": [
        # Stratégies de traitement
        "choix entre réduction, transfert, acceptation et refus du risque",
        "justification de la stratégie de réduction pour un risque G3/V3",
        "conditions d'application du transfert du risque par assurance cyber",
        "acceptation d'un risque résiduel faible : formalisation et responsabilités",
        "refus de mise en service suite à risque résiduel jugé inacceptable",
        # Plan de traitement
        "élaboration du plan de traitement du risque pour un scénario critique",
        "priorisation P0/P1/P2 des mesures de sécurité sous contrainte budgétaire",
        "arbitrage entre mesures techniques et mesures organisationnelles",
        "mesures de sécurité réduisant la vraisemblance d'un scénario",
        "mesures de sécurité réduisant la gravité d'un scénario",
        # Risque résiduel
        "calcul et cotation du risque résiduel après application des mesures",
        "gestion d'un risque résiduel persistant supérieur au seuil acceptable",
        "présentation des risques résiduels à l'autorité d'homologation",
        # Homologation
        "structuration du dossier d'homologation à partir des résultats EBIOS RM",
        "composants obligatoires du dossier d'homologation (déclaration d'applicabilité, avis RSSI)",
        "durée de validité de l'homologation et conditions de révision anticipée",
        # Suivi
        "définition des indicateurs de suivi de la sécurité (KPI/KRI) post-homologation",
        "processus de revue annuelle et mise à jour de l'analyse EBIOS RM",
    ],
}


# ============================================================================
# DATACLASSES DU CORPUS
# ============================================================================

@dataclass
class Message:
    """Un tour de conversation (system | user | assistant)."""
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class CorpusExample:
    """
    Un exemple annoté du corpus EBIOS RM.

    Champs obligatoires : id, atelier, secteur, source, messages.
    Champs optionnels   : metadata, is_counterexample, error_type.
    """
    id: str                                              # ex: "qa_sante_a3_001"
    atelier: Literal["A1", "A2", "A3", "A4", "A5"]
    secteur: str                                         # valeur de SECTORS
    source: Literal["synthetic", "anonymized", "official_doc", "counterexample"]
    messages: list[Message]
    metadata: dict = field(default_factory=dict)
    is_counterexample: bool = False
    error_type: str | None = None                        # ex: "forbidden_term"

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "atelier":           self.atelier,
            "secteur":           self.secteur,
            "source":            self.source,
            "is_counterexample": self.is_counterexample,
            "error_type":        self.error_type,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in self.messages
            ],
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "CorpusExample":
        return CorpusExample(
            id=d["id"],
            atelier=d["atelier"],
            secteur=d["secteur"],
            source=d["source"],
            is_counterexample=d.get("is_counterexample", False),
            error_type=d.get("error_type"),
            messages=[Message(**m) for m in d["messages"]],
            metadata=d.get("metadata", {}),
        )
