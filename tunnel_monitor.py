import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import docker

# Only accept an actual Tunnelmole forwarding line, not the example URL printed
# by `tmole --help` if the tunnel command ever fails to start.
URL_PATTERN = re.compile(
    r'https://[a-zA-Z0-9-]+\.(?:trycloudflare\.com|tunnelmole\.net)(?=\s+⟶)'
)
OUTPUT = Path('/app/data/tunnel_url.txt')


def is_url_healthy(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TunnelMonitor/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            content = response.read().decode('utf-8', errors='ignore')
            if 'No matching tunnelmole domain' in content:
                return False
            return True
    except urllib.error.HTTPError as error:
        try:
            content = error.read().decode('utf-8', errors='ignore')
            if 'No matching tunnelmole domain' in content:
                return False
        except Exception:
            pass
        return True
    except Exception:
        return True


def restart_tunnel_safely(client, tunnel):
    try:
        fresh_tunnel = client.containers.get(tunnel.id)
        fresh_tunnel.restart()
    except docker.errors.APIError as error:
        print(
            f'Direct tunnel restart failed ({error}). Attempting proxy network recovery...',
            flush=True,
        )
        try:
            proxies = client.containers.list(filters={'label': 'com.docker.compose.service=proxy'})
            if proxies:
                proxies[0].restart()
            fresh_tunnel = client.containers.get(tunnel.id)
            fresh_tunnel.restart()
        except Exception as recovery_error:
            print(f'Tunnel recovery failed: {recovery_error}', flush=True)


def main():
    client = docker.from_env()
    previous_url = ''
    previous_tunnel_id = ''
    url_first_seen = 0.0
    consecutive_failures = 0

    while True:
        try:
            tunnels = client.containers.list(filters={'label': 'com.docker.compose.service=tunnel'})
            tunnel = tunnels[0] if tunnels else None
            tunnel_id = tunnel.id if tunnel else ''
            if tunnel_id != previous_tunnel_id:
                OUTPUT.unlink(missing_ok=True)
                previous_url = ''
                url_first_seen = 0.0
                consecutive_failures = 0
                previous_tunnel_id = tunnel_id
            # Tunnelmole prints its public URL once at startup. Vite requests can
            # quickly push that line out of a short log tail, leaving the monitor
            # unhealthy forever. Read this tunnel instance's full startup log
            # until its URL is discovered; afterwards no log scan is needed.
            logs = (
                tunnel.logs().decode('utf-8', errors='ignore')
                if tunnel and not previous_url
                else ''
            )
            matches = URL_PATTERN.findall(logs)
            if matches:
                public_url = matches[-1].rstrip('/').rstrip('.,;)')
                if public_url != previous_url:
                    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
                    OUTPUT.write_text(f'{public_url}\n', encoding='utf-8')
                    previous_url = public_url
                    url_first_seen = time.time()
                    consecutive_failures = 0
                    print(f'Published WebApp URL: {previous_url}', flush=True)

            if previous_url and tunnel and (time.time() - url_first_seen > 30):
                if not is_url_healthy(previous_url):
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        print(
                            f'Tunnel domain expired or dropped: {previous_url}. '
                            f'Restarting tunnel container...',
                            flush=True,
                        )
                        restart_tunnel_safely(client, tunnel)
                        previous_url = ''
                        consecutive_failures = 0
                else:
                    consecutive_failures = 0
        except Exception as error:
            print(f'Tunnel monitor error: {error}', flush=True)
        time.sleep(5)


if __name__ == '__main__':
    main()
