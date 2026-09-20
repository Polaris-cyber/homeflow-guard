from __future__ import annotations

from typing import Any


DOMAIN_SERVICES: dict[str, dict[str, dict[str, tuple[float, float] | None]]] = {
    "light": {
        "light.turn_on": {"brightness": (0, 255)},
        "light.turn_off": {},
        "light.toggle": {},
    },
    "climate": {
        "climate.set_temperature": {"temperature": (5, 35)},
        "climate.turn_on": {},
        "climate.turn_off": {},
    },
    "cover": {
        "cover.open_cover": {},
        "cover.close_cover": {},
        "cover.set_cover_position": {"position": (0, 100)},
    },
    "media_player": {
        "media_player.media_play": {},
        "media_player.media_pause": {},
        "media_player.volume_set": {"volume_level": (0, 1)},
        "media_player.play_media": {"media_content_id": None, "media_content_type": None},
    },
    "lock": {
        "lock.lock": {},
        "lock.unlock": {},
    },
    "binary_sensor": {},
}


SENSITIVE_SERVICES = {"lock.unlock"}


ACTION_RESULT_STATES: dict[str, str] = {
    "light.turn_on": "on",
    "light.turn_off": "off",
    "climate.turn_on": "on",
    "climate.turn_off": "off",
    "cover.open_cover": "open",
    "cover.close_cover": "closed",
    "media_player.media_play": "playing",
    "media_player.media_pause": "paused",
    "lock.lock": "locked",
    "lock.unlock": "unlocked",
}


def default_services_for(domain: str) -> list[str]:
    return list(DOMAIN_SERVICES.get(domain, {}))


def service_parameters(service: str) -> dict[str, tuple[float, float] | None] | None:
    domain = service.split(".", 1)[0] if "." in service else ""
    return DOMAIN_SERVICES.get(domain, {}).get(service)


def infer_action_state(service: str, parameters: dict[str, Any], current: str) -> str:
    if service == "light.toggle":
        return "off" if current == "on" else "on"
    return ACTION_RESULT_STATES.get(service, current)
