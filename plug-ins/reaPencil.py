"""ReaPencil: canonical Maya plug-in entry point."""
import os,sys
_source=globals().get('__file__',(lambda:None).__code__.co_filename)
_scripts=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(_source))),'scripts')
if _scripts not in sys.path:sys.path.insert(0,_scripts)
from reatoon.plugin import maya_useNewAPI,initializePlugin,uninitializePlugin
