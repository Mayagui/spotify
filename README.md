# 🎵 Spotify Group Playlist Generator - Système de Recommandation Avancé

Application FastAPI pour générer des playlists de groupe Spotify avec des algorithmes de recommandation intelligents (collaborative filtering, content-based, hybride).

## ✨ Fonctionnalités

- **🔐 Authentification OAuth Spotify** : Connexion sécurisée avec gestion automatique des tokens
- **👥 Multi-utilisateurs** : Plusieurs utilisateurs peuvent se connecter et contribuer
- **🤖 Recommandation Collaborative** : Analyse les similarités entre utilisateurs pour recommander des titres
- **🎼 Recommandation Content-Based** : Recommandations basées sur les caractéristiques audio (tempo, énergie, valence, etc.)
- **🔮 Modèle Hybride** : Combine collaborative et content-based avec poids configurables
- **💾 Persistance SQLite** : Stockage des utilisateurs, tracks, feedbacks et historique d'écoute
- **📊 Feedback Utilisateur** : Système de likes/skips/dislikes pour améliorer les recommandations
- **🎨 Interface Moderne** : UI intuitive avec contrôles avancés

## 📋 Prérequis

- Python 3.10+
- Compte Spotify Developer avec application créée
- Redirect URI configuré dans Spotify Dashboard

## 🚀 Installation

1. **Cloner le projet** (ou utiliser le dossier existant)

2. **Créer un environnement virtuel** :
```bash
python3 -m venv .venv
source .venv/bin/activate  # Sur macOS/Linux
# ou
.venv\Scripts\activate  # Sur Windows
```

3. **Installer les dépendances** :
```bash
pip install -r requirements.txt
```

4. **Configurer les variables d'environnement** :
Créez un fichier `.env` à la racine du projet :
```env
SPOTIFY_CLIENT_ID=votre_client_id
SPOTIFY_CLIENT_SECRET=votre_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
APP_SECRET_KEY=votre_secret_key_aleatoire
DATABASE_URL=sqlite:///./spotify.db
```

