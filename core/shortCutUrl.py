"""Mantém URLs originais sem encaminhá-las a serviços de encurtamento."""
from lib.http import validate_url


def shortCutUrl(url):
    if not url:
        return None
    return validate_url(url)
