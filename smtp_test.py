# system imports:
import contextlib
import logging
import unittest
from typing import Iterator

# email_proto imports:
import smtp_proto

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
		
		self.assertEqual ( smtp_proto.b64_encode ( 'Hello' ), 'SGVsbG8=' )
		self.assertEqual ( smtp_proto.b64_decode ( 'SGVsbG8=' ), 'Hello' )
		
		evt = smtp_proto.SendDataEvent ( b'foo' )
		self.assertEqual ( repr ( evt ), "smtp_proto.SendDataEvent(chunks=(b'foo',))" )
		
		# test edge cases in Connection buffer management
		if True:
			class BrokenConnection ( smtp_proto.Connection ):
				def _receive_line ( self, line: bytes ) -> Iterator[smtp_proto.Event]:
					yield from super()._receive_line ( line )
			broken = BrokenConnection ( False )
			with self.assertRaises ( NotImplementedError ):
				list ( broken._receive_line ( b'fubar' ) )
		
		class TestConnection ( smtp_proto.Connection ):
			def _receive_line ( self, line: bytes ) -> Iterator[smtp_proto.Event]:
				if line:
					yield smtp_proto.SendDataEvent ( line )
		
		conn = TestConnection ( False )
		evts = list ( conn.receive ( b'foo\r' ) )
		self.assertEqual ( evts, [] )
		evts = [ b''.join ( evt.chunks ) for evt in conn.receive ( b'\nba' ) ]
		self.assertEqual ( evts, [
			b'foo\r\n',
		] )
		evts = [ b''.join ( evt.chunks ) for evt in conn.receive ( b'ar\r\nbaz' ) ]
		self.assertEqual ( evts, [
			b'baar\r\n',
		] )
		evts = [ b''.join ( evt.chunks ) for evt in conn.receive ( b'' ) ]
		self.assertEqual ( evts, [
			b'baz',
		] )
		with self.assertRaises ( smtp_proto.Closed ):
			evts = list ( conn.receive ( b'' ) )
		
		conn = TestConnection ( False )
		with self.assertRaises ( smtp_proto.ProtocolError ):
			evts = list ( conn.receive ( b'X' * smtp_proto._MAXLINE ) )
		
		if False: # the following test may no longer be valid due to client proto refactor
			cli = smtp_proto.Client()
			with self.assertRaises ( smtp_proto.Closed ):
				try:
					list ( cli._receive_line ( b'XXX_BAD_MEDICINE' ) )
				except smtp_proto.Closed as e:
					self.assertEqual ( repr ( e ),
						'''Closed('malformed response from server line=b\\'XXX_BAD_MEDICINE\\': e=ValueError("invalid literal for int() with base 10: b\\'XXX\\'")')'''
					)
					raise
		
		evt2 = smtp_proto.AuthEvent ( 'foo', 'bar' )
		evt2.reject ( 404, 'Not Found' )
		
		with quiet_logging():
			evt2.reject (
				250, # <-- not valid for a rejection
				'Not Found\n', # <-- not valid ( contains a \n )
			)
			# make sure ev2 has it's defaults since we fed it invalid data
			self.assertEqual ( evt2._code, smtp_proto.AuthEvent.error_code )
			self.assertEqual ( evt2._message, smtp_proto.AuthEvent.error_message )
		
		#srv = smtp_proto.Server ( 'localhost' )
		#ss = smtp_proto.ServerState()
		#x = list ( ss.receive_line ( srv, b'FREE BEER\r\n' ) )
		#self.assertEqual ( repr ( x ), "[smtp_proto.SendDataEvent(data=b'500 command not recognized or not available: FREE\\r\\n')]" )
		
		evt = smtp_proto.Event()
		self.assertEqual ( repr ( evt ), 'smtp_proto.Event()' )
		
		evt = smtp_proto.CompleteEvent ( 'from@test.com', [ 'to@test.com' ], b'' )
		self.assertEqual ( repr ( evt ),
			"smtp_proto.CompleteEvent(_acceptance=None, _code=450, _message='Unable to accept message for delivery')",
		)
		
		evt = smtp_proto.AuthEvent ( 'Zaphod', 'Beeblebrox' )
		self.assertEqual ( repr ( evt ), "smtp_proto.AuthEvent(uid='Zaphod')" ) # <-- intentionally not showing pwd
		
		evt = smtp_proto.MailFromEvent ( 'zaphod@beeblebrox.com' )
		self.assertEqual ( repr ( evt ), "smtp_proto.MailFromEvent(mail_from='zaphod@beeblebrox.com')" )
		
		evt = smtp_proto.RcptToEvent ( 'ford@prefect.com' )
		self.assertEqual ( repr ( evt ), "smtp_proto.RcptToEvent(rcpt_to='ford@prefect.com')" )
		
		#class AuthPluginStatus_Broken ( smtp_proto.AuthPluginStatus ):
		#	def _resolve ( self, server: smtp_proto.Server ) -> Iterator[smtp_proto.Event]:
		#		yield from super()._resolve ( server )
		#x = AuthPluginStatus_Broken()
		#with self.assertRaises ( NotImplementedError ):
		#	list ( x._resolve ( None ) )
		
		#class AuthPlugin_Broken ( smtp_proto.AuthPlugin ):
		#	def first_line ( self, extra: str ) -> smtp_proto.AuthPluginStatus:
		#		return super().first_line ( extra )
		#	def receive_line ( self, line: bytes ) -> smtp_proto.AuthPluginStatus:
		#		return super().receive_line ( line )
		#x = AuthPlugin_Broken()
		#with self.assertRaises ( NotImplementedError ):
		#	x.first_line ( '' )
		#with self.assertRaises ( NotImplementedError ):
		#	x.receive_line ( b'' )
		
		self.assertEqual (
			smtp_proto._auth_lines ( 'Neque porro quisquam est qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit...'.split() ),
			[
				'AUTH Neque porro quisquam est qui dolorem ipsum quia dolor sit amet,',
				'AUTH consectetur, adipisci velit...',
			]
		)

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
