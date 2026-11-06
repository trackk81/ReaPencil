"""Locate an optional, isolated CPU accelerator without replacing Maya NumPy."""
import os
import sys
from pathlib import Path


def enable():
    # Load host NumPy before adding the sidecar. The installer uses --no-deps.
    import numpy
    tag = 'py%d%d' % sys.version_info[:2]
    candidates = []
    explicit = os.environ.get('REVTOON_ACCELERATOR_PATH')
    if explicit:
        candidates.append(Path(explicit))
    package_root = Path(__file__).resolve().parents[2]
    candidates.append(package_root.parent / 'ReaToonAccelerator' / tag)
    if sys.platform == 'win32':
        candidates.append(Path.home() / 'Documents' / 'maya' / 'ReaToonAccelerator' / tag)
    elif sys.platform == 'darwin':
        candidates.append(Path.home() / 'Library/Preferences/Autodesk/maya/ReaToonAccelerator' / tag)
    else:
        candidates.append(Path.home() / 'maya/ReaToonAccelerator' / tag)
    for folder in candidates:
        if (folder / 'numba').is_dir() and (folder / 'llvmlite').is_dir():
            if (folder / 'numpy').exists():
                raise RuntimeError('Accelerator directory must not contain a replacement NumPy: ' + str(folder))
            if str(folder) not in sys.path:
                sys.path.insert(0, str(folder))
            return str(folder)
    return None
