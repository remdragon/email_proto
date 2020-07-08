# coverage run --branch tests.py && coverage report -m

import inspect
import logging
import os
import pathlib
import sys
import unittest

import importlib.util
def imp_load_source ( module_name, path ):
	#print ( f'loading {path!r}' )
	spec = importlib.util.spec_from_file_location ( module_name, path )
	module = importlib.util.module_from_spec ( spec )
	spec.loader.exec_module ( module )
	return module

logging.basicConfig (
	stream = sys.stdout,
	#level = logging.DEBUG,
	format = (
		#'%(asctime)s '
		'[%(name)s %(levelname)s] '
		'%(message)s'
	),
)

loader = unittest.TestLoader()
suite = unittest.TestSuite()

def look_for_tests ( path, prefix='' ):
	for p in pathlib.Path ( path ).glob ( '*_test.py' ):
		module_name = prefix + os.path.splitext ( p.name )[0]
		module = imp_load_source ( module_name, str ( p ) )
		for attr in dir ( module ):
			if attr[0] != '_':
				x = getattr ( module, attr )
				#print ( 'checking', attr )
				if inspect.isclass ( x ) and issubclass ( x, unittest.TestCase ):
					#print ( 'TestCase:', module_name, attr )
					cls = getattr ( module, attr )
					suite.addTest ( loader.loadTestsFromTestCase ( cls ) )
				#else:
				#	print ( 'garbage:', module_name, attr )

look_for_tests ( 'tests', 'tests.' )
look_for_tests ( '.' )

#logging.basicConfig ( stream=sys.stdout, level=logging.DEBUG, format='%(asctime)s [%(threadName)s %(levelname)s] %(message)s' )
unittest.TextTestRunner ( verbosity = 1, failfast = True ).run ( suite )
