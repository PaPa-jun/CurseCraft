import requests, os, hashlib
from tqdm import tqdm
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed


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
        url = self._base_url + endpoint
        try:
            response = requests.request(
                method=method, url=url, headers=self._headers, params=params, json=json
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP 请求错误: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"请求发生错误: {e}")
            return None

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("POST", endpoint, json=json)

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
            dest_path = os.path.join(home_path, "Downloads")
        os.makedirs(dest_path, exist_ok=True)
        full_path = os.path.join(dest_path, file_name)

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
