# 🔌 Darkmoon — MCP (Model Context Protocol)

Ce document décrit **le serveur MCP Darkmoon**, son rôle, son fonctionnement,
et pourquoi il est **central** dans l’architecture.

Public cible :
- architectes
- développeurs backend
- AI engineers
- experts sécurité

---

## 1. Qu’est-ce que le MCP dans Darkmoon ?

Le MCP (Model Context Protocol) est **la frontière de sécurité et d’exécution**
entre :

- l’IA (OpenCode + agents),
- les outils réels de pentest.

👉 L’IA **ne touche jamais directement** aux outils.
👉 Tout passe par le MCP.

---

## 2. Rôle du MCP Darkmoon

Le MCP sert à :

- exposer des **fonctions contrôlées** à l’IA,
- exécuter des commandes dans la toolbox Docker,
- fournir des **workflows métiers** prêts à l’emploi,
- empêcher toute action non autorisée.

---

## 3. Implémentation technique

Le MCP Darkmoon est implémenté avec **FastMCP**.

Emplacement :

```

mcp/src/server.py

```

Il expose :
- des outils simples,
- des outils avancés,
- des workflows dynamiques.

---

## 4. Outils MCP exposés

### 4.1 Santé & diagnostic

- `health_check`
- `check_tool`
- `diagnose`

👉 Permet à l’IA de vérifier l’état du système **avant d’attaquer**.

---

### 4.2 Exécution générique

- `execute_command`
- `list_allowed_tools`

Caractéristiques :
- whitelist stricte,
- protection contre commandes dangereuses,
- timeouts contrôlés.

---

### 4.3 Workflows dynamiques

- `list_workflows`
- `run_workflow`

Les workflows sont découverts **automatiquement** au runtime.

---

## 5. Interaction avec Docker

Le MCP utilise :
- l’API Docker locale,
- un client dédié (`DarkmoonDockerClient`),
- un nom de conteneur fixe (`darkmoon`).

👉 Le MCP :
- ne dépend pas du shell utilisateur,
- ne dépend pas du host,
- reste isolé.

---

## 6. Exemple d’utilisation côté IA

Dans le chat OpenCode :

> “exécute un scan de vulnérabilité sur example.com”

L’IA :
1. identifie le besoin,
2. choisit le workflow,
3. appelle `run_workflow`,
4. interprète les résultats,
5. enchaîne si nécessaire.

---

## 7. Sécurité par design

Le MCP impose :
- aucune exécution libre,
- aucun accès Docker direct,
- aucun montage non maîtrisé,
- aucune élévation implicite.

👉 C’est la **clé de la sécurité globale** de Darkmoon.

---

## 8. Étendre le MCP

Pour ajouter une fonctionnalité :

1. créer un nouveau workflow,
2. ou ajouter un outil MCP,
3. redémarrer le serveur MCP.

Aucune modification côté agent requise.

---

## 9. Pourquoi ce design est robuste

- séparation IA / exécution,
- auditabilité totale,
- extensibilité contrôlée,
- réduction massive des risques.

---

## 10. Résumé

Le MCP est :
- le **cœur d’exécution** de Darkmoon,
- la **barrière de sécurité**,
- le point d’extension principal.

---

➡️ Pour comprendre les outils réels :
voir `docs/toolbox.md`