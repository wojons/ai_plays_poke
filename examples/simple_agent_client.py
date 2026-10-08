"""CH-SPLIT increment 1: minimal NON-cron_runner agent client.

Proves an external agent can drive the environment purely through the HTTP
observe/act contract (see docs/api/env_service.md):

1. GET  /env/health
2. POST /env/boot    (if not already booted)
3. loop: GET /env/observe -> POST /env/act  (scripted 20-step walk)

Run from the repo root with the service up::

    uvicorn src.env_service:app --port 8765
    python examples/simple_agent_client.py --base-url http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json

import httpx

WALK_SCRIPT: list[str] = ["up", "left", "down", "right"] * 5  # 20 steps
ACT_FRAMES = 8
HTTP_TIMEOUT = 60.0


def boot_if_needed(client: httpx.Client, base_url: str) -> None:
    health = client.get(f"{base_url}/env/health").json()
    if health.get("booted"):
        print(f"[agent] already booted: {health.get('rom_path')}")
        return
    response = client.post(f"{base_url}/env/boot", json={})
    if response.status_code >= 400:
        raise SystemExit(f"[agent] boot failed: {response.status_code} {response.text}")
    print(f"[agent] booted: {response.json().get('rom_path')}")


def observe_act(
    client: httpx.Client, base_url: str, step: int, button: str
) -> dict[str, object]:
    response = client.post(
        f"{base_url}/env/act",
        json={"buttons": [button], "frames": ACT_FRAMES},
    )
    if response.status_code >= 400:
        raise SystemExit(
            f"[agent] act failed at step {step}: {response.status_code} {response.text}"
        )
    result: dict[str, object] = response.json()
    obs: dict[str, object] = result["observation"]  # type: ignore[assignment]
    print(
        f"[agent] step {step:02d} button={button:<5s} "
        f"location={obs.get('location')} "
        f"tile=({obs.get('player_tile_x')},{obs.get('player_tile_y')}) "
        f"screen={obs.get('screen_type')}"
    )
    return obs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scripted 20-step agent over the env HTTP contract",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        base_url = args.base_url.rstrip("/")
        boot_if_needed(client, base_url)
        observe = client.get(f"{base_url}/env/observe").json()
        print(
            f"[agent] start: location={observe.get('location')} "
            f"tile=({observe.get('player_tile_x')},"
            f"{observe.get('player_tile_y')})"
        )
        for step, button in enumerate(WALK_SCRIPT, start=1):
            observe_act(client, base_url, step, button)
        observe = client.get(f"{base_url}/env/observe").json()
        print("[agent] final observation:")
        print(json.dumps(observe, indent=2))


if __name__ == "__main__":
    main()
