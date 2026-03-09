import requests
from ..models import SourceSearchRequest, SourceSearchResult
from .base import BaseSourceConnector

FREESOUND_API_BASE = "https://freesound.org/apiv2"


class FreesoundConnector(BaseSourceConnector):
    source_name = "freesound"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, request: SourceSearchRequest) -> list[SourceSearchResult]:
        params = {
            "query": request.query,
            "page_size": min(request.limit, 150),
            "fields": (
                "id,name,description,username,license,duration,"
                "type,download,previews,tags"
            ),
            "filter": self._build_filter(request.filters),
            "token": self.api_key,
        }
        try:
            resp = requests.get(f"{FREESOUND_API_BASE}/search/text/", params=params, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[freesound] search error: {e}")
            return []

        results = []
        for item in resp.json().get("results", []):
            license_str = item.get("license", "")
            result = SourceSearchResult(
                source_name="freesound",
                source_item_id=str(item["id"]),
                source_url=f"https://freesound.org/s/{item['id']}/",
                title=item.get("name"),
                description=item.get("description"),
                creator=item.get("username"),
                license=license_str,
                attribution_required=True,
                commercial_use_allowed="0" in license_str or "by" in license_str.lower(),
                derivative_use_allowed="nd" not in license_str.lower(),
                duration_seconds=item.get("duration"),
                original_format="mp3",  # previews are always mp3
                # Use preview URL — full download requires OAuth2.
                # preview-hq-mp3 is publicly accessible with just the token as a param.
                download_url=item.get("previews", {}).get("preview-hq-mp3"),
                preview_url=item.get("previews", {}).get("preview-hq-mp3"),
                source_tags=item.get("tags", []),
                raw_metadata=item,
            )
            results.append(result)

        print(f"[freesound] found {len(results)} results for '{request.query}'")
        return results

    def _build_filter(self, filters: dict) -> str:
        parts = []
        min_dur = filters.get("min_duration")
        max_dur = filters.get("max_duration")
        if min_dur or max_dur:
            lo = min_dur or "*"
            hi = max_dur or "*"
            parts.append(f"duration:[{lo} TO {hi}]")
        license_filter = filters.get("license")
        if license_filter:
            parts.append(f'license:"{license_filter}"')
        return " ".join(parts) if parts else ""
