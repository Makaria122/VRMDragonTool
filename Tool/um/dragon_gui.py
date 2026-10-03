"""Entry point of the desktop GUI; the implementation lives in the um.gui package."""
from um.gui import main
from um.gui.app import DragonApp as DragonWindow

__all__ = ['main', 'DragonWindow']
