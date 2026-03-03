import os, json
from .models import BaseClientModel
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, Tuple, Optional, List


class FabricLoader(BaseClientModel):
    def __init__(
        self,
        api_base_url: str = "https://meta.fabricmc.net",
        max_workers: int = 5,
    ) -> None:
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15"
        }
        super(FabricLoader, self).__init__(self._headers, api_base_url, max_workers)

    def _maven_name_to_path(self, name: str) -> str:
        parts = name.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid Maven coordinate format: {name}")
        group_id, artifact_id, version = parts
        group_path = group_id.replace(".", "/")
        return f"{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.jar"

    def _get_lib_hash(self, data: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        if data.get("md5") is not None:
            return data.get("md5"), "md5"
        elif data.get("sha1") is not None:
            return data.get("sha1"), "sha1"
        elif data.get("sha256") is not None:
            return data.get("sha256"), "sha256"
        elif data.get("sha512") is not None:
            return data.get("sha512"), "sha512"
        else:
            return None
        
    def _get_minecraft_dir_path() -> str:
        home_path = Path.home()
        if os.name == "nt":
            appdata = os.getenv("APPDATA")
            minecraft_dir_path = (
                os.path.join(appdata, ".minecraft")
                if appdata
                else os.path.join(str(home_path), ".minecraft")
            )
        elif os.name == "posix":
            if os.path.exists(
                os.path.join(
                    str(home_path), "Library", "Application Support", "minecraft"
                )
            ):
                minecraft_dir_path = os.path.join(
                    str(home_path), "Library", "Application Support", "minecraft"
                )
            else:
                minecraft_dir_path = os.path.join(str(home_path), ".minecraft")
        else:
            minecraft_dir_path = os.path.join(str(home_path), ".minecraft")
        return minecraft_dir_path

    def download_dependencies(
        self,
        minecraft_version: str,
        loader_version: str,
        dest_path: Optional[str] = None,
        block_size: int = 8192,
    ):
        if dest_path is None:
            home_path = Path.home()
            dest_path = os.path.join(home_path, "Downloads")
        response = self.get(
            f"/v2/versions/loader/{minecraft_version}/{loader_version}/profile/json"
        )
        libraries = response["libraries"]
        grouped_tasks: Dict[str, List[str]] = defaultdict(list)
        for lib in libraries:
            hash_pack = self._get_lib_hash(lib)
            maven_path = self._maven_name_to_path(lib.get("name"))
            url = lib.get("url") + maven_path
            folder_prefix = str(Path(maven_path).parent)
            file_name = Path(maven_path).name
            if hash_pack is not None:
                task = (file_name, url, hash_pack[0], hash_pack[1])
            else:
                task = (file_name, url)
            grouped_tasks[folder_prefix].append(task)

        results = []
        for prefix, tasks in grouped_tasks.items():
            path = os.path.join(dest_path, prefix)
            results.extend(self.batch_download(tasks, path, block_size))
        return results

    def install(
        self,
        minecraft_version: str,
        loader_version: str,
        minecraft_dir_path: Optional[str] = None,
        version_name: Optional[str] = None,
        download_block_size: int = 8192,
    ):
        if version_name is None:
            version_name = f"fabric-{minecraft_version}-{loader_version}"
        if minecraft_dir_path is None:
            minecraft_dir_path = self._get_minecraft_dir_path()
        libraries_path = os.path.join(minecraft_dir_path, "libraries")
        versions_path = os.path.join(minecraft_dir_path, "versions")
        profile_path = os.path.join(versions_path, version_name)
        profile_json_file = os.path.join(profile_path, f"{version_name}.json")
        deps_res = self.download_dependencies(
            minecraft_version, loader_version, libraries_path, download_block_size
        )
        if all(deps_res) is not True:
            return False
        os.makedirs(profile_path, exist_ok=True)
        response = self.get(
            f"/v2/versions/loader/{minecraft_version}/{loader_version}/profile/json"
        )
        response["id"] = version_name
        try:
            with open(profile_json_file, "w", encoding="utf-8") as file:
                json.dump(response, file, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"写入配置文件失败: {e}")
            return False
        return True
