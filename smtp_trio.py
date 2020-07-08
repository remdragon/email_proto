from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import trio # pip install trio trio-typing

# mail_proto imports:
import smtp

logger = logging.getLogger ( __name__ )

happy_eyeballs_delay: float = 0.25 # this is the same as trio's default circa version 0.16.0

b2s = smtp.b2s

class Client:
	cli: smtp.Client
	stream: trio.abc.Stream
	
	async def connect ( self, hostname: str, port: int ) -> None:
		stream = await trio.open_tcp_stream ( hostname, port,
			happy_eyeballs_delay = happy_eyeballs_delay,
		)
		await self._connect ( stream )
	
	async def _connect ( self, stream: trio.abc.Stream ) -> None:
		self.stream = stream
		greeting = smtp.GreetingRequest()
		self.cli = smtp.Client ( greeting )
		await self._recv ( greeting )
	
	async def helo ( self, local_hostname: str ) -> None:
		await self._send_recv ( smtp.HeloRequest ( local_hostname ) )
	
	async def auth_plain1 ( self, uid: str, pwd: str ) -> None:
		await self._send_recv ( smtp.AuthPlain1Request ( uid, pwd ) )
	
	async def auth_plain2 ( self, uid: str, pwd: str ) -> None:
		await self._send_recv ( smtp.AuthPlain2Request ( uid, pwd ) )
	
	async def auth_login ( self, uid: str, pwd: str ) -> None:
		await self._send_recv ( smtp.AuthLoginRequest ( uid, pwd ) )
	
	async def mail_from ( self, email: str ) -> None:
		await self._send_recv ( smtp.MailFromRequest ( email ) )
	
	async def rcpt_to ( self, email: str ) -> None:
		await self._send_recv ( smtp.RcptToRequest ( email ) )
	
	async def data ( self, content: bytes ) -> None:
		await self._send_recv ( smtp.DataRequest ( content ) )
	
	async def quit ( self ) -> None:
		await self._send_recv ( smtp.QuitRequest() )
	
	async def _event ( self, event: smtp.Event ) -> None:
		log = logger.getChild ( 'Client._event' )
		if isinstance ( event, smtp.SendDataEvent ):
			log.debug ( f'C>{b2s(event.data).rstrip()}' )
			await self.stream.send_all ( event.data )
		else:
			assert False, f'unrecognized {event=}'
	
	async def _recv ( self, request: smtp.Request ) -> smtp.Response:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = await self.stream.receive_some()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				await self._event ( event )
		return request.response
	
	async def _send_recv ( self, request: smtp.Request ) -> smtp.Response:
		#log = logger.getChlid ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			await self._event ( event )
		return await self._recv ( request )


class Server ( metaclass = ABCMeta ):
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	@abstractmethod
	async def on_authenticate ( self, event: smtp.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_authenticate()' )
	
	@abstractmethod
	async def on_mail_from ( self, event: smtp.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_mail_from()' )
	
	@abstractmethod
	async def on_rcpt_to ( self, event: smtp.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	@abstractmethod
	async def on_complete ( self, event: smtp.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	async def run ( self, stream: trio.abc.Stream ) -> None:
		log = logger.getChild ( 'Server.run' )
		try:
			srv = smtp.Server ( self.hostname )
			
			async def _send ( data: bytes ) -> None:
				log.debug ( f'S>{b2s(data).rstrip()}' )
				await stream.send_all ( data )
			
			async def _recv() -> bytes:
				try:
					data = await stream.receive_some()
				except trio.EndOfChannel:
					raise smtp.Closed()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				return data
			
			await _send ( srv.greeting() )
			while True:
				data = await _recv()
				for event in srv.receive ( data ):
					if isinstance ( event, smtp.SendDataEvent ): # this will be the most common event...
						await _send ( event.data )
					elif isinstance ( event, smtp.RcptToEvent ): # 2nd most common event
						#log.debug ( f'{event.rcpt_to=}' )
						await self.on_rcpt_to ( event )
					elif isinstance ( event, smtp.AuthEvent ):
						await self.on_authenticate ( event )
					elif isinstance ( event, smtp.MailFromEvent ):
						#log.debug ( f'{event.mail_from=}' )
						await self.on_mail_from ( event )
					elif isinstance ( event, smtp.CompleteEvent ):
						await self.on_complete ( event )
					else:
						assert False, f'unrecognized {event=}'
		except smtp.Closed:
			pass
		finally:
			await stream.aclose()

if __name__ == '__main__':
	logging.basicConfig ( level = logging.DEBUG )
	
	import trio.testing
	
	async def main() -> None:
		
		thing1, thing2 = trio.testing.lockstep_stream_pair()
		
		async def client_task ( stream: trio.abc.Stream ) -> None:
			log = logger.getChild ( 'main.client_task' )
			try:
				cli = Client()
				
				await cli._connect ( stream )
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
			
			except smtp.ErrorResponse as e:
				log.error ( f'server error: {e=}' )
			except smtp.Closed as e:
				log.debug ( f'server closed connection: {e=}' )
			finally:
				await stream.aclose()
		
		async def server_task ( stream: trio.abc.Stream ) -> None:
			log = logger.getChild ( 'main.server_task' )
			try:
				class TestServer ( Server ):
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
						print ( f'MAIL FROM: {event.mail_from}' )
						for rcpt_to in event.rcpt_to:
							print ( f'RCPT TO: {rcpt_to}' )
						print ( '-' * 20 )
						print ( b2s ( b''.join ( event.data ) ) )
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
	
	trio.run ( main )
