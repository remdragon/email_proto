# python imports:
import logging
from pathlib import Path
import sys
import unittest

if __name__ == '__main__': # pragma: no cover
	sys.path.append ( str ( Path ( __file__ ).parent.parent.absolute() ) )

# email_proto imports:
import event_handling

logger = logging.getLogger ( __name__ )

class Tests ( unittest.TestCase ):
	def test_coverage ( self ) -> None:
		with self.assertRaises ( event_handling.Closed ):
			try:
				with event_handling.close_if_oserror():
					raise OSError ( 'foo' )
			except event_handling.Closed as e:
				self.assertEqual ( repr ( e ), '''Closed("OSError('foo')")''' )
				raise

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()