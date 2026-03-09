from abc import ABC, abstractmethod
from ..models import SourceSearchRequest, SourceSearchResult


class BaseSourceConnector(ABC):
    source_name: str = ""

    @abstractmethod
    def search(self, request: SourceSearchRequest) -> list[SourceSearchResult]:
        """Search the source and return a list of candidates."""
        ...
