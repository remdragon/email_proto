# system imports:
from abc import ABCMeta, abstractmethod
import logging

# email_proto imports:
import smtp_proto

logger = logging.getLogger ( __name__ )

b2s = smtp_proto.b2s

class Client ( metaclass = ABCMeta ):
	cli: smtp_proto.Client
	
	async def _connect ( self ) -> smtp_proto.SuccessResponse:
		self.cli = smtp_proto.Client()
		return await self.greeting()
	
	async def greeting ( self ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.GreetingRequest() )
	
	async def helo ( self, local_hostname: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.HeloRequest ( local_hostname ) )
	
	async def ehlo ( self, local_hostname: str ) -> smtp_proto.EhloResponse:
		r = await self._send_recv ( smtp_proto.EhloRequest ( local_hostname ) )
		assert isinstance ( r, smtp_proto.EhloResponse ), f'invalid {r=}'
		return r
	
	async def starttls ( self ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.StartTlsRequest() )
	
	async def auth_plain1 ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.AuthPlain1Request ( uid, pwd ) )
	
	async def auth_plain2 ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.AuthPlain2Request ( uid, pwd ) )
	
	async def auth_login ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.AuthLoginRequest ( uid, pwd ) )
	
	async def expn ( self, mailbox: str ) -> smtp_proto.ExpnResponse:
		return await self._send_recv ( smtp_proto.VrfyRequest ( mailbox ) )
	
	async def vrfy ( self, mailbox: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.VrfyRequest ( mailbox ) )
	
	async def mail_from ( self, email: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.MailFromRequest ( email ) )
	
	async def rcpt_to ( self, email: str ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.RcptToRequest ( email ) )
	
	async def data ( self, content: bytes ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.DataRequest ( content ) )
	
	async def rset ( self ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.RsetRequest() )
	
	async def noop ( self ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.NoOpRequest() )
	
	async def quit ( self ) -> smtp_proto.SuccessResponse:
		return await self._send_recv ( smtp_proto.QuitRequest() )
	
	async def _event ( self, event: smtp_proto.Event ) -> None:
		log = logger.getChild ( 'Client._event' )
		if isinstance ( event, smtp_proto.SendDataEvent ):
			log.debug ( f'C>{b2s(event.data).rstrip()}' )
			await self._write ( event.data )
		elif isinstance ( event, smtp_proto.StartTlsBeginEvent ):
			await self.on_starttls_begin ( event )
		else:
			assert False, f'unrecognized {event=}'
	
	async def _recv ( self, request: smtp_proto.Request ) -> smtp_proto.SuccessResponse:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = await self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				await self._event ( event )
		return request.response
	
	async def _send_recv ( self, request: smtp_proto.Request ) -> smtp_proto.SuccessResponse:
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
	
	@abstractmethod
	async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._close()' )


class Server ( metaclass = ABCMeta ):
	esmtp_8bitmime: bool = True
	esmtp_pipelining: bool = True
	
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	@abstractmethod
	async def on_starttls_accept ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_starttls_accept()' )
	
	@abstractmethod
	async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_starttls_begin()' )
	
	@abstractmethod
	async def on_authenticate ( self, event: smtp_proto.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_authenticate()' )
	
	async def on_expn ( self, event: smtp_proto.ExpnEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	async def on_vrfy ( self, event: smtp_proto.VrfyEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	@abstractmethod
	async def on_mail_from ( self, event: smtp_proto.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_mail_from()' )
	
	@abstractmethod
	async def on_rcpt_to ( self, event: smtp_proto.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	@abstractmethod
	async def on_complete ( self, event: smtp_proto.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	async def _run ( self ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = smtp_proto.Server ( self.hostname )
			srv.esmtp_8bitmime = self.esmtp_8bitmime
			srv.esmtp_pipelining = self.esmtp_pipelining
			
			async def _send ( data: bytes ) -> None:
				log.debug ( f'S>{b2s(data).rstrip()}' )
				await self._write ( data )
			
			await _send ( srv.greeting() )
			while True:
				try:
					data = await self._read()
				except OSError: # TODO FIXME: more specific exception?
					raise smtp_proto.Closed()
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					if isinstance ( event, smtp_proto.SendDataEvent ): # this will be the most common event...
						await _send ( event.data )
					elif isinstance ( event, smtp_proto.RcptToEvent ): # 2nd most common event
						await self.on_rcpt_to ( event )
					elif isinstance ( event, smtp_proto.StartTlsAcceptEvent ):
						await self.on_starttls_accept ( event )
					elif isinstance ( event, smtp_proto.StartTlsBeginEvent ):
						await self.on_starttls_begin ( event )
					elif isinstance ( event, smtp_proto.AuthEvent ):
						await self.on_authenticate ( event )
					elif isinstance ( event, smtp_proto.MailFromEvent ):
						await self.on_mail_from ( event )
					elif isinstance ( event, smtp_proto.CompleteEvent ):
						await self.on_complete ( event )
					elif isinstance ( event, smtp_proto.ExpnEvent ):
						await self.on_expn ( event )
					elif isinstance ( event, smtp_proto.VrfyEvent ):
						await self.on_vrfy ( event )
					else:
						assert False, f'unrecognized {event=}'
		except smtp_proto.Closed:
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
