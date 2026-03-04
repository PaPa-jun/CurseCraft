import io, os, re, requests, hashlib, tempfile, subprocess, json, zipfile
from tqdm import tqdm
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils import get_main_class


class BaseClientModel:
    def __init__(self, headers: Dict[str, Any], base_url: str, max_workers: int = 5):
        self._base_url = base_url
        self._headers = headers
        self._max_workers = max_workers

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        try:
            response = requests.request(
                method=method,
                url=endpoint,
                headers=self._headers,
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            print(f"HTTP 请求错误: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"请求发生错误: {e}")
            return None

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._base_url + endpoint
        return self._request("GET", url, params=params)

    def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> Any:
        url = self._base_url + endpoint
        return self._request("POST", url, json=json)

    def _calculate_file_hash(self, file_path: str, hash_algo: str):
        try:
            hash_func = hashlib.new(hash_algo)
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except Exception as e:
            print(f"计算文件哈希值失败 {file_path}: {e}")
            return None

    def _hash_verify(self, file_path: str, expected_hash: str, hash_algo: str):
        expected_hash = expected_hash.lower().strip()
        file_hash = self._calculate_file_hash(file_path, hash_algo)
        if file_hash == expected_hash:
            return True
        print(f"文件校验失败：{file_path}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return False

    def single_download(
        self,
        url: str,
        file_name: str,
        dest_path: Optional[str] = None,
        block_size: int = 8192,
        expected_hash: Optional[str] = None,
        hash_algo: str = "sha256",
    ) -> bool:
        if dest_path is None:
            home_path = Path.home()
            dest_path = Path(home_path, "Downloads")
        os.makedirs(dest_path, exist_ok=True)
        full_path = Path(dest_path, file_name)

        if os.path.exists(full_path):
            if expected_hash:
                return self._hash_verify(full_path, expected_hash, hash_algo)
            else:
                return True

        try:
            with requests.get(url=url, stream=True, headers=self._headers) as request:
                request.raise_for_status()

                total_size = int(request.headers.get("content-length", 0))
                with open(full_path, "wb") as f:
                    with tqdm(
                        total=total_size, unit="B", unit_scale=True, desc=file_name
                    ) as pbar:
                        for chunk in request.iter_content(chunk_size=block_size):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
            if expected_hash is not None:
                return self._hash_verify(full_path, expected_hash, hash_algo)
            return True
        except Exception as e:
            print(f"下载失败 {file_name}: {e}")
            if os.path.exists(full_path):
                os.remove(full_path)
            return False

    def batch_download(
        self,
        files: List[Union[Tuple[str, str], Tuple[str, str, str, str]]],
        dest_path: Optional[str] = None,
        block_size: int = 8192,
    ) -> List[bool]:
        results = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future2file = {}
            for item in files:
                args = (
                    (item[1], item[0], dest_path, block_size)
                    if len(item) == 2
                    else (
                        (item[1], item[0], dest_path, block_size, item[2], item[3])
                        if len(item) == 4
                        else None
                    )
                )
                future2file[executor.submit(self.single_download, *args)] = item[0]

            for future in as_completed(future2file):
                file_name = future2file[future]
                try:
                    success = future.result()
                    results[file_name] = success
                except Exception as exc:
                    print(f"{file_name} 生成异常: {exc}")
                    results[file_name] = False

        return [results[item[0]] for item in files if item[0] in results]


class Installer(BaseClientModel):
    def __init__(
        self,
        api_base_url: str,
        max_workers: int = 5,
    ):
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15"
        }
        super(Installer, self).__init__(
            self._headers, api_base_url, max_workers
        )

        self.installer = {}
        self._static_data = {}
        self._pattern = re.compile(r"(\{[A-Z_]+\})|(\[[^\]]+\])")

        self._minecraft_manifest = requests.request(
            "GET", "https://launchermeta.mojang.com/mc/game/version_manifest.json"
        ).json()

    def _get_minecraft_dir_path(self) -> str:
        home_path = Path.home()
        if os.name == "nt":
            appdata = os.getenv("APPDATA")
            minecraft_dir_path = (
                Path(appdata, ".minecraft")
                if appdata
                else Path(str(home_path), ".minecraft")
            )
        elif os.name == "posix":
            if os.path.exists(
                Path(
                    str(home_path), "Library", "Application Support", "minecraft"
                )
            ):
                minecraft_dir_path = Path(
                    str(home_path), "Library", "Application Support", "minecraft"
                )
            else:
                minecraft_dir_path = Path(str(home_path), ".minecraft")
        else:
            minecraft_dir_path = Path(str(home_path), ".minecraft")
        return minecraft_dir_path

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

    def _run_processors(
        self, processors: Dict[str, Any], java_executable: str = "java"
    ) -> List[bool]:
        def _single_process(
            processor: Dict[str, Any],
            java_executable: str = "java",
        ) -> bool:
            main_class = processor.get("main_class")
            class_paths = processor.get("class_paths")

            jar_path = processor["jar"]
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

    def check_and_download_minecraft_jar(self, block_size: int = 8192) -> bool:
        if os.path.exists(self._static_data["MINECRAFT_JAR"]) is False:
            target_version = None
            for version_info in self._minecraft_manifest["versions"]:
                if version_info["id"] == self._static_data["MINECRAFT_VERSION"]:
                    target_version = version_info
                    break
            version_data = requests.request("GET", target_version["url"]).json()
            return self.single_download(
                version_data["downloads"]["client"]["url"],
                f"{self._static_data["MINECRAFT_VERSION"]}.jar",
                Path(
                    self._static_data["ROOT"],
                    "versions",
                    self._static_data["MINECRAFT_VERSION"],
                ),
                block_size,
                version_data["downloads"]["client"]["sha1"],
                "sha1",
            )
        return True

    def install(
        self,
        minecraft_version: str,
        loader_version: str,
        minecraft_dir_path: Optional[str] = None,
        download_block_size: int = 8192,
        install_side: str = "client",
    ):
        raise NotImplementedError("Not implemented yet.")
