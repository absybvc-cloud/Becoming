import requests
from ..models import SourceSearchRequest, SourceSearchResult
from .base import BaseSourceConnector

IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
IA_METADATA_URL = "https://archive.org/metadata"
IA_DOWNLOAD_BASE = "https://archive.org/download"


class InternetArchiveConnector(BaseSourceConnector):
    source_name = "internet_archive"

    def search(self, request: SourceSearchRequest) -> list[SourceSearchResult]:
        params = {
            "q": f"({request.query}) AND mediatype:audio",
            "fl[]": "identifier,title,description,creator,licenseurl,subject",
            "rows": min(request.limit, 100),
            "page": request.page,
            "output": "json",
        }
        min_dur = request.filters.get("min_duration")
        max_dur = request.filters.get("max_duration")
        if min_dur:
            params["q"] += f" AND audio_length:[{min_dur} TO *]"
        if max_dur:
            params["q"] += f" AND audio_length:[* TO {max_dur}]"

        try:
            resp = requests.get(IA_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
        except Exception as e:
            print(f"[internet_archive] search error: {e}")
            return []

        results = []
        for doc in docs:
            identifier = doc.get("identifier")
            if not identifier:
                continue
            file_info = self._get_first_audio_file(identifier)
            if not file_info:
                continue
            license_url = doc.get("licenseurl", "")
            result = SourceSearchResult(
                source_name="internet_archive",
                source_item_id=identifier,
                source_url=f"https://archive.org/details/{identifier}",
                title=doc.get("title"),
                description=doc.get("description"),
                creator=doc.get("creator"),
                license=license_url,
                attribution_required=True,
                commercial_use_allowed="publicdomain" in license_url or "cc0" in license_url.lower(),
                derivative_use_allowed="nd" not in license_url.lower(),
                duration_seconds=file_info.get("length"),
                original_format=file_info.get("format"),
                download_url=f"{IA_DOWNLOAD_BASE}/{identifier}/{file_info['name']}",
                source_tags=doc.get("subject", []) if isinstance(doc.get("subject"), list) else [],
                raw_metadata=doc,
            )
            results.append(result)

        print(f"[internet_archive] found {len(results)} results for '{request.query}'")
        return results

    def _get_first_audio_file(self, identifier: str) -> dict | None:
        try:
            resp = requests.get(f"{IA_METADATA_URL}/{identifier}", timeout=10)
            resp.raise_for_status()
            files = resp.json().get("files", [])
        except Exception:
            return None

        audio_formats = {"mp3", "flac", "wav", "ogg", "aiff"}
        for f in files:
            fmt = f.get("format", "").lower()
            if any(a in fmt for a in audio_formats):
                return f
        return None
