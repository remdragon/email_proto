# system imports;
import logging
import socket
import sys
import threading
import unittest

# mail_proto imports:
import smtp
import smtp_socket

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ):
		thing1, thing2 = socket.socketpair()
		
		def client_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_auth_plain1.client_task' )
			try:
				cli = smtp_socket.Client()
				
				cli._connect ( sock )
				cli.helo ( 'localhost' )
				cli.auth_plain1 ( 'Zaphod', 'Beeblebrox' )
				cli.mail_from ( 'from@test.com' )
				cli.rcpt_to ( 'to@test.com' )
				cli.data (
					b'From: from@test.com\r\n'
					b'To: to@test.com\r\n'
					b'Subject: Test email\r\n'
					b'Date: 2000-01-01T00:00:00Z\r\n' # yes I know this isn't formatted correctly...
					b'\r\n' # a sane person would use the email module to create their email content...
					b'This is a test. This message does not end in a period, period.\r\n'
				)
				cli.quit()
			
			except smtp.ErrorResponse as e: # pragma: no cover
				log.error ( f'server error: {e=}' )
			except smtp.Closed as e: # pragma: no cover
				log.debug ( f'server closed connection: {e=}' )
			finally:
				sock.close()
		
		def server_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_auth_plain1.server_task' )
			try:
				class TestServer ( smtp_socket.Server ):
					def on_authenticate ( self, event: smtp.AuthEvent ) -> None:
						if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
							event.accept()
						else:
							event.reject()
					
					def on_mail_from ( self, event: smtp.MailFromEvent ) -> None:
						event.accept() # or .reject()
					
					def on_rcpt_to ( self, event: smtp.RcptToEvent ) -> None:
						event.accept() # or .reject()
					
					def on_complete ( self, event: smtp.CompleteEvent ) -> None:
						log.debug ( f'MAIL FROM: {event.mail_from}' )
						for rcpt_to in event.rcpt_to:
							log.debug ( f'RCPT TO: {rcpt_to}' )
						log.debug ( '-' * 20 )
						log.debug ( b2s ( b''.join ( event.data ) ) )
						event.accept() # or .reject()
				
				srv = TestServer ( 'milliways.local' )
				
				srv.run ( sock )
			except smtp.Closed:
				pass
			finally:
				sock.close()
		
		thread1 = threading.Thread ( target = client_task, args = ( thing1, ) )
		thread2 = threading.Thread ( target = server_task, args = ( thing2, ) )
		
		thread1.start()
		thread2.start()
		
		thread1.join()
		thread2.join()
		
		return 7

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
