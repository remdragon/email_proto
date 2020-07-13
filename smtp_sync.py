# system imports:
from abc import ABCMeta, abstractmethod
import logging
import sys

# email_proto imports:
import smtp_proto
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( metaclass = ABCMeta ):
	cli: smtp_proto.Client
	
	def _connect ( self, tls: bool ) -> smtp_proto.SuccessResponse:
		self.cli = smtp_proto.Client ( tls )
		return self.greeting()
	
	def greeting ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.GreetingRequest() )
	
	def helo ( self, local_hostname: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.HeloRequest ( local_hostname ) )
	
	def ehlo ( self, local_hostname: str ) -> smtp_proto.EhloResponse:
		r = self._send_recv ( smtp_proto.EhloRequest ( local_hostname ) )
		assert isinstance ( r, smtp_proto.EhloResponse ), f'invalid {r=}'
		return r
	
	def starttls ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.StartTlsRequest() )
	
	def auth_plain1 ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.AuthPlain1Request ( uid, pwd ) )
	
	def auth_plain2 ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.AuthPlain2Request ( uid, pwd ) )
	
	def auth_login ( self, uid: str, pwd: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.AuthLoginRequest ( uid, pwd ) )
	
	def expn ( self, mailbox: str ) -> smtp_proto.ExpnResponse:
		r = self._send_recv ( smtp_proto.ExpnRequest ( mailbox ) )
		assert isinstance ( r, smtp_proto.ExpnResponse )
		return r
	
	def vrfy ( self, mailbox: str ) -> smtp_proto.VrfyResponse:
		r = self._send_recv ( smtp_proto.VrfyRequest ( mailbox ) )
		assert isinstance ( r, smtp_proto.VrfyResponse )
		return r
	
	def mail_from ( self, email: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.MailFromRequest ( email ) )
	
	def rcpt_to ( self, email: str ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.RcptToRequest ( email ) )
	
	def data ( self, content: bytes ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.DataRequest ( content ) )
	
	def rset ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.RsetRequest() )
	
	def noop ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.NoOpRequest() )
	
	def quit ( self ) -> smtp_proto.SuccessResponse:
		return self._send_recv ( smtp_proto.QuitRequest() )
	
	def on_SendDataEvent ( self, event: smtp_proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Client.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			self._write ( chunk )
	
	def _on_event ( self, event: smtp_proto.Event ) -> None:
		log = logger.getChild ( 'Client._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
	
	def _recv ( self, request: smtp_proto.Request ) -> smtp_proto.SuccessResponse:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				self._on_event ( event )
		assert isinstance ( request.response, smtp_proto.SuccessResponse )
		return request.response
	
	def _send_recv ( self, request: smtp_proto.Request ) -> smtp_proto.SuccessResponse:
		log = logger.getChild ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			self._on_event ( event )
		return self._recv ( request )
	
	@abstractmethod
	def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._read()' )
	
	@abstractmethod
	def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._write()' )
	
	@abstractmethod
	def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
	
	@abstractmethod
	def on_StartTlsBeginEvent ( self, event: smtp_proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )


class Server ( metaclass = ABCMeta ):
	
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	def on_GreetingAcceptEvent ( self, event: smtp_proto.GreetingAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	def on_HeloAcceptEvent ( self, event: smtp_proto.HeloAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	def on_EhloAcceptEvent ( self, event: smtp_proto.EhloAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	@abstractmethod
	def on_StartTlsAcceptEvent ( self, event: smtp_proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsAcceptEvent()' )
	
	@abstractmethod
	def on_StartTlsBeginEvent ( self, event: smtp_proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )
	
	@abstractmethod
	def on_AuthEvent ( self, event: smtp_proto.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_AuthEvent()' )
	
	def on_ExpnEvent ( self, event: smtp_proto.ExpnEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	def on_VrfyEvent ( self, event: smtp_proto.VrfyEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	@abstractmethod
	def on_MailFromEvent ( self, event: smtp_proto.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_MailFromEvent()' )
	
	@abstractmethod
	def on_RcptToEvent ( self, event: smtp_proto.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_RcptToEvent()' )
	
	@abstractmethod
	def on_CompleteEvent ( self, event: smtp_proto.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_complete()' )
	
	def on_SendDataEvent ( self, event: smtp_proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Server.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			self._write ( chunk )
	
	def _on_event ( self, event: smtp_proto.Event ) -> None:
		log = logger.getChild ( 'Server._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
	
	def _run ( self, tls: bool ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = smtp_proto.Server ( self.hostname, tls )
			
			for event in srv.startup():
				self._on_event ( event )
			
			while True:
				try:
					data = self._read()
				except OSError as e: # TODO FIXME: more specific exception?
					raise smtp_proto.Closed ( repr ( e ) ) from e
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					self._on_event ( event )
		except smtp_proto.Closed as e:
			log.debug ( f'connection closed with reason: {e.args[0]!r}' )
		finally:
			self.close()
	
	@abstractmethod
	def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	def _write ( self, data: bytes ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}()' )
	
	@abstractmethod
	def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
