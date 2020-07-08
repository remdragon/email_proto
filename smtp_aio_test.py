# system imports:
from abc import ABCMeta, abstractmethod
import asyncio
import logging
import unittest

# mail_proto imports:
if not __package__:
	from _aiotesting import open_pipe_stream
else:
	from ._aiotesting import open_pipe_stream
import smtp
import smtp_aio

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ):
		async def _test() -> None:
			
			# TODO FIXME: apparently socket.socketpair() does work on Windows, use that instead of _aiotesting.open_pipe_stream()
			rx1, tx1 = open_pipe_stream()
			rx2, tx2 = open_pipe_stream()
			
			async def client_task ( rx: asyncio.StreamReader, tx: asyncio.StreamWriter ) -> None:
				log = logger.getChild ( 'main.client_task' )
				try:
					cli = smtp_aio.Client()
					
					await cli._connect ( rx, tx )
					await cli.helo ( 'localhost' )
					await cli.auth_plain1 ( 'Zaphod', 'Beeblebrox' )
					await cli.mail_from ( 'from@test.com' )
					await cli.rcpt_to ( 'to@test.com' )
					await cli.data (
						b'From: from@test.com\r\n'
						b'To: to@test.com\r\n'
						b'Subject: Test email\r\n'
						b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
						b'\r\n' # a sane person would use the email module to create their email content...
						b'This is a test. This message does not end in a period, period.\r\n'
					)
					await cli.quit()
				
				except smtp.ErrorResponse as e: # pragma: no cover
					log.error ( f'server error: {e=}' )
				except smtp.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					tx.close()
			
			async def server_task ( rx: asyncio.StreamReader, tx: asyncio.StreamWriter ) -> None:
				log = logger.getChild ( 'main.server_task' )
				try:
					class TestServer ( smtp_aio.Server ):
						async def on_authenticate ( self, event: smtp.AuthEvent ) -> None:
							if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
								event.accept()
							else:
								event.reject()
						
						async def on_mail_from ( self, event: smtp.MailFromEvent ) -> None:
							event.accept() # or .reject()
						
						async def on_rcpt_to ( self, event: smtp.RcptToEvent ) -> None:
							event.accept() # or .reject()
						
						async def on_complete ( self, event: smtp.CompleteEvent ) -> None:
							log.debug ( f'MAIL FROM: {event.mail_from}' )
							for rcpt_to in event.rcpt_to:
								log.debug ( f'RCPT TO: {rcpt_to}' )
							log.debug ( '-' * 20 )
							log.debug ( b2s ( b''.join ( event.data ) ) )
							event.accept() # or .reject()
					
					srv = TestServer ( 'milliways.local' )
					
					await srv.run ( rx, tx )
				except smtp.Closed:
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
