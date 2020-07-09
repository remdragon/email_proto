# system imports:
import contextlib
import logging
import unittest
from typing import Iterator

# email_proto imports:
import smtp

logger = logging.getLogger ( __name__ )

@contextlib.contextmanager
def quiet_logging ( quiet: bool = True ) -> Iterator[None]:
	try:
		if quiet:
			logging.disable ( logging.CRITICAL )
		yield None
	finally:
		if quiet:
			logging.disable ( logging.NOTSET )

class Tests ( unittest.TestCase ):
	def test_misc ( self ):
		log = logger.getChild ( 'Tests.test_misc' )
		
		self.assertEqual ( smtp.b64_encode ( 'Hello' ), 'SGVsbG8=' )
		self.assertEqual ( smtp.b64_decode ( 'SGVsbG8=' ), 'Hello' )
		
		evt = smtp.SendDataEvent ( b'foo' )
		self.assertEqual ( repr ( evt ), "smtp.SendDataEvent(data=b'foo')" )
		
		# test edge cases in Connection buffer management
		if True:
			class BrokenConnection ( smtp.Connection ):
				def _receive_line ( self, line: bytes ) -> Iterator[smtp.Event]:
					yield from super()._receive_line ( line )
			broken = BrokenConnection()
			with self.assertRaises ( NotImplementedError ):
				list ( broken._receive_line ( b'fubar' ) )
		
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
		
		cli = smtp.Client ( smtp.GreetingRequest() )
		with self.assertRaises ( smtp.Closed ):
			try:
				list ( cli._receive_line ( b'XXX_BAD_MEDICINE' ) )
			except smtp.Closed as e:
				self.assertEqual ( repr ( e ),
					'''Closed('malformed response from server line=b\\'XXX_BAD_MEDICINE\\': e=ValueError("invalid literal for int() with base 10: b\\'XXX\\'")')'''
				)
				raise
		
		evt2 = smtp.AuthEvent ( 'foo', 'bar' )
		evt2.reject ( 404, 'Not Found' )
		
		with quiet_logging():
			evt2.reject (
				250, # <-- not valid for a rejection
				'Not Found\n', # <-- not valid ( contains a \n )
			)
			# make sure ev2 has it's defaults since we fed it invalid data
			self.assertEqual ( evt2._code, smtp.AuthEvent.error_code )
			self.assertEqual ( evt2._message, smtp.AuthEvent.error_message )
		
		srv = smtp.Server ( 'localhost' )
		ss = smtp.ServerState()
		x = list ( ss.receive_line ( srv, b'FREE BEER\r\n' ) )
		self.assertEqual ( repr ( x ), "[smtp.SendDataEvent(data=b'500 command not recognized or not available: FREE\\r\\n')]" )
		
		evt = smtp.Event()
		self.assertEqual ( repr ( evt ), 'smtp.Event()' )
		
		evt = smtp.CompleteEvent ( 'from@test.com', [ 'to@test.com' ], b'' )
		self.assertEqual ( repr ( evt ), 'smtp.CompleteEvent(_acceptance=None, _code=None, _message=None)' )
		
		evt = smtp.ErrorEvent ( 500, 'Brittney Spears concert sold out' )
		self.assertEqual ( repr ( evt ), "smtp.ErrorEvent(code=500, message='Brittney Spears concert sold out')" )
		
		evt = smtp.AuthEvent ( 'Zaphod', 'Beeblebrox' )
		self.assertEqual ( repr ( evt ), "smtp.AuthEvent(uid='Zaphod')" ) # <-- intentionally not showing pwd
		
		evt = smtp.MailFromEvent ( 'zaphod@beeblebrox.com' )
		self.assertEqual ( repr ( evt ), "smtp.MailFromEvent(mail_from='zaphod@beeblebrox.com')" )
		
		evt = smtp.RcptToEvent ( 'ford@prefect.com' )
		self.assertEqual ( repr ( evt ), "smtp.RcptToEvent(rcpt_to='ford@prefect.com')" )
		
		class AuthPluginStatus_Broken ( smtp.AuthPluginStatus ):
			def _resolve ( self, server: smtp.Server ) -> Iterator[smtp.Event]:
				yield from super()._resolve ( server )
		x = AuthPluginStatus_Broken()
		with self.assertRaises ( NotImplementedError ):
			list ( x._resolve ( None ) )
		
		class AuthPlugin_Broken ( smtp.AuthPlugin ):
			def first_line ( self, extra: str ) -> smtp.AuthPluginStatus:
				return super().first_line ( extra )
			def receive_line ( self, line: bytes ) -> smtp.AuthPluginStatus:
				return super().receive_line ( line )
		x = AuthPlugin_Broken()
		with self.assertRaises ( NotImplementedError ):
			x.first_line ( '' )
		with self.assertRaises ( NotImplementedError ):
			x.receive_line ( b'' )

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
