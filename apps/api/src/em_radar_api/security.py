# SPDX-License-Identifier: Apache-2.0

"""Credential-masking helpers shared across the API package."""


def mask_secret(secret: str) -> str:
    """Return a masked representation showing only the last 4 characters.

    Tokens shorter than or equal to 4 characters are fully masked to `****`
    so that the mask itself reveals no information about token length.
    """
    if len(secret) <= 4:
        return "****"
    return f"****{secret[-4:]}"
