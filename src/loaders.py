import os, json, zipfile, io, requests, subprocess, re, tempfile
from .models import BaseClientModel
from .utils import get_main_class
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List


class ModLoaderInstaller(BaseClientModel):
    def __init__(
        self,
        api_base_url: str,
        max_workers: int = 5,
    ):
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15"
        }
        super(ModLoaderInstaller, self).__init__(
            self._headers, api_base_url, max_workers
        )

        self.installer = {}
        self._static_data = {}
        self._pattern = re.compile(r"(\{[A-Z_]+\})|(\[[^\]]+\])")

        self._minecraft_manifest = requests.request(
            "GET", "https://launchermeta.mojang.com/mc/game/version_manifest.json"
        ).json()

    def _install_initialize(
        self,
        install_side: str,
        minecraft_version: str,
        loader_name: str,
        loader_version: str,
        install_path: Optional[str] = None,
    ) -> None:
        self._static_data["SIDE"] = install_side
        self._static_data["ROOT"] = (
            install_path if install_path else self._get_minecraft_dir_path()
        )
        self._static_data["MINECRAFT_VERSION"] = minecraft_version
        self._static_data["LOADER_NAME"] = loader_name
        self._static_data["LOADER_VERSION"] = loader_version
        self._static_data["MINECRAFT_JAR"] = str(
            Path(
                self._static_data["ROOT"],
                "versions",
                minecraft_version,
                f"{minecraft_version}.jar",
            )
        )

        if os.path.exists(self._static_data["MINECRAFT_JAR"]) is False:
            target_version = None
            for version_info in self._minecraft_manifest["versions"]:
                if version_info["id"] == minecraft_version:
                    target_version = version_info
                    break
            version_data = requests.request("GET", target_version["url"]).json()
            self.single_download(
                version_data["downloads"]["client"]["url"],
                f"{minecraft_version}.jar",
                Path(self._static_data["ROOT"], "versions", minecraft_version),
                8192,
                version_data["downloads"]["client"]["sha1"],
                "sha1",
            )

    def _run_processors(
        self, processors: Dict[str, Any], java_executable: str = "java"
    ) -> List[bool]:
        def _single_process(
            processor: Dict[str, Any],
            java_executable: str = "java",
        ) -> bool:
            main_class = processor.get("main_class")
            class_paths = processor.get("class_paths")

            jar_path = processor[
                "jar"
            ]
            args = processor["args"]

            temp_files = []

            for i, arg in enumerate(args):
                if arg.startswith("/data/"):
                    file_key = arg[1:]
                    file_bytes = self.installer[file_key]

                    temp_file = tempfile.NamedTemporaryFile(
                        delete=False, suffix=os.path.basename(file_key)
                    )
                    temp_file.write(file_bytes)
                    temp_file.close()

                    temp_files.append(temp_file.name)
                    args[i] = temp_file.name

            classpath_str = os.pathsep.join(class_paths)
            command = [java_executable, "-cp", classpath_str, main_class] + args

            try:
                result = subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                print(result.stdout)
                return True
            except subprocess.CalledProcessError as e:
                print(f"Fail to patch, Return Code: {e.returncode}")
                print(f"Stdout: {e.stdout}")
                print(f"Stderr: {e.stderr}")
                return False
            except Exception as e:
                print(f"Fail to patch: {e}")
                return False
            finally:
                for temp_file_path in temp_files:
                    try:
                        os.remove(temp_file_path)
                    except OSError:
                        pass

        results = []
        for processor in processors:
            results.append(_single_process(processor, java_executable))
        return results

    def _write_version_file(self, data: Dict[str, Any]) -> bool:
        file_path = Path(
            self._static_data["ROOT"],
            "versions",
            f"{self._static_data["LOADER_NAME"]}-{self._static_data["LOADER_VERSION"]}",
        )
        file_name = str(
            Path(
                file_path,
                f"{self._static_data["LOADER_NAME"]}-{self._static_data["LOADER_VERSION"]}.json",
            )
        )
        data["id"] = (
            f"{self._static_data["LOADER_NAME"]}-{self._static_data["LOADER_VERSION"]}.json"
        )
        try:
            os.makedirs(file_path, exist_ok=True)
            with open(file_name, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"写入配置文件失败: {e}")
            return False
        return True

    def _replace_arg_variable(self, arg: str) -> str:
        def replace_match(match):
            var_match = match.group(1)
            maven_match = match.group(2)

            if var_match:
                key = var_match[1:-1]
                if key in self._static_data:
                    return self._static_data[key]
                else:
                    return var_match

            elif maven_match:
                coord = maven_match[1:-1]
                try:
                    resolved_path = self._resolve_maven_coord(coord)
                    resolved_path = str(
                        Path(self._static_data["ROOT"], "libraries", resolved_path)
                    )
                    return resolved_path
                except Exception as e:
                    print(f"Error resolving maven coord {coord}: {e}")
                    return maven_match

            return match.group(0)

        return self._pattern.sub(replace_match, arg)

    def _parse_install_profile(self, install_profile: Dict[str, Any]):
        for key, values in install_profile["data"].items():
            self._static_data[key] = self._replace_arg_variable(values["client"])

        processors = []
        for processor in install_profile["processors"]:
            if self._static_data["SIDE"] not in processor.get("sides", ["client"]):
                continue
            jar_path = str(
                Path(
                    self._static_data["ROOT"],
                    "libraries",
                    self._resolve_maven_coord(processor["jar"]),
                )
            )
            main_class = get_main_class(jar_path)
            class_paths = []
            for class_coord in processor.get("classpath"):
                class_path = str(
                    Path(
                        self._static_data["ROOT"],
                        "libraries",
                        self._resolve_maven_coord(class_coord),
                    )
                )
                class_paths.append(class_path)
            args = []
            for arg in processor["args"]:
                arg = self._replace_arg_variable(arg)
                args.append(arg)
            processors.append(
                {
                    "jar": jar_path,
                    "main_class": main_class,
                    "class_paths": class_paths,
                    "args": args,
                }
            )
        return processors

    def _get_minecraft_dir_path(self) -> str:
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

    def _resolve_maven_coord(self, coord: str) -> str:
        extension = "jar"
        
        if "@" in coord:
            coord_body, extension = coord.rsplit("@", 1)
            parts = coord_body.split(":")
        else:
            parts = coord.split(":")

        if len(parts) < 3:
            raise ValueError(f"Invalid maven coord: {coord}")

        group = parts[0]
        artifact = parts[1]
        version = parts[2]
        classifier = parts[3] if len(parts) > 3 else None
        
        if classifier and "@" in classifier:
            classifier, ext_override = classifier.split("@", 1)
            if ext_override:
                extension = ext_override
        group_path = group.replace(".", "/")
        filename = f"{artifact}-{version}"
        
        if classifier:
            filename += f"-{classifier}"
        filename += f".{extension}"
        return f"{group_path}/{artifact}/{version}/{filename}"

    def _get_installer(self, url: str) -> None:
        response = self._request("GET", url)
        try:
            with zipfile.ZipFile(io.BytesIO(response.content), "r") as zip_ref:
                for file_name in zip_ref.namelist():
                    if file_name.endswith("/"):
                        continue
                    self.installer[file_name] = zip_ref.read(file_name)
        except Exception as e:
            raise RuntimeError(f"解析 installer 失败: {e}")

    def install(
        self,
        minecraft_version: str,
        loader_version: str,
        minecraft_dir_path: Optional[str] = None,
        download_block_size: int = 8192,
        install_side: str = "client",
    ):
        raise NotImplementedError("Not implemented yet.")


class FabricInstaller(ModLoaderInstaller):
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


class NeoForgeInstaller(ModLoaderInstaller):
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
