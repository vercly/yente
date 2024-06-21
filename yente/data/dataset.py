from banal import as_bool
from normality import slugify
from datetime import datetime
from typing import Dict, Optional, Any, List
from nomenklatura.dataset import Dataset as NKDataset
from nomenklatura.dataset import DataCatalog
from nomenklatura.dataset.util import type_check
from nomenklatura.util import iso_to_version, datetime_iso
from followthemoney.types import registry
from followthemoney.namespace import Namespace
from followthemoney.util import sanitize_text

from yente.logs import get_logger
from yente.data.util import get_url_local_path
from yente.data.loader import load_json_url

log = get_logger(__name__)
BOOT_TIME = datetime_iso(datetime.utcnow())


class Dataset(NKDataset):
    def __init__(self, catalog: DataCatalog["Dataset"], data: Dict[str, Any]):
        self._available_versions_map: Dict[str, str] = {}
        name = data["name"]
        norm_name = slugify(name, sep="_")
        if name != norm_name:
            raise ValueError("Invalid dataset name %r (try: %r)" % (name, norm_name))
        super().__init__(catalog, data)
        self.load = as_bool(data.get("load"), not self.is_collection)
        self.entities_url = self._get_entities_url(data)
        if self.entities_url is not None:
            entities_path = get_url_local_path(self.entities_url)
            if entities_path is not None:
                self.entities_url = entities_path.as_uri()

        if self.version is None:
            ts = data.get("last_export", BOOT_TIME)
            if self.entities_url is not None:
                path = get_url_local_path(self.entities_url)
                if path is not None and path.exists():
                    mtime = path.stat().st_mtime
                    mdt = datetime.fromtimestamp(mtime)
                    ts = datetime_iso(mdt)
            self.version = iso_to_version(ts) or "static"

        self.delta_url = data.get("delta_url", None)

        namespace = as_bool(data.get("namespace"), False)
        self.ns = Namespace(self.name) if namespace else None
        self.index_version: Optional[str] = None

    def _get_entities_url(self, data: Dict[str, Any]) -> Optional[str]:
        entities_url = sanitize_text(data.get("entities_url", data.get("path")))
        if entities_url is not None:
            return entities_url
        resource_name = type_check(registry.string, data.get("resource_name"))
        resource_type = type_check(registry.string, data.get("resource_type"))
        for resource in self.resources:
            if resource.url is None:
                continue
            if resource_name is not None and resource.name == resource_name:
                return resource.url
            if resource_type is not None and resource.mime_type == resource_type:
                return resource.url
        return None

    def delta_path(self, version: str) -> str:
        """
        Get the URL for the delta file for a specific version of this dataset.
        """
        if version not in self._available_versions_map:
            raise ValueError(f"Version {version} not available for {self.name}")
        return self._available_versions_map[version]

    async def _load_versions_map(self, refresh: bool = False) -> None:
        """
        Set a map of versions to their URLs for this dataset.
        """
        if self._available_versions_map is {} or refresh is True:
            if self.delta_url is None:
                raise Exception(f"No delta_index path specified for {self.name}")
            resp = await load_json_url(self.delta_url)
            if "versions" not in resp:
                raise ValueError(f"Invalid versions file found at {self.delta_url}")
            self._available_versions_map = resp.get("versions")
            if (
                self.version is not None
                and self.delta_url is not None
                and self.version not in self._available_versions_map
            ):
                self._available_versions_map[self.version] = self.delta_url

    async def available_versions(self, refresh: bool = False) -> List[str]:
        await self._load_versions_map(refresh=refresh)
        return list(self._available_versions_map.keys())

    async def newest_version(self) -> str | None:
        """
        Get the newest version available for this dataset. If delta versioning
        is not implemented for this dataset, return None.
        """
        try:
            available = await self.available_versions(refresh=True)
            return sorted(available)[-1]
        except Exception as e:
            log.warning(f"Failed to get newest version for {self.name}: {e}")
            return None

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["load"] = self.load
        if self.entities_url:
            data["entities_url"] = self.entities_url
        data["index_version"] = self.index_version
        data["index_current"] = self.index_version == self.version
        if self.ns is not None:
            data["namespace"] = True
        if "children" not in data:
            data["children"] = [c.name for c in self.children]
        return data
