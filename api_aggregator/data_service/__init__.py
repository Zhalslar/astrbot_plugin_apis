from ..entry import APIEntry
from ..log import logger
from ..model import DataResource
from .local_data import LocalDataService
from .remote_data import RemoteDataService
from .request_result import RequestResult as RequestResult


class DataService:
    """High-level fetch service combining remote fetch and local fallback."""

    def __init__(
        self,
        remote: RemoteDataService,
        local: LocalDataService,
    ) -> None:
        self.remote = remote
        self.local = local

    async def fetch(
        self, entry: APIEntry, *, use_local: bool = True
    ) -> DataResource | None:
        """Fetch data by entry, save to local storage, then return normalized resource.

        Behavior:
        - Try remote first.
        - On remote failure and `use_local=True`, fallback to random local item.
        - Return `None` when both paths fail.

        Returns:
            A `DataResource` with either `saved_text` or `saved_path`, or `None`.
        """

        # ================== Remote call ==================
        try:
            result = await self.remote.get_data(entry)

            if not result.ok:
                raise RuntimeError(result.error or "request not ok")

            # Build DataResource
            data = DataResource(
                data_type=entry.data_type,
                name=entry.name,
                text=result.raw_text,
                binary=result.raw_content,
            )

            # Persist locally (fills saved_* internally)
            saved_data = await self.local.save_data(data)

            return saved_data

        except Exception as e:
            logger.warning(f"API call failed [{entry.name}] : {e}")

        # ================== Local fallback ==================
        if use_local:
            try:
                local_data = await self.local.get_random_data(
                    entry.data_type,
                    entry.name,
                )
                return local_data

            except Exception as e:
                logger.error(f"Local fallback failed [{entry.name}] : {e}")

        # ================== Final failure ==================
        return None
