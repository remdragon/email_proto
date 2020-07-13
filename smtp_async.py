# system imports:
from abc import ABCMeta, abstractmethod
import logging
import sys

# email_proto imports:
import smtp_proto as proto
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( metaclass = ABCMeta ):
	cli: proto.Client
	
	async def _connect ( self, tls: bool ) -> proto.SuccessResponse:
		self.cli = proto.Client ( tls )
		return await self.greeting()
	
	async def greeting ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.GreetingRequest() )
	
	async def helo ( self, local_hostname: str ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.HeloRequest ( local_hostname ) )
	
	async def ehlo ( self, local_hostname: str ) -> proto.EhloResponse:
		r = await self._send_recv ( proto.EhloRequest ( local_hostname ) )
		assert isinstance ( r, proto.EhloResponse ), f'invalid {r=}'
		return r
	
	async def starttls ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.StartTlsRequest() )
	
	async def auth_plain1 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.AuthPlain1Request ( uid, pwd ) )
	
	async def auth_plain2 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.AuthPlain2Request ( uid, pwd ) )
	
	async def auth_login ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.AuthLoginRequest ( uid, pwd ) )
	
	async def expn ( self, mailbox: str ) -> proto.ExpnResponse:
		r = await self._send_recv ( proto.ExpnRequest ( mailbox ) )
		assert isinstance ( r, proto.ExpnResponse )
		return r
	
	async def vrfy ( self, mailbox: str ) -> proto.VrfyResponse:
		r = await self._send_recv ( proto.VrfyRequest ( mailbox ) )
		assert isinstance ( r, proto.VrfyResponse )
		return r
	
	async def mail_from ( self, email: str ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.MailFromRequest ( email ) )
	
	async def rcpt_to ( self, email: str ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.RcptToRequest ( email ) )
	
	async def data ( self, content: bytes ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.DataRequest ( content ) )
	
	async def rset ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.RsetRequest() )
	
	async def noop ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.NoOpRequest() )
	
	async def quit ( self ) -> proto.SuccessResponse:
		return await self._send_recv ( proto.QuitRequest() )
	
	async def on_SendDataEvent ( self, event: proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Client.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			await self._write ( chunk )
	
	async def _on_event ( self, event: proto.Event ) -> None:
		log = logger.getChild ( 'Client._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			await func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
	
	async def _recv ( self, request: proto.Request ) -> proto.SuccessResponse:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = await self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				await self._on_event ( event )
		assert isinstance ( request.response, proto.SuccessResponse )
		return request.response
	
	async def _send_recv ( self, request: proto.Request ) -> proto.SuccessResponse:
		log = logger.getChild ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			await self._on_event ( event )
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
	async def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
	
	@abstractmethod
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )


class Server ( metaclass = ABCMeta ):
	
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	async def on_GreetingAcceptEvent ( self, event: proto.GreetingAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	async def on_HeloAcceptEvent ( self, event: proto.HeloAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	async def on_EhloAcceptEvent ( self, event: proto.EhloAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	@abstractmethod
	async def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_starttls_accept()' )
	
	@abstractmethod
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )
	
	@abstractmethod
	async def on_AuthEvent ( self, event: proto.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_authenticate()' )
	
	async def on_ExpnEvent ( self, event: proto.ExpnEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	async def on_VrfyEvent ( self, event: proto.VrfyEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	@abstractmethod
	async def on_MailFromEvent ( self, event: proto.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_mail_from()' )
	
	@abstractmethod
	async def on_RcptToEvent ( self, event: proto.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	@abstractmethod
	async def on_CompleteEvent ( self, event: proto.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_rcpt_to()' )
	
	async def on_SendDataEvent ( self, event: proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Server.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			await self._write ( chunk )
	
	async def _on_event ( self, event: proto.Event ) -> None:
		log = logger.getChild ( 'Server._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			await func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
	
	async def _run ( self, tls: bool ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = proto.Server ( self.hostname, tls )
			
			for event in srv.startup():
				await self._on_event ( event )
			
			while True:
				try:
					data = await self._read()
				except OSError as e: # TODO FIXME: more specific exception?
					raise proto.Closed ( repr ( e ) ) from e
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					await self._on_event ( event )
		except proto.Closed as e:
			log.debug ( f'connection closed with reason: {e.args[0]!r}' )
		finally:
			await self.close()
	
	@abstractmethod
	async def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	async def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	async def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
