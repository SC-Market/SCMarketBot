"""Links to sc-market.space pages, for embed titles (one site link per message)."""
from urllib.parse import quote

SITE = "https://sc-market.space"


def site_url(*segments: str) -> str:
    """SITE plus path segments, each percent-encoded; no segments is the home page."""
    if not segments:
        return SITE
    return SITE + "/" + "/".join(quote(str(s), safe="") for s in segments)
