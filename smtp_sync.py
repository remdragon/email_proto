# system imports:
from abc import abstractmethod
import logging
import sys

# email_proto imports:
from event_handling import SyncClient, SyncServer
import smtp_proto as proto
from transport import SyncTransport
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( SyncClient ):
	protocls = proto.Client
	
	def greeting ( self ) -> proto.SuccessResponse:
		return self._request ( proto.GreetingRequest() )
	
	def helo ( self, local_hostname: str ) -> proto.SuccessResponse:
		return self._request ( proto.HeloRequest ( local_hostname ) )
	
	def ehlo ( self, local_hostname: str ) -> proto.EhloResponse:
		return self._request ( proto.EhloRequest ( local_hostname ) )
	
	def starttls ( self ) -> proto.SuccessResponse:
		return self._request ( proto.StartTlsRequest() )
	
	def auth_plain1 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return self._request ( proto.AuthPlain1Request ( uid, pwd ) )
	
	def auth_plain2 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return self._request ( proto.AuthPlain2Request ( uid, pwd ) )
	
	def auth_login ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return self._request ( proto.AuthLoginRequest ( uid, pwd ) )
	
	def expn ( self, mailbox: str ) -> proto.ExpnResponse:
		return self._request ( proto.ExpnRequest ( mailbox ) )
	
	def vrfy ( self, mailbox: str ) -> proto.VrfyResponse:
		return self._request ( proto.VrfyRequest ( mailbox ) )
	
	def mail_from ( self, email: str ) -> proto.SuccessResponse:
		return self._request ( proto.MailFromRequest ( email ) )
	
	def rcpt_to ( self, email: str ) -> proto.SuccessResponse:
		return self._request ( proto.RcptToRequest ( email ) )
	
	def data ( self, content: bytes ) -> proto.SuccessResponse:
		return self._request ( proto.DataRequest ( content ) )
	
	def rset ( self ) -> proto.SuccessResponse:
		return self._request ( proto.RsetRequest() )
	
	def noop ( self ) -> proto.SuccessResponse:
		return self._request ( proto.NoOpRequest() )
	
	def quit ( self ) -> proto.SuccessResponse:
		return self._request ( proto.QuitRequest() )
	
	def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		self.transport.starttls_client ( self.server_hostname )


class Server ( SyncServer ):
	protocls = proto.Server
	
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
	
	def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None: # pragma: no cover
		self.transport.starttls_server()
	
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
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_CompleteEvent()' )
