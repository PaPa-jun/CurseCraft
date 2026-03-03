from configparser import ConfigParser
from src.client import CurseforgeClient
from src.loaders import FabricLoader


configs = ConfigParser()
configs.read("cfg.ini")

cli = CurseforgeClient(
    configs.get("DEFAULT", "API_KEY"),
    configs.get("DEFAULT", "BASE_URL"),
    configs.get("DEFAULT", "GAME_ID"),
)

# res = cli.get_minecraft_loaders("1.21.8", include_all=True)
# for loader in res:
#     print(loader.name, loader.game_version)

fabric_loader = FabricLoader()
fabric_loader.install("1.21.8", "0.18.4", "/mnt/c/Users/Pengy/AppData/Roaming/.minecraft/")

# mod = cli.get_mod(925200)
# cli.download_modpacks(925200, mode="complete")
