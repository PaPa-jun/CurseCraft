import json
from configparser import ConfigParser
from src.client import CurseforgeClient
from src.loaders import FabricInstaller, NeoForgeInstaller


configs = ConfigParser()
configs.read("cfg.ini")

cli = CurseforgeClient(
    configs.get("DEFAULT", "API_KEY"),
    configs.get("DEFAULT", "BASE_URL"),
    configs.get("DEFAULT", "GAME_ID"),
)

loader = NeoForgeInstaller()

# cli.download_modpacks(925200, "/mnt/g/Minecraft/ATM10", "complete")
loader.install("1.21.1", "21.1.219", ".minecraft/")
