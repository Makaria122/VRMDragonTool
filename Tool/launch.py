"""Launch the bundled GUI with an installed Python 3.10+ (with Tkinter)."""
import sys
from pathlib import Path
# Optional dependencies installed into Tool, not the system Python environment.
sys.path.insert(0,str(Path(__file__).resolve().parent/'runtime'/'python-packages'))
from um.dragon_gui import main

if __name__ == "__main__":
    main()
