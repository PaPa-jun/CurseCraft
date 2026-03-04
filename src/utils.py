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


def resolve_maven_coord(coord: str) -> str:
    extension = "jar"
    if "@" in coord:
        coord_body, extension = coord.rsplit("@", 1)
        if "@" in coord_body:
            raise ValueError(f"Invalid maven coord: {coord}")
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
        classifier, extension = classifier.split("@", 1)
    group_path = group.replace(".", "/")
    filename = f"{artifact}-{version}"

    if classifier:
        filename += f"-{classifier}"
    filename += f".{extension}"
    return f"{group_path}/{artifact}/{version}/{filename}"
