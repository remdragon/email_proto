# system imports;
from functools import partial
import logging
import socket
import ssl
import sys
import threading
import trustme # pip install trustme
import unittest

# mail_proto imports:
import itrustme
import smtp_proto
import smtp_socket

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s

trust = itrustme.ServerOnly ( server_hostname = 'milliways.local' )

class Tests ( unittest.TestCase ):
	def test_auth_plain1 ( self ) -> None:
		thing1, thing2 = socket.socketpair()
		
		def client_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_auth_plain1.client_task' )
			try:
				cli = smtp_socket.Client()
				
				cli.server_hostname = 'milliways.local'
				cli.ssl_context = trust.client_context()
				cli.sock = sock
				
				self.assertEqual (
					repr ( cli._connect() ),
					"smtp_proto.SuccessResponse(220, 'milliways.local ESMTP')",
				)
				
				self.assertEqual (
					repr ( cli.helo ( 'localhost' ) ),
					"smtp_proto.SuccessResponse(250, 'milliways.local greets localhost')",
				)
				
				self.assertEqual (
					repr ( cli.starttls() ),
					"smtp_proto.SuccessResponse(220, 'Go ahead, make my day')",
				)
				
				self.assertEqual (
					repr ( cli.auth_plain1 ( 'Zaphod', 'Beeblebrox' ) ),
					"smtp_proto.SuccessResponse(235, 'Authentication successful')",
				)
				
				self.assertEqual (
					repr ( cli.expn ( 'mike' ) ),
					"smtp_proto.ExpnResponse(250, 'mike@abc.com')",
				)
				
				self.assertEqual (
					repr ( cli.vrfy ( 'users-hackers' ) ),
					"smtp_proto.VrfyResponse(250, 'carol@abc.com', 'greg@abc.com', 'marcha@abc.com', 'peter@abc.com')",
				)
				
				self.assertEqual (
					repr ( cli.mail_from ( 'from@test.com' ) ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				self.assertEqual (
					repr ( cli.rcpt_to ( 'to@test.com' ) ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
				
				self.assertEqual ( repr ( cli.data (
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
					repr ( cli.quit() ),
					"smtp_proto.SuccessResponse(250, 'OK')",
				)
			
			except smtp_proto.Closed as e: # pragma: no cover
				log.debug ( f'server closed connection: {e=}' )
			except Exception:
				log.exception ( 'Unexpected client_task exception:' )
			finally:
				sock.close()
		
		def server_task ( sock: socket.socket ) -> None:
			log = logger.getChild ( 'test_auth_plain1.server_task' )
			try:
				class TestServer ( smtp_socket.Server ):
					def on_starttls_accept ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None:
						event.accept()
					
					def on_expnvrfy ( self, event: smtp_proto.ExpnVrfyEvent ) -> None:
						if event.mailbox == 'mike':
							event.accept ( 'mike@abc.com' )
						elif event.mailbox == 'users-hackers':
							event.accept ( 'carol@abc.com', 'greg@abc.com', 'marcha@abc.com', 'peter@abc.com' ) # sheesh, someone was a Brady's Bunch fan
						else:
							event.reject()
					
					def on_expn ( self, event: smtp_proto.ExpnEvent ) -> None:
						self.on_expnvrfy ( event )
					
					def on_vrfy ( self, event: smtp_proto.VrfyEvent ) -> None:
						self.on_expnvrfy ( event )
					
					def on_authenticate ( self, event: smtp_proto.AuthEvent ) -> None:
						if event.uid == 'Zaphod' and event.pwd == 'Beeblebrox':
							event.accept()
						else:
							event.reject()
					
					def on_mail_from ( self, event: smtp_proto.MailFromEvent ) -> None:
						event.accept() # or .reject()
					
					def on_rcpt_to ( self, event: smtp_proto.RcptToEvent ) -> None:
						event.accept() # or .reject()
					
					def on_complete ( self, event: smtp_proto.CompleteEvent ) -> None:
						log.debug ( f'MAIL FROM: {event.mail_from}' )
						for rcpt_to in event.rcpt_to:
							log.debug ( f'RCPT TO: {rcpt_to}' )
						log.debug ( '-' * 20 )
						log.debug ( b2s ( b''.join ( event.data ) ) )
						event.accept() # or .reject()
				
				srv = TestServer ( 'milliways.local' )
				
				srv.ssl_context = trust.server_context()
				
				srv.run ( sock )
			except smtp_proto.Closed:
				pass
			except Exception:
				log.exception ( 'Unexpected server_task exception:' )
			finally:
				sock.close()
		
		thread1 = threading.Thread ( target = partial ( client_task, thing1 ), name = 'SocketClientThread' )
		thread2 = threading.Thread ( target = partial ( server_task, thing2 ), name = 'SocketServerThread' )
		
		thread1.start()
		thread2.start()
		
		thread1.join()
		thread2.join()

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	unittest.main()
