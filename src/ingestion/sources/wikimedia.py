import requests
from ..models import SourceSearchRequest, SourceSearchResult
from .base import BaseSourceConnector

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


class WikimediaConnector(BaseSourceConnector):
    source_name = "wikimedia"

    def search(self, request: SourceSearchRequest) -> list[SourceSearchResult]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{request.query} filetype:audio",
            "gsrlimit": min(request.limit, 50),
            "gsroffset": (request.page - 1) * min(request.limit, 50),
            "gsrnamespace": 6,
            "prop": "imageinfo|categories",
            "iiprop": "url|mime|size|extmetadata",
            "format": "json",
        }
        headers = {
            "User-Agent": "BecomingSoundEngine/1.0 (https://github.com/absybvc-cloud/Becoming; sound art project)",
        }
        try:
            resp = requests.get(WIKIMEDIA_API, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
        except Exception as e:
            print(f"[wikimedia] search error: {e}")
            return []

        results = []
        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if not info_list:
                continue
            info = info_list[0]
            mime = info.get("mime", "")
            if not mime.startswith("audio/"):
                continue

            ext_meta = info.get("extmetadata", {})
            license_short = ext_meta.get("LicenseShortName", {}).get("value", "")
            license_url = ext_meta.get("LicenseUrl", {}).get("value", "")
            artist = ext_meta.get("Artist", {}).get("value", "")
            description = ext_meta.get("ImageDescription", {}).get("value", "")
            duration = ext_meta.get("Duration", {}).get("value")

            result = SourceSearchResult(
                source_name="wikimedia",
                source_item_id=str(page["pageid"]),
                source_url=info.get("descriptionurl"),
                title=page.get("title", "").replace("File:", ""),
                description=description,
                creator=artist,
                license=license_short,
                attribution_required=True,
                commercial_use_allowed="CC0" in license_short or "Public" in license_short,
                derivative_use_allowed="ND" not in license_short,
                duration_seconds=float(duration) if duration else None,
                original_format=mime.split("/")[-1],
                download_url=info.get("url"),
                preview_url=info.get("url"),
                source_tags=[],
                raw_metadata=page,
            )
            results.append(result)

        print(f"[wikimedia] found {len(results)} results for '{request.query}'")
        return results
