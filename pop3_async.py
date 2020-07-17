# system imports:
from abc import abstractmethod
import email.utils
import logging
import sys
from typing import Iterator, Optional as Opt

# email_proto imports:
from event_handling import AsyncClient, AsyncServer
from transport import AsyncTransport
import pop3_proto as proto
from util import b2s

logger = logging.getLogger ( __name__ )


class Client ( AsyncClient ):
	protocls = proto.Client
	
	async def greeting ( self ) -> proto.GreetingResponse:
		return await self._request ( proto.GreetingRequest() )
	
	async def capa ( self ) -> proto.CapaResponse:
		#log = logger.getChild ( 'Client.capa' )
		return await self._request ( proto.CapaRequest() )
	
	async def apop ( self, uid: str, pwd: str, challenge: str ) -> proto.SuccessResponse:
		return await self._request ( proto.ApopRequest ( uid, pwd, challenge ) )
	
	async def starttls ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.StartTlsRequest() )
	
	async def rset ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.RsetRequest() )
	
	async def noop ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.NoOpRequest() )
	
	async def quit ( self ) -> proto.SuccessResponse:
		return await self._request ( proto.QuitRequest() )
	
	async def on_ApopChallengeEvent ( self, event: proto.ApopChallengeEvent ) -> None:
		event.accept (
			email.utils.make_msgid ( self.server_hostname ) # this is slooooowwwww, probably should generate my own
		)
	
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		await self.transport.starttls_client ( self.server_hostname )


class Server ( AsyncServer ):
	protocls = proto.Server
	
	async def on_GreetingAcceptEvent ( self, event: proto.GreetingAcceptEvent ) -> None:
		# implementations only need to override this if they want to change the behavior
		event.accept()
	
	@abstractmethod
	async def on_StartTlsAcceptEvent ( self, event: proto.StartTlsAcceptEvent ) -> None: # pragma: no cover
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.on_StartTlsAcceptEvent()' )
	
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		self.transport.starttls_server()
