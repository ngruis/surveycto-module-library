import json

from surveycto_module_library.credentials import (
    SERVICE,
    Credentials,
    load_credentials,
    save_credentials,
)


def test_credentials_use_one_keyring_item(monkeypatch):
    calls = []
    encoded = json.dumps({"username": "tester", "password": "secret"})

    def get_password(service, account):
        calls.append((service, account))
        return encoded

    monkeypatch.setattr("surveycto_module_library.credentials.keyring.get_password", get_password)

    assert load_credentials("example") == Credentials("tester", "secret")
    assert calls == [(SERVICE, "example:credentials")]


def test_credentials_are_saved_together(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "surveycto_module_library.credentials.keyring.set_password",
        lambda service, account, password: calls.append((service, account, password)),
    )

    save_credentials("example", "tester", "secret")

    assert len(calls) == 1
    service, account, encoded = calls[0]
    assert service == SERVICE
    assert account == "example:credentials"
    assert json.loads(encoded) == {"username": "tester", "password": "secret"}


def test_invalid_combined_credentials_are_ignored(monkeypatch):
    monkeypatch.setattr(
        "surveycto_module_library.credentials.keyring.get_password",
        lambda service, account: "not-json",
    )

    assert load_credentials("example") is None
