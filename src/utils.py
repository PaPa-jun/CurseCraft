import zipfile
import os
from typing import Optional


def unzip_file(
    zip_path: str, extract_to: str = ".", password: Optional[str] = None
) -> bool:
    os.makedirs(extract_to, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        pwd_bytes = password.encode("utf-8") if password else None
        zip_ref.extractall(path=extract_to, pwd=pwd_bytes)

    return True


def get_main_class(jar_path: str):
    manifest_content = None
    with zipfile.ZipFile(jar_path, "r") as zip_ref:
        for file_name in zip_ref.namelist():
            if file_name == "META-INF/MANIFEST.MF":
                manifest_content = zip_ref.read(file_name).decode("utf-8")
                break
    for line in manifest_content.splitlines():
        if line.startswith("Main-Class:"):
            return line.split(":", 1)[1].strip()
    return None
