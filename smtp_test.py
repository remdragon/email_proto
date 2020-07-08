# system imports:
import logging
import unittest
from typing import Iterator

# email_proto imports:
import smtp

logger = logging.getLogger ( __name__ )

class Tests ( unittest.TestCase ):
	def test_misc ( self ):
		log = logger.getChild ( 'Tests.test_misc' )
		
		self.assertEqual ( smtp.b64_encode ( 'Hello' ), 'SGVsbG8=' )
		self.assertEqual ( smtp.b64_decode ( 'SGVsbG8=' ), 'Hello' )
		
		evt = smtp.SendDataEvent ( b'foo' )
		self.assertEqual ( repr ( evt ), 'smtp.SendDataEvent()' )
		
		# test edge cases in Connection buffer management
		class TestConnection ( smtp.Connection ):
			def _receive_line ( self, line: bytes ) -> Iterator[smtp.Event]:
				if line:
					yield smtp.SendDataEvent ( line )
		
		conn = TestConnection()
		evts = list ( conn.receive ( b'foo\r' ) )
		self.assertEqual ( evts, [] )
		evts = [ evt.data for evt in conn.receive ( b'\nba' ) ]
		self.assertEqual ( evts, [
			b'foo\r\n',
		] )
		evts = [ evt.data for evt in conn.receive ( b'ar\r\nbaz' ) ]
		self.assertEqual ( evts, [
			b'baar\r\n',
		] )
		evts = [ evt.data for evt in conn.receive ( b'' ) ]
		self.assertEqual ( evts, [
			b'baz',
		] )
		with self.assertRaises ( smtp.Closed ):
			evts = list ( conn.receive ( b'' ) )
		
		conn = TestConnection()
		with self.assertRaises ( smtp.ProtocolError ):
			evts = list ( conn.receive ( b'X' * smtp._MAXLINE ) )
		
		evt2 = smtp.AuthEvent ( 'foo', 'bar' )
		evt2.reject ( 404, 'Not Found' )

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
