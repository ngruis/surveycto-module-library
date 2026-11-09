from __future__ import annotations

import getpass
import json
import subprocess
from dataclasses import dataclass

import keyring

SERVICE = "J-PAL MENA SurveyCTO Module Library"


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


def load_credentials(server: str) -> Credentials | None:
    encoded = keyring.get_password(SERVICE, f"{server}:credentials")
    if not encoded:
        return None
    try:
        payload = json.loads(encoded)
        username = str(payload["username"])
        password = str(payload["password"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not username or not password:
        return None
    return Credentials(username=username, password=password)


def save_credentials(server: str, username: str, password: str) -> None:
    keyring.set_password(
        SERVICE,
        f"{server}:credentials",
        json.dumps({"username": username, "password": password}),
    )


def prompt_and_save(server: str, popup: bool = False) -> Credentials:
    if popup:
        username = _mac_dialog("SurveyCTO username", "Enter your SurveyCTO username:", hidden=False)
        password = _mac_dialog("SurveyCTO password", "Enter your SurveyCTO password:", hidden=True)
    else:
        username = input("SurveyCTO username: ").strip()
        password = getpass.getpass("SurveyCTO password: ")
    if not username or not password:
        raise RuntimeError("A SurveyCTO username and password are required.")
    save_credentials(server, username, password)
    return Credentials(username=username, password=password)


def _mac_dialog(title: str, prompt: str, hidden: bool) -> str:
    script = 'display dialog "{}" with title "{}" default answer ""{}'.format(
        prompt.replace('"', '\\"'),
        title.replace('"', '\\"'),
        " with hidden answer" if hidden else "",
    )
    script += "\nreturn text returned of result"
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
