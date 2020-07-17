#from __future__ import annotations

from typing import Any, List

__path__: List[str] = []

import os
from pathlib import Path
import sys
__all__ = []

import importlib.util
def imp_load_source ( module_name: str, path: str ) -> Any:
	#print ( f'loading {path!r}' )
	spec = importlib.util.spec_from_file_location ( module_name, path )
	module = importlib.util.module_from_spec ( spec )
	spec.loader.exec_module ( module ) # type: ignore
	return module

g = globals()
for p in Path ( os.path.split ( __file__ )[0] ).glob ( '*.py' ):
	if not p.name.lower().endswith ( '_test.py' ):
		#print ( f'skipping: {p.name!r}' )
		continue
	#print ( f'loading: {p.name!r}' )
	module_name = os.path.splitext ( p.name )[0]
	#print ( f'importing {module_name!r}' )
	module = imp_load_source ( module_name, str ( p ) )
	#print ( f'adding module {module_name!r} to __dict__' )
	g[module_name] = module
	__all__.append ( module_name )
#for key, val in dict(globals()).items():
#	if key not in ( '__builtins__', 'g' ):
#		print ( '********', key, val )
