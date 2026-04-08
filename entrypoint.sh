#!/bin/bash
# Copy default products.json to shared volume if not already present.
if [ ! -f /app/config/products.json ]; then
    mkdir -p /app/config
    if [ -f /app/config/products.json.default ]; then
        cp /app/config/products.json.default /app/config/products.json
        echo "[entrypoint] Seeded products.json from default."
    elif [ -f /app/config.baked/products.json ]; then
        cp /app/config.baked/products.json /app/config/products.json
        echo "[entrypoint] Seeded products.json from baked config."
    else
        echo "[entrypoint] WARNING: No products.json found and no default to seed from."
    fi
fi

exec "$@"
