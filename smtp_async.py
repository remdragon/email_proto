# system imports:
from abc import abstractmethod
import logging
import sys

# email_proto imports:
from event_handling import AsyncClient, AsyncServer
import smtp_proto as proto
from transport import AsyncTransport
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( AsyncClient ):
	protocls = proto.Client
	
	async def greeting ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.GreetingRequest() )
	
	async def helo ( self, local_hostname: str ) -> proto.SuccessResponse:
		return await self._request ( proto.HeloRequest ( local_hostname ) )
	
	async def ehlo ( self, local_hostname: str ) -> proto.EhloResponse:
		return await self._request ( proto.EhloRequest ( local_hostname ) )
	
	async def starttls ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.StartTlsRequest() )
	
	async def auth_plain1 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return await self._request ( proto.AuthPlain1Request ( uid, pwd ) )
	
	async def auth_plain2 ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return await self._request ( proto.AuthPlain2Request ( uid, pwd ) )
	
	async def auth_login ( self, uid: str, pwd: str ) -> proto.SuccessResponse:
		return await self._request ( proto.AuthLoginRequest ( uid, pwd ) )
	
	async def expn ( self, mailbox: str ) -> proto.ExpnResponse:
		return await self._request ( proto.ExpnRequest ( mailbox ) )
	
	async def vrfy ( self, mailbox: str ) -> proto.VrfyResponse:
		return await self._request ( proto.VrfyRequest ( mailbox ) )
	
	async def mail_from ( self, email: str ) -> proto.SuccessResponse:
		return await self._request ( proto.MailFromRequest ( email ) )
	
	async def rcpt_to ( self, email: str ) -> proto.SuccessResponse:
		return await self._request ( proto.RcptToRequest ( email ) )
	
	async def data ( self, content: bytes ) -> proto.SuccessResponse:
		return await self._request ( proto.DataRequest ( content ) )
	
	async def rset ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.RsetRequest() )
	
	async def noop ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.NoOpRequest() )
	
	async def quit ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.QuitRequest() )
	
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		await self.transport.starttls_client ( self.server_hostname )


class Server ( AsyncServer ):
	protocls = proto.Server
	
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
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsAcceptEvent()' )
	
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		await self.transport.starttls_server()
	
	@abstractmethod
	async def on_AuthEvent ( self, event: proto.AuthEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_AuthEvent()' )
	
	async def on_ExpnEvent ( self, event: proto.ExpnEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	async def on_VrfyEvent ( self, event: proto.VrfyEvent ) -> None:
		event.reject() # NOTE: it isn't required to implement this. The default behavior is to report '550 Access Denied!'
	
	@abstractmethod
	async def on_MailFromEvent ( self, event: proto.MailFromEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_MailFromEvent()' )
	
	@abstractmethod
	async def on_RcptToEvent ( self, event: proto.RcptToEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_RcptToEvent()' )
	
	@abstractmethod
	async def on_CompleteEvent ( self, event: proto.CompleteEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_CompleteEvent()' )
