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

# res = cli.get_minecraft_loaders("1.20.2", include_all=True)
# for loader in res:
#     print(loader.name, loader.game_version)

# loader = FabricInstaller()
# loader.install("1.20.2", "0.18.4", ".minecraft/")

loader = NeoForgeInstaller()
res = loader.install("1.21.1", "21.1.129", ".minecraft")
print(res)
# /mnt/c/Users/Pengy/AppData/Roaming/.minecraft/

# loader = NeoForgeInstaller()
# loader._get_installer(
#     "https://maven.neoforged.net/releases/net/neoforged/neoforge/21.8.52/neoforge-21.8.52-installer.jar"
# )
# loader._install_initialize("client", "1.21.8", "neoforge", "21.8.52", ".minecraft")
# processors = loader._parse_install_profile(
#     json.loads(loader.installer["install_profile.json"])
# )
# for processor in processors:
#     print(json.dumps(processor, indent=2))
