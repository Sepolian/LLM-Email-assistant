"""Microsoft Graph authentication helper (skeleton).

Use MSAL (msal library) to acquire tokens for Microsoft Graph.
"""
from typing import Any, Dict


def acquire_token_interactively(client_id: str, tenant_id: str, scopes: list):
    """Interactive flow using MSAL PublicClientApplication or ConfidentialClientApplication.

    TODO: implement.
    """
    raise NotImplementedError()


def acquire_token_silent(account, app):
    """Try to get token silently."""
    raise NotImplementedError()
