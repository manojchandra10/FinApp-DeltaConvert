#!/bin/sh
# Reloads nginx at a fixed interval so certificates renewed by the certbot
# container take effect. nginx reads certificate files only when it starts
# or reloads, so without this a renewed certificate sits unused on disk
# until the old one expires. A reload is graceful: open connections finish
# on the old workers.
#
# The official nginx image runs every executable *.sh in /docker-entrypoint.d/
# before starting nginx. This script only starts the loop in the background
# and returns at once. NGINX_RELOAD_INTERVAL overrides the default of 6 hours
# (busybox sleep accepts values such as 30s, 15m or 6h).

interval="${NGINX_RELOAD_INTERVAL:-6h}"

(
    while sleep "$interval"; do
        nginx -s reload || echo "reload-certs: nginx reload failed" >&2
    done
    echo "reload-certs: invalid NGINX_RELOAD_INTERVAL '$interval'; periodic reload stopped" >&2
) &

echo "reload-certs: nginx will reload every $interval to pick up renewed certificates"
