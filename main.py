from configparser import ConfigParser
from cursecraft import CurseCraft, NeoForgeInstaller


configs = ConfigParser()
configs.read("cfg.ini")

craft = CurseCraft(configs)

craft.install_modpack(490660, "G:\\Minecraft")