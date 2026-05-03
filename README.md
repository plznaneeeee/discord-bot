# 🤖 Bot Discord — Guide d'installation

## 📦 Prérequis
- Python 3.10 ou supérieur
- Un compte Discord + bot créé sur le [Portail Développeurs](https://discord.com/developers/applications)

---

## ⚙️ Installation

### 1. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 2. Configurer le token
Dans `bot.py`, remplace la ligne :
```python
BOT_TOKEN = "VOTRE_TOKEN_ICI"
```
par ton token Discord (disponible dans l'onglet **Bot** du portail développeurs).

### 3. Lancer le bot
```bash
python bot.py
```

---

## 🔑 Permissions requises pour le bot
Dans le portail développeurs, active ces **Privileged Gateway Intents** :
- ✅ Server Members Intent
- ✅ Message Content Intent

Et donne ces permissions lors de l'invitation :
- Gérer les rôles
- Expulser/Bannir des membres
- Gérer les messages
- Gérer les salons
- Lire/Envoyer des messages

---

## 📋 Commandes disponibles

### 🔨 Modération
| Commande | Description |
|----------|-------------|
| `+kick @membre raison` | Expulse un membre |
| `+ban @membre raison` | Bannit un membre |
| `+unban ID raison` | Débannit via l'ID |
| `+mute @membre raison` | Mute permanent |
| `+unmute @membre` | Unmute un membre |
| `+tempmute @membre 5min raison` | Mute temporaire |
| `+warn @membre raison` | Avertit un membre |
| `+warnings @membre` | Voir les avertissements |
| `+clearwarns @membre` | Effacer les avertissements |
| `+purge 10` | Supprime X messages |

### ⏱️ Formats de durée pour tempmute
- `30s` → 30 secondes
- `5min` → 5 minutes
- `2h` → 2 heures
- `1j` ou `1d` → 1 jour

### 🎭 Rôles
| Commande | Description |
|----------|-------------|
| `+addrole @membre @rôle` | Ajoute un rôle |
| `+removerole @membre @rôle` | Retire un rôle |
| `+roles [@membre]` | Affiche les rôles |

### 🎫 Tickets
| Commande | Description |
|----------|-------------|
| `+ticket-setup [catégorie] [rôle]` | Crée le panel tickets |
| `+add-to-ticket @membre` | Ajoute qqn au ticket |

### 🛡️ Auto-modération & Configuration
| Commande | Description |
|----------|-------------|
| `+setlog #salon` | Définit le salon de logs |
| `+automod antispam on/off` | Active/désactive anti-spam |
| `+automod antilink on/off` | Active/désactive anti-liens |
| `+automod all on/off` | Active/désactive tout |
| `+antilink-bypass @rôle` | Rôle qui peut envoyer des liens |

### ℹ️ Utilitaires
| Commande | Description |
|----------|-------------|
| `+userinfo [@membre]` | Infos sur un membre |
| `+serverinfo` | Infos sur le serveur |
| `+ping` | Latence du bot |

---

## 🔧 Mise en place recommandée

1. **Logs** → `+setlog #logs-modération`
2. **Anti-spam** → activé par défaut
3. **Anti-liens** → activé par défaut (désactive avec `+automod antilink off`)
4. **Tickets** → `+ticket-setup` dans le salon souhaité

---

## 📝 Notes
- La configuration est sauvegardée dans `config.json`
- Les avertissements (`+warn`) sont en mémoire (redémarrage = reset)
- Pour persister les warns, une base de données (SQLite/PostgreSQL) peut être ajoutée
