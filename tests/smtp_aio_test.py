# system imports:
from abc import ABCMeta, abstractmethod
import asyncio
import logging
import socket
import unittest

# mail_proto imports:
import smtp_proto
import smtp_aio
from util import b2s

logger = logging.getLogger ( __name__ )


class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		test = self
		
		async def _test() -> None:
			thing1, thing2 = socket.socketpair()
			
			async def client_task ( sock: socket.socket ) -> None:
				log = logger.getChild ( 'main.client_task' )
				rx, tx = await asyncio.open_connection ( sock = sock )
				xport = smtp_aio.Transport ( rx, tx )
				tls = True
				cli = smtp_aio.Client ( xport, tls, 'milliways.local' )
				try:
					test.assertEqual (
						repr ( await cli.greeting() ),
						"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
					)
					
					r = await cli.ehlo ( 'localhost' )
					test.assertEqual ( type ( r ), smtp_proto.EhloResponse )
					test.assertEqual ( r.code, 250 )
					test.assertEqual ( r.lines[0],
						'milliways.local greets localhost',
					)
					test.assertEqual ( sorted ( r.esmtp_auth ), [
						# TODO FIXME WARNING: we are *pretending* to be in ssl in this test
						'LOGIN',
						'PLAIN',
					] )
					test.assertEqual ( sorted ( r.esmtp_features ), [
						'8BITMIME',
						'PIPELINING',
						#'STARTTLS', # not available because smtp_proto thinks we're already encrypted
					] )
					
					test.assertEqual (
						repr ( await cli.auth_plain1 ( 'Zaphod', 'Beeblebrox' ) ),
						"smtp_proto.SuccessResponse(235, 'Authentication successful')",
					)
					
					test.assertEqual (
						repr ( await cli.mail_from ( 'from@test.com' ) ),
						"smtp_proto.SuccessResponse(250, 'OK')",
					)
					
					test.assertEqual (
						repr ( await cli.rcpt_to ( 'to@test.com' ) ),
						"smtp_proto.SuccessResponse(250, 'OK')",
					)
					
					test.assertEqual ( repr ( await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
					) ), "smtp_proto.SuccessResponse(250, 'Message accepted for delivery')" )
					
					test.assertEqual (
						repr ( await cli.quit() ),
						"smtp_proto.SuccessResponse(221, 'Closing connection')",
					)
				
				except smtp_proto.ErrorResponse as e: # pragma: no cover
					log.error ( f'server error: {e=}' )
				except smtp_proto.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await cli.close()
			
			async def server_task ( sock: socket.socket ) -> None:
				log = logger.getChild ( 'main.server_task' )
				class TestServer ( smtp_aio.Server ):
					async def on_StartTlsAcceptEvent ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None:
						event.reject() # not ready yet
					
					async def on_AuthEvent ( self, event: smtp_proto.AuthEvent ) -> None:
						if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
							event.accept()
						else:
							event.reject()
					
					async def on_MailFromEvent ( self, event: smtp_proto.MailFromEvent ) -> None:
						event.accept() # or .reject()
					
					async def on_RcptToEvent ( self, event: smtp_proto.RcptToEvent ) -> None:
						event.accept() # or .reject()
					
					async def on_CompleteEvent ( self, event: smtp_proto.CompleteEvent ) -> None:
						test.assertEqual ( event.mail_from, 'from@test.com' )
						test.assertEqual ( event.rcpt_to, [ 'to@test.com' ] )
						lines = b''.join ( event.data ).split ( b'\r\n' )
						test.assertEqual ( lines[0], b'From: from@test.com' )
						test.assertEqual ( lines[1], b'To: to@test.com' )
						test.assertEqual ( lines[2], b'Subject: Test email' )
						test.assertEqual ( lines[3], b'Date: 2000-01-01T00:00:00Z' )
						test.assertEqual ( lines[4], b'' )
						test.assertEqual ( lines[5], b'This is a test. This message does not end in a period, period.' )
						test.assertEqual ( lines[6], b'.<<< Evil line beginning with a dot' )
						test.assertEqual ( lines[7], b'Last line of message' )
						test.assertEqual ( lines[8], b'' )
						with test.assertRaises ( IndexError ):
							test.assertEqual ( lines[9], b'?????' )
						event.accept() # or .reject()
				
				rx, tx = await asyncio.open_connection ( sock = sock )
				xport = smtp_aio.Transport ( rx, tx )
				tls = True
				srv = TestServer ( xport, tls, 'milliways.local' )
				
				try:
					await srv.run()
				except smtp_proto.Closed:
					pass
				finally:
					await srv.close()
			
			task1 = asyncio.create_task ( client_task ( thing1 ) )
			task2 = asyncio.create_task ( server_task ( thing2 ) )
			
			await task1
			await task2
		
		asyncio.run ( _test() )


if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
