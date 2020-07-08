# system imports:
from abc import ABCMeta, abstractmethod
import logging
import trio # pip install trio trio-typing
import trio.testing
import unittest

# mail_proto imports:
import smtp
import smtp_trio

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		async def _test() -> None:
			thing1, thing2 = trio.testing.lockstep_stream_pair()
			
			async def client_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.client_task' )
				try:
					cli = smtp_trio.Client()
					
					await cli._connect ( stream )
					await cli.helo ( 'localhost' )
					with self.assertRaises ( smtp.ErrorResponse ):
						await cli.auth_plain1 ( 'Ford', 'Prefect' )
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
					log.exception ( f'server error: {e=}' )
				except smtp.Closed as e: # pragma: no cover
					log.debug ( f'server closed connection: {e=}' )
				finally:
					await stream.aclose()
			
			async def server_task ( stream: trio.abc.Stream ) -> None:
				log = logger.getChild ( 'main.server_task' )
				try:
					class TestServer ( smtp_trio.Server ):
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
					
					await srv.run ( stream )
				except smtp.Closed:
					pass
				finally:
					await stream.aclose()
			
			async with trio.open_nursery() as nursery:
				nursery.start_soon ( client_task, thing1 )
				nursery.start_soon ( server_task, thing2 )
		
		trio.run ( _test )

if __name__ == '__main__':
	logging.basicConfig (
		level = logging.DEBUG,
	)
	unittest.main()
