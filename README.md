# Playlist de groupe Spotify (Flask)

## Prérequis
- Python 3.10+
- Compte Spotify Developer (app créée, Redirect URI configurée)

## Installation
1. Copiez `.env.example` en `.env` et remplissez vos identifiants Spotify.
2. Installez les dépendances :
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement
```bash
export FLASK_APP=app.py
flask run --port 5050 --debug
```

## Flux
- Ouvrez `http://localhost:5050/ui` et cliquez sur « Se connecter ».
- Après redirection, l'utilisateur est enregistré dans le store SQLite.
- Liste des membres: `GET /members`.
- Générer une playlist: `POST /generate` avec JSON:
```json
{
  "member_ids": ["spotify_user_id_1", "spotify_user_id_2"],
  "name": "Ma Playlist de Groupe",
  "description": "Générée automatiquement",
  "public": false,
  "preferences": {
    "limit": 30,
    "target_energy": null,
    "target_valence": null
  }
}
```

### Persistance (SQLite)
- Une base locale `app.db` est créée automatiquement (variable `SPOTIFY_APP_DB` pour changer l'emplacement).
- Les tokens sont stockés par `spotify_user_id` et rafraîchis automatiquement.

## Scopes requis
- `user-top-read`
- `playlist-modify-private` (ou `playlist-modify-public`)

## Notes
- `.env` n'est pas versionné; partagez les valeurs via `.env.example`.
- Pour la prod, utilisez une base de données et un stockage sécurisé des secrets.
