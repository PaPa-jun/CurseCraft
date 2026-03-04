import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

from .models import Installer


class ForgeInstaller(Installer):
    def __init__(
        self,
        api_base_url: str = "https://meta.fabricmc.net",
        max_workers: int = 5,
    ) -> None:
        super(FabricInstaller, self).__init__(api_base_url, max_workers)


class FabricInstaller(Installer):
    def __init__(
        self,
        api_base_url: str = "https://meta.fabricmc.net",
        max_workers: int = 5,
    ) -> None:
        super(FabricInstaller, self).__init__(api_base_url, max_workers)

    def _get_lib_hash(self, data: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        if data.get("sha1") is not None:
            return data.get("sha1"), "sha1"
        elif data.get("md5") is not None:
            return data.get("md5"), "md5"
        elif data.get("sha256") is not None:
            return data.get("sha256"), "sha256"
        elif data.get("sha512") is not None:
            return data.get("sha512"), "sha512"
        else:
            return None

    def install(
        self,
        minecraft_version: str,
        loader_version: str,
        minecraft_dir_path: Optional[str] = None,
        download_block_size: int = 8192,
        install_side: str = "client",
    ):
        self._install_initialize(
            install_side,
            minecraft_version,
            "fabric",
            loader_version,
            minecraft_dir_path,
        )

        version_profile = self.get(
            f"/v2/versions/loader/{minecraft_version}/{loader_version}/profile/json"
        ).json()
        libraries = version_profile["libraries"]

        grouped_tasks: Dict[str, List[str]] = {}
        for lib in libraries:
            hash_pack = self._get_lib_hash(lib)
            maven_path = self._resolve_maven_coord(lib.get("name"))
            url = lib.get("url") + maven_path
            folder_prefix = str(Path(maven_path).parent)
            file_name = Path(maven_path).name
            if hash_pack is not None:
                task = (file_name, url, hash_pack[0], hash_pack[1])
            else:
                task = (file_name, url)
            grouped_tasks.setdefault(folder_prefix, []).append(task)

        deps_res = []
        for prefix, tasks in grouped_tasks.items():
            path = Path(self._static_data["ROOT"], "libraries", prefix)
            deps_res.extend(self.batch_download(tasks, path, download_block_size))
        if all(deps_res) is not True:
            return False

        return self._write_version_file(version_profile)


class NeoForgeInstaller(Installer):
    def __init__(
        self, maven_base_url: str = "https://maven.neoforged.net", max_workers=5
    ) -> None:
        super(NeoForgeInstaller, self).__init__(maven_base_url, max_workers)

    def install(
        self,
        minecraft_version,
        loader_version,
        minecraft_dir_path=None,
        download_block_size=8192,
        install_side="client",
    ):
        self._install_initialize(
            install_side,
            minecraft_version,
            "neoforge",
            loader_version,
            minecraft_dir_path,
        )
        self.check_and_download_minecraft_jar(download_block_size)
        self._get_installer(
            f"{self._base_url}/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar"
        )

        install_profile = json.loads(self.installer["install_profile.json"])
        version_profile = json.loads(self.installer["version.json"])

        grouped_tasks: Dict[str, List[str]] = {}
        for lib in install_profile["libraries"]:
            sha1_value = lib["downloads"]["artifact"]["sha1"]
            folder_prefix = str(Path(lib["downloads"]["artifact"]["path"]).parent)
            file_name = str(Path(lib["downloads"]["artifact"]["path"]).name)
            task = (file_name, lib["downloads"]["artifact"]["url"], sha1_value, "sha1")
            grouped_tasks.setdefault(folder_prefix, []).append(task)

        deps_res = []
        for prefix, tasks in grouped_tasks.items():
            path = Path(self._static_data["ROOT"], "libraries", prefix)
            deps_res.extend(self.batch_download(tasks, path, download_block_size))
        if not all(deps_res):
            return False

        processors = self._parse_install_profile(install_profile)
        pro_res = self._run_processors(processors)
        if not all(pro_res):
            return False

        return self._write_version_file(version_profile)
