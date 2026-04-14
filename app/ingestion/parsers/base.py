from abc import ABC, abstractmethod

from app.models.normalized import NormalizedBatch


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, data: bytes | dict, **kwargs) -> NormalizedBatch:
        """Parse raw data into a NormalizedBatch."""
