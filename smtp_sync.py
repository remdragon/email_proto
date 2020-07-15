# system imports:
from abc import abstractmethod
import logging
import sys

# email_proto imports:
import smtp_proto as proto
from transports import SyncTransport
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( SyncTransport ):
	cli: proto.Client
	
	def _connect ( self, tls: bool ) -> proto.SuccessResponse:
		self.cli = proto.Client ( tls )
		return self.greeting()
	
	def greeting ( self ) -> proto.SuccessResponse:
		return self._send_recv ( proto.GreetingRequest() )
	
	def helo ( self, local_hostname: str ) -> proto.SuccessResponse:
		return self._send_recv ( proto.HeloRequest ( local_hostname ) )
	
	def ehlo ( self, local_hostname: str ) -> proto.EhloResponse:
		r = self._send_recv ( proto.EhloRequest ( local_hostname ) )
		assert isinstance ( r, proto.EhloResponse ), f'invalid {r=}'
		return r
	
	def starttls ( self ) -> proto.SuccessResponse:
		return self._send_recv ( proto.StartTlsRequest() )
	
	def auth_plain1 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return self._send_recv ( proto.AuthPlain1Request ( uid, pwd ) )
	
	def auth_plain2 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return self._send_recv ( proto.AuthPlain2Request ( uid, pwd ) )
	
	def auth_login ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return self._send_recv ( proto.AuthLoginRequest ( uid, pwd ) )
	
	def expn ( self, mailbox: str ) -> proto.ExpnResponse:
		r = self._send_recv ( proto.ExpnRequest ( mailbox ) )
		assert isinstance ( r, proto.ExpnResponse )
		return r
	
	def vrfy ( self, mailbox: str ) -> proto.VrfyResponse:
		r = self._send_recv ( proto.VrfyRequest ( mailbox ) )
		assert isinstance ( r, proto.VrfyResponse )
		return r
	
	def mail_from ( self, email: str ) -> proto.SuccessResponse:
		return self._send_recv ( proto.MailFromRequest ( email ) )
	
	def rcpt_to ( self, email: str ) -> proto.SuccessResponse:
		return self._send_recv ( proto.RcptToRequest ( email ) )
	
	def data ( self, content: bytes ) -> proto.SuccessResponse:
		return self._send_recv ( proto.DataRequest ( content ) )
	
	def rset ( self ) -> proto.SuccessResponse:
		return self._send_recv ( proto.RsetRequest() )
	
	def noop ( self ) -> proto.SuccessResponse:
		return self._send_recv ( proto.NoOpRequest() )
	
	def quit ( self ) -> proto.SuccessResponse:
		return self._send_recv ( proto.QuitRequest() )
	
	def on_SendDataEvent ( self, event: proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Client.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			self._write ( chunk )
	
	def _recv ( self, request: proto.Request ) -> proto.SuccessResponse:
		log = logger.getChild ( 'Client._recv' )
		while not request.response:
			data: bytes = self._read()
			log.debug ( f'S>{b2s(data).rstrip()}' )
			for event in self.cli.receive ( data ):
				self._on_event ( event )
		assert isinstance ( request.response, proto.SuccessResponse )
		return request.response
	
	def _send_recv ( self, request: proto.Request ) -> proto.SuccessResponse:
		log = logger.getChild ( 'Client._send_recv' )
		for event in self.cli.send ( request ):
			self._on_event ( event )
		return self._recv ( request )
	
	@abstractmethod
	def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )


class Server ( SyncTransport ):
	
	def __init__ ( self, hostname: str ) -> None:
		self.hostname = hostname
	
	def on_GreetingAcceptEvent ( self, event: proto.GreetingAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	def on_HeloAcceptEvent ( self, event: proto.HeloAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	def on_EhloAcceptEvent ( self, event: proto.EhloAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	@abstractmethod
	def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsAcceptEvent()' )
	
	@abstractmethod
	def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsBeginEvent()' )
	
	@abstractmethod
	def on_AuthEvent ( self, event: proto.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_AuthEvent()' )
	
	def on_ExpnEvent ( self, event: proto.ExpnEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	def on_VrfyEvent ( self, event: proto.VrfyEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	@abstractmethod
	def on_MailFromEvent ( self, event: proto.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_MailFromEvent()' )
	
	@abstractmethod
	def on_RcptToEvent ( self, event: proto.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_RcptToEvent()' )
	
	@abstractmethod
	def on_CompleteEvent ( self, event: proto.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_complete()' )
	
	def on_SendDataEvent ( self, event: proto.SendDataEvent ) -> None:
		log = logger.getChild ( 'Server.on_SendDataEvent' )
		for chunk in event.chunks:
			log.debug ( f'S>{b2s(chunk).rstrip()}' )
			self._write ( chunk )
	
	def _run ( self, tls: bool ) -> None:
		log = logger.getChild ( 'Server._run' )
		try:
			srv = proto.Server ( self.hostname, tls )
			
			for event in srv.startup():
				self._on_event ( event )
			
			while True:
				try:
					data = self._read()
				except OSError as e: # TODO FIXME: more specific exception?
					raise proto.Closed ( repr ( e ) ) from e
				log.debug ( f'C>{b2s(data).rstrip()}' )
				for event in srv.receive ( data ):
					self._on_event ( event )
		except proto.Closed as e:
			log.debug ( f'connection closed with reason: {e.args[0]!r}' )
		finally:
			self.close()
