# system imports:
from abc import ABCMeta, abstractmethod
import logging

# email_proto imports:
import smtp

logger = logging.getLogger ( __name__ )

b2s = smtp.b2s

class Client ( metaclass = ABCMeta ):
	cli: smtp.Client
	
	async def _connect ( self ) -> smtp.Response:
		greeting = smtp.GreetingRequest()
		self.cli = smtp.Client ( greeting )
		return await self._recv ( greeting )
	
	async def helo ( self, local_hostname: str ) -> smtp.Response:
		return await self._send_recv ( smtp.HeloRequest ( local_hostname ) )
	
	async def ehlo ( self, local_hostname: str ) -> smtp.Response:
		return await self._send_recv ( smtp.EhloRequest ( local_hostname ) )
	
	async def auth_plain1 ( self, uid: str, pwd: str ) -> smtp.Response:
		return await self._send_recv ( smtp.AuthPlain1Request ( uid, pwd ) )
	
	async def auth_plain2 ( self, uid: str, pwd: str ) -> smtp.Response:
		return await self._send_recv ( smtp.AuthPlain2Request ( uid, pwd ) )
	
	async def auth_login ( self, uid: str, pwd: str ) -> smtp.Response:
		return await self._send_recv ( smtp.AuthLoginRequest ( uid, pwd ) )
	
	async def expn ( self, maillist: str ) -> smtp.Response:
		log = logger.getChild ( 'Client.expn' )
		log.debug ( f'{maillist=}' )
		return await self._send_recv ( smtp.ExpnRequest ( maillist ) )
	
	async def vrfy ( self, mailbox: str ) -> smtp.Response:
		return await self._send_recv ( smtp.VrfyRequest ( mailbox ) )
	
	async def mail_from ( self, email: str ) -> smtp.Response:
		return await self._send_recv ( smtp.MailFromRequest ( email ) )
	
	async def rcpt_to ( self, email: str ) -> smtp.Response:
		return await self._send_recv ( smtp.RcptToRequest ( email ) )
	
	async def data ( self, content: bytes ) -> smtp.Response:
		return await self._send_recv ( smtp.DataRequest ( content ) )
	
	async def rset ( self ) -> smtp.Response:
		return await self._send_recv ( smtp.RsetRequest() )
	
	async def noop ( self ) -> smtp.Response:
		return await self._send_recv ( smtp.NoOpRequest() )
	
	async def quit ( self ) -> smtp.Response:
		return await self._send_recv ( smtp.QuitRequest() )
	
	async def _event ( self, event: smtp.Event ) -> None:
		log = logger.getChild ( 'Client._event' )
		if isinstance ( event, smtp.SendDataEvent ):
			log.debug ( f'C>{b2s(event.data).rstrip()}' )
			await self._write ( event.data )
		elif isinstance ( event, smtp.ErrorEvent ):
			raise smtp.ErrorResponse ( event.code, event.message )
		else:
			assert False, f'unrecognized {event=}'
	
	async def _recv ( self, request: smtp.Request ) -> smtp.Response:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = await self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				await self._event ( event )
		log.debug ( f'{request=} -> {request.response=}' )
		return request.response
	
	async def _send_recv ( self, request: smtp.Request ) -> smtp.Response:
		log = logger.getChild ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			await self._event ( event )
		return await self._recv ( request )
	
	@abstractmethod
	async def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._read()' )
	
	@abstractmethod
	async def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._write()' )
	
	@abstractmethod
	async def _close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._close()' )


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
	
	async def _run ( self ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = smtp.Server ( self.hostname )
			
			async def _send ( data: bytes ) -> None:
				log.debug ( f'S>{b2s(data).rstrip()}' )
				await self._write ( data )
			
			await _send ( srv.greeting() )
			while True:
				try:
					data = await self._read()
				except OSError: # TODO FIXME: more specific exception?
					raise smtp.Closed()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					if isinstance ( event, smtp.SendDataEvent ): # this will be the most common event...
						await _send ( event.data )
					elif isinstance ( event, smtp.RcptToEvent ): # 2nd most common event
						await self.on_rcpt_to ( event )
					elif isinstance ( event, smtp.AuthEvent ):
						await self.on_authenticate ( event )
					elif isinstance ( event, smtp.MailFromEvent ):
						await self.on_mail_from ( event )
					elif isinstance ( event, smtp.CompleteEvent ):
						await self.on_complete ( event )
					elif isinstance ( event, smtp.ErrorEvent ):
						raise smtp.ErrorResponse ( event.code, event.message )
					else:
						assert False, f'unrecognized {event=}'
		except smtp.Closed:
			pass
		finally:
			await self._close()
	
	@abstractmethod
	async def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	async def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	async def _close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._close()' )
