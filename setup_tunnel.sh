#!/bin/bash

# Script pour configurer le tunnel HTTPS avec cloudflared

echo "🔧 Configuration du tunnel HTTPS..."

# Arrêter les anciens tunnels
pkill -f cloudflared || true
sleep 2

# Lancer le tunnel et capturer l'URL
echo "🚇 Démarrage du tunnel cloudflared..."
./cloudflared tunnel --url http://localhost:8000 --protocol http2 > cf_tunnel.log 2>&1 &
TUNNEL_PID=$!

# Attendre que le tunnel démarre
sleep 5

# Extraire l'URL HTTPS du tunnel
TUNNEL_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' cf_tunnel.log | head -1)

if [ -z "$TUNNEL_URL" ]; then
    echo "❌ Impossible de récupérer l'URL du tunnel"
    echo "📋 Vérifiez manuellement dans cf_tunnel.log"
    cat cf_tunnel.log | grep -i "https://" | head -3
    exit 1
fi

echo "✅ Tunnel actif sur: $TUNNEL_URL"
echo ""
echo "📝 Mise à jour de la configuration..."

# Mettre à jour le .env
CALLBACK_URL="${TUNNEL_URL}/callback"
sed -i '' "s|SPOTIFY_REDIRECT_URI=.*|SPOTIFY_REDIRECT_URI=${CALLBACK_URL}|g" .env

echo "✅ Configuration mise à jour dans .env"
echo ""
echo "🔗 URI de callback: $CALLBACK_URL"
echo ""
echo "⚠️  IMPORTANT: Ajoutez cette URI dans votre Spotify Dashboard:"
echo "   1. Allez sur https://developer.spotify.com/dashboard"
echo "   2. Ouvrez votre application"
echo "   3. Cliquez sur 'Edit Settings'"
echo "   4. Dans 'Redirect URIs', ajoutez: $CALLBACK_URL"
echo "   5. Cliquez sur 'Add' puis 'Save'"
echo ""
echo "🔄 Redémarrez le serveur FastAPI pour prendre en compte les changements"
echo ""
echo "📊 Le tunnel tourne en arrière-plan (PID: $TUNNEL_PID)"
echo "📋 Logs disponibles dans: cf_tunnel.log"