5. **Configurer Spotify Dashboard** :
   - Allez sur [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Créez une nouvelle app
   - Ajoutez `http://localhost:8000/callback` dans "Redirect URIs"
   - Copiez le Client ID et Client Secret dans votre `.env`

## 🎯 Lancement

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Lancer le serveur FastAPI
uvicorn app:app --reload --port 8000
```

L'application sera accessible sur `http://localhost:8000`

## 📖 Utilisation

### Interface Web

1. Ouvrez `http://localhost:8000/ui` dans votre navigateur
2. Cliquez sur "Se connecter avec Spotify"
3. Autorisez l'application dans Spotify
4. Une fois connecté, vous verrez la liste des membres
5. Configurez les paramètres de génération :
   - **Algorithme** : Hybride (recommandé), Collaboratif, Content-Based, ou Simple
   - **Poids** (pour hybride) : Ajustez le ratio entre content-based et collaboratif
   - **Nom** : Nom de votre playlist
   - **Description** : Description optionnelle
   - **Nombre de morceaux** : Entre 10 et 100
6. Cliquez sur "Générer la Playlist"
7. La playlist sera créée dans votre compte Spotify !

### API Endpoints

#### `GET /`
Retourne les routes disponibles

#### `GET /ui`
Interface web principale

#### `GET /login`
Redirige vers l'authentification Spotify

#### `GET /callback`
Callback OAuth après authentification Spotify

#### `GET /members`
Liste tous les membres connectés
```json
{
  "members": [
    {
      "spotify_id": "user123",
      "display_name": "John Doe",
      "profile_image": "https://..."
    }
  ]
}
```

#### `POST /generate`
Génère une playlist de groupe
```json
{
  "member_ids": ["user1", "user2"],
  "name": "Ma Playlist de Groupe",
  "description": "Générée automatiquement",
  "public": false,
  "limit": 30,
  "preferences": {
    "method": "hybrid",
    "content_weight": 0.6,
    "collab_weight": 0.4
  }
}
```

#### `POST /feedback`
Enregistre un feedback utilisateur
```json
{
  "track_id": "spotify_track_id",
  "feedback_type": "like"  // "like", "skip", ou "dislike"
}
```
Query param: `spotify_user_id`

#### `GET /recommendations/{spotify_user_id}`
Retourne des recommandations personnalisées pour un utilisateur
Query params: `limit` (défaut: 20)

#### `GET /stats/{spotify_user_id}`
Retourne les statistiques d'un utilisateur

## 🧠 Algorithmes de Recommandation

### 1. Collaborative Filtering
- Analyse les similarités entre utilisateurs
- Recommande des titres aimés par des utilisateurs similaires
- Utilise les feedbacks explicites (likes/skips/dislikes) et l'historique d'écoute

### 2. Content-Based Filtering
- Analyse les caractéristiques audio des morceaux (danceability, energy, valence, tempo, etc.)
- Calcule la similarité cosinus entre tracks
- Recommande des morceaux similaires aux favoris de l'utilisateur

### 3. Modèle Hybride
- Combine les deux approches avec des poids configurables
- Par défaut : 60% content-based, 40% collaboratif
- Permet d'ajuster le ratio selon les préférences

### 4. Méthode Simple
- Déduplication et mélange aléatoire des favoris
- Pas d'algorithme avancé, méthode de base

## 🗄️ Base de Données

L'application utilise SQLModel avec SQLite par défaut. Les tables suivantes sont créées automatiquement :

- **spotify_users** : Utilisateurs connectés avec leurs tokens
- **tracks** : Morceaux avec leurs audio features
- **user_feedback** : Feedback utilisateur (likes/skips/dislikes)
- **listening_history** : Historique d'écoute

Pour utiliser PostgreSQL en production, modifiez `DATABASE_URL` dans `.env` :
```env
DATABASE_URL=postgresql://user:password@localhost:5432/spotify_db
```

## 🔧 Configuration Avancée

### Scopes Spotify Requis
- `user-top-read` : Lire les top tracks/artists
- `user-read-recently-played` : Historique d'écoute
- `playlist-modify-public` : Créer/modifier playlists publiques
- `playlist-modify-private` : Créer/modifier playlists privées
- `user-read-private` : Lire le profil utilisateur
- `user-read-email` : Lire l'email

### Variables d'Environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `SPOTIFY_CLIENT_ID` | Client ID Spotify (requis) | - |
| `SPOTIFY_CLIENT_SECRET` | Client Secret Spotify (requis) | - |
| `SPOTIFY_REDIRECT_URI` | URI de redirection OAuth | `http://localhost:8000/callback` |
| `APP_SECRET_KEY` | Clé secrète pour sessions | `dev-secret-change-me` |
| `DATABASE_URL` | URL de la base de données | `sqlite:///./spotify.db` |

## 🐛 Dépannage

### Erreur "INVALID_CLIENT: Insecure redirect URI"
- Vérifiez que l'URI dans `.env` correspond exactement à celle dans Spotify Dashboard
- Pour développement local, utilisez `http://localhost:8000/callback` (pas `127.0.0.1`)
- Pour HTTPS, utilisez un tunnel (cloudflared, ngrok) et mettez à jour les deux endroits

### Erreur "Token invalide"
- Les tokens expirent après 1 heure
- L'application rafraîchit automatiquement les tokens avec le refresh_token
- Si le problème persiste, reconnectez-vous via `/login`

### Aucune recommandation générée
- Vérifiez que les utilisateurs ont des top tracks dans leur compte Spotify
- Pour collaborative filtering, il faut au moins 2 utilisateurs avec des feedbacks
- Essayez la méthode "simple" en fallback

## 📝 Notes

- `.env` n'est pas versionné pour des raisons de sécurité
- Pour la production, utilisez une base de données PostgreSQL et un stockage sécurisé des secrets
- Les tokens sont stockés en clair dans SQLite (à chiffrer en production)

## 🎨 Améliorations UX/UI

- Interface moderne avec animations
- Contrôles intuitifs pour les algorithmes
- Feedback visuel en temps réel
- Affichage des statistiques de génération
- Avatars utilisateurs depuis Spotify

## 📚 Structure du Projet

```
spotify/
├── app.py                      # Application FastAPI principale
├── models.py                   # Modèles SQLModel (User, Track, Feedback, etc.)
├── database.py                 # Configuration base de données
├── recommendation_service.py   # Service de recommandation (algorithms)
├── group_playlist.py           # Logique de génération de playlist
├── spotify_oauth.py            # Gestion OAuth Spotify
├── store.py                    # Store SQLite (legacy, pour compatibilité)
├── config.py                   # Configuration et variables d'environnement
├── requirements.txt            # Dépendances Python
├── templates/
│   └── index.html              # Interface web
└── README.md                   # Ce fichier
```

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

## 📄 Licence

Ce projet est fourni tel quel, sans garantie.
