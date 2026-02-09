# 🔧 Configuration Spotify Dashboard - Guide Étape par Étape

## ⚠️ ERREUR "INVALID_CLIENT: Invalid redirect URI"

Cette erreur signifie que l'URI de redirection dans votre Dashboard Spotify ne correspond **PAS EXACTEMENT** à celle utilisée par l'application.

## ✅ Solution

### Étape 1 : Vérifier l'URI actuelle

L'application utilise actuellement :
```
https://carl-advisors-camcorder-city.trycloudflare.com/callback
```

### Étape 2 : Configurer le Spotify Dashboard

1. **Allez sur** : https://developer.spotify.com/dashboard
2. **Connectez-vous** avec votre compte Spotify
3. **Cliquez sur votre application** (celle avec le Client ID utilisé)
4. **Cliquez sur "Edit Settings"** (bouton vert en haut à droite)
5. **Dans la section "Redirect URIs"** :
   - **SUPPRIMEZ** toutes les anciennes URIs (surtout celles avec `localhost` ou `127.0.0.1`)
   - **AJOUTEZ EXACTEMENT** cette URI (copiez-collez) :
     ```
     https://carl-advisors-camcorder-city.trycloudflare.com/callback
     ```
   - ⚠️ **ATTENTION** : 
     - Pas d'espace avant/après
     - Pas de `/` à la fin
     - Exactement comme ci-dessus
6. **Cliquez sur "Add"** puis **"Save"**

### Étape 3 : Vérifier

Après avoir sauvegardé, vérifiez que l'URI apparaît bien dans la liste des Redirect URIs.

### Étape 4 : Tester

1. Ouvrez : `https://carl-advisors-camcorder-city.trycloudflare.com/ui`
2. Cliquez sur "Se connecter avec Spotify"
3. Si ça fonctionne, vous serez redirigé vers Spotify pour autoriser l'application

## 🔄 Si l'URI du tunnel change

Si vous redémarrez cloudflared, l'URL peut changer. Dans ce cas :

1. Vérifiez la nouvelle URL dans `cf_tunnel.log` :
   ```bash
   grep "https://" cf_tunnel.log | tail -1
   ```

2. Mettez à jour le `.env` :
   ```bash
   # Remplacez OLD_URL par la nouvelle URL
   sed -i '' 's|SPOTIFY_REDIRECT_URI=.*|SPOTIFY_REDIRECT_URI=https://NOUVELLE-URL.trycloudflare.com/callback|g' .env
   ```

3. Redémarrez le serveur :
   ```bash
   pkill -f uvicorn
   uvicorn app:app --reload --port 8000
   ```

4. **Mettez à jour le Dashboard Spotify** avec la nouvelle URI

## 📝 Checklist

- [ ] URI ajoutée dans Spotify Dashboard
- [ ] Anciennes URIs supprimées (localhost, 127.0.0.1)
- [ ] URI correspond exactement (pas d'espace, pas de `/` à la fin)
- [ ] Dashboard sauvegardé
- [ ] Tunnel cloudflared actif
- [ ] Serveur FastAPI actif sur port 8000

## 🆘 Si ça ne fonctionne toujours pas

1. Vérifiez que vous utilisez le **bon Client ID** dans votre `.env`
2. Vérifiez que le **Client Secret** est correct
3. Essayez de **rotater le Client Secret** dans le Dashboard (Edit Settings → Rotate client secret)
4. Vérifiez les logs du serveur pour voir l'erreur exacte
