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
	def test_misc ( self ) -> None:
		log = logger.getChild ( 'Tests.test_misc' )
		test = self
		
		test.assertEqual ( smtp_proto.b64_encode ( 'Hello' ), 'SGVsbG8=' )
		test.assertEqual ( smtp_proto.b64_decode ( 'SGVsbG8=' ), 'Hello' )
		
		evt = smtp_proto.SendDataEvent ( b'foo' )
		test.assertEqual ( repr ( evt ), "smtp_proto.SendDataEvent(chunks=(b'foo',))" )
		
		# test edge cases in Connection buffer management
		if True:
			class BrokenConnection ( smtp_proto.Connection ):
				def _receive_line ( self, line: bytes ) -> Iterator[smtp_proto.Event]:
					yield from super()._receive_line ( line )
			broken = BrokenConnection ( False )
			with test.assertRaises ( NotImplementedError ):
				list ( broken._receive_line ( b'fubar' ) )
		
		class TestConnection ( smtp_proto.Connection ):
			def _receive_line ( self, line: bytes ) -> Iterator[smtp_proto.Event]:
				if line:
					yield smtp_proto.SendDataEvent ( line )
		
		def IsSendData ( evt: smtp_proto.Event ) -> smtp_proto.SendDataEvent:
			assert isinstance ( evt, smtp_proto.SendDataEvent )
			return evt
		
		conn = TestConnection ( False )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in conn.receive ( b'foo\r' ) ]
		test.assertEqual ( evts, [] )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in conn.receive ( b'\nba' ) ]
		test.assertEqual ( evts, [
			b'foo\r\n',
		] )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in conn.receive ( b'ar\r\nbaz' ) ]
		test.assertEqual ( evts, [
			b'baar\r\n',
		] )
		evts = [ b''.join ( IsSendData ( evt ).chunks ) for evt in conn.receive ( b'' ) ]
		test.assertEqual ( evts, [
			b'baz',
		] )
		with test.assertRaises ( smtp_proto.Closed ):
			list ( conn.receive ( b'' ) )
		
		conn = TestConnection ( False )
		with test.assertRaises ( smtp_proto.ProtocolError ):
			list ( conn.receive ( b'X' * smtp_proto._MAXLINE ) )
		
		test.assertEqual (
			repr ( smtp_proto.GreetingRequest() ),
			'smtp_proto.GreetingRequest()',
		)
		
		with test.assertRaises ( smtp_proto.Closed ):
			try:
				smtp_proto.Response.parse ( b'999 INVALID\r\n' )
			except smtp_proto.Closed as e:
				test.assertEqual ( e.args[0],
					"malformed response from server"
					" line=b'999 INVALID\\r\\n':"
					" e=AssertionError('invalid code=999')"
				)
				raise
		
		if False: # the following test may no longer be valid due to client proto refactor
			cli = smtp_proto.Client()
			with test.assertRaises ( smtp_proto.Closed ):
				try:
					list ( cli._receive_line ( b'XXX_BAD_MEDICINE' ) )
				except smtp_proto.Closed as e:
					test.assertEqual ( repr ( e ),
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
			test.assertEqual ( evt2._code, smtp_proto.AuthEvent.error_code )
			test.assertEqual ( evt2._message, smtp_proto.AuthEvent.error_message )
		
		#srv = smtp_proto.Server ( 'localhost' )
		#ss = smtp_proto.ServerState()
		#x = list ( ss.receive_line ( srv, b'FREE BEER\r\n' ) )
		#test.assertEqual ( repr ( x ), "[smtp_proto.SendDataEvent(data=b'500 command not recognized or not available: FREE\\r\\n')]" )
		
		evt3 = smtp_proto.Event()
		test.assertEqual ( repr ( evt3 ), 'smtp_proto.Event()' )
		
		evt4 = smtp_proto.CompleteEvent ( 'from@test.com', [ 'to@test.com' ], ( b'', ) )
		test.assertEqual ( repr ( evt4 ),
			"smtp_proto.CompleteEvent(_acceptance=None, _code=450, _message='Unable to accept message for delivery')",
		)
		
		evt5 = smtp_proto.AuthEvent ( 'Zaphod', 'Beeblebrox' )
		test.assertEqual ( repr ( evt5 ), "smtp_proto.AuthEvent(uid='Zaphod')" ) # <-- intentionally not showing pwd
		
		evt6 = smtp_proto.MailFromEvent ( 'zaphod@beeblebrox.com' )
		test.assertEqual ( repr ( evt6 ), "smtp_proto.MailFromEvent(mail_from='zaphod@beeblebrox.com')" )
		
		evt7 = smtp_proto.RcptToEvent ( 'ford@prefect.com' )
		test.assertEqual ( repr ( evt7 ), "smtp_proto.RcptToEvent(rcpt_to='ford@prefect.com')" )
		
		#class AuthPluginStatus_Broken ( smtp_proto.AuthPluginStatus ):
		#	def _resolve ( self, server: smtp_proto.Server ) -> Iterator[smtp_proto.Event]:
		#		yield from super()._resolve ( server )
		#x = AuthPluginStatus_Broken()
		#with test.assertRaises ( NotImplementedError ):
		#	list ( x._resolve ( None ) )
		
		#class AuthPlugin_Broken ( smtp_proto.AuthPlugin ):
		#	def first_line ( self, extra: str ) -> smtp_proto.AuthPluginStatus:
		#		return super().first_line ( extra )
		#	def receive_line ( self, line: bytes ) -> smtp_proto.AuthPluginStatus:
		#		return super().receive_line ( line )
		#x = AuthPlugin_Broken()
		#with test.assertRaises ( NotImplementedError ):
		#	x.first_line ( '' )
		#with test.assertRaises ( NotImplementedError ):
		#	x.receive_line ( b'' )
		
		test.assertEqual (
			smtp_proto._auth_lines ( 'Neque porro quisquam est qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit...'.split() ),
			[
				'AUTH Neque porro quisquam est qui dolorem ipsum quia dolor sit amet,',
				'AUTH consectetur, adipisci velit...',
			]
		)

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
