# system imports:
from abc import ABCMeta, abstractmethod
import asyncio
import logging
import unittest

# mail_proto imports:
if not __package__:
	from _aiotesting import open_pipe_stream
else:
	from ._aiotesting import open_pipe_stream # type: ignore
import smtp_proto
import smtp_aio

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		async def _test() -> None:
			
			# TODO FIXME: apparently socket.socketpair() does work on Windows, use that instead of _aiotesting.open_pipe_stream()
			rx1, tx1 = open_pipe_stream()
			rx2, tx2 = open_pipe_stream()
			
			async def client_task ( rx: asyncio.StreamReader, tx: asyncio.StreamWriter ) -> None:
				log = logger.getChild ( 'main.client_task' )
				try:
					cli = smtp_aio.Client()
					cli.rx, cli.tx = rx, tx
					
					self.assertEqual (
						repr ( await cli._connect() ),
						"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
					)
					
					r = await cli.ehlo ( 'localhost' )
					self.assertEqual ( type ( r ), smtp_proto.EhloResponse )
					self.assertEqual ( r.code, 250 )
					self.assertEqual ( sorted ( r.lines ), [
						'AUTH PLAIN LOGIN',
						'STARTTLS',
						'milliways.local greets localhost',
					] )
					
					self.assertEqual (
						repr ( await cli.auth_plain1 ( 'Zaphod', 'Beeblebrox' ) ),
						"smtp_proto.SuccessResponse(235, 'Authentication successful')",
					)
					
					self.assertEqual (
						repr ( await cli.mail_from ( 'from@test.com' ) ),
						"smtp_proto.SuccessResponse(250, 'OK')",
					)
					
					self.assertEqual (
						repr ( await cli.rcpt_to ( 'to@test.com' ) ),
						"smtp_proto.SuccessResponse(250, 'OK')",
					)
					
					self.assertEqual ( repr ( await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
						b'.<<< Evil line beginning with a dot\r\n'
						b'Last line of message\r\n'
					) ), "smtp_proto.SuccessResponse(250, 'Message accepted for delivery')" )
					
					self.assertEqual (
						repr ( await cli.quit() ),
						"smtp_proto.SuccessResponse(250, 'OK')",
					)
				
				except smtp_proto.ErrorResponse as e: # pragma: no cover
					log.error ( f'server error: {e=}' )
				except smtp_proto.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					tx.close()
			
			async def server_task ( rx: asyncio.StreamReader, tx: asyncio.StreamWriter ) -> None:
				log = logger.getChild ( 'main.server_task' )
				try:
					class TestServer ( smtp_aio.Server ):
						async def on_starttls_accept ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None:
							event.reject() # not implemented yet
						
						async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
							raise NotImplementedError
						
						async def on_authenticate ( self, event: smtp_proto.AuthEvent ) -> None:
							if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
								event.accept()
							else:
								event.reject()
						
						async def on_mail_from ( self, event: smtp_proto.MailFromEvent ) -> None:
							event.accept() # or .reject()
						
						async def on_rcpt_to ( self, event: smtp_proto.RcptToEvent ) -> None:
							event.accept() # or .reject()
						
						async def on_complete ( self, event: smtp_proto.CompleteEvent ) -> None:
							log.debug ( f'MAIL FROM: {event.mail_from}' )
							for rcpt_to in event.rcpt_to:
								log.debug ( f'RCPT TO: {rcpt_to}' )
							log.debug ( '-' * 20 )
							log.debug ( b2s ( b''.join ( event.data ) ) )
							event.accept() # or .reject()
					
					srv = TestServer ( 'milliways.local' )
					srv.esmtp_pipelining = False # code coverage reasons
					srv.esmtp_8bitmime = False # code coverage reasons
					
					await srv.run ( rx, tx )
				except smtp_proto.Closed:
					pass
				finally:
					tx.close()
			
			task1 = asyncio.create_task ( client_task ( rx1, tx2 ) )
			task2 = asyncio.create_task ( server_task ( rx2, tx1 ) )
			
			await task1
			await task2
		
		asyncio.run ( _test() )


if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
