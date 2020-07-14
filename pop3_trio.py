from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import ssl
import trio # pip install trio trio-typing
from typing import Optional as Opt

# mail_proto imports:
import pop3_proto as proto
import pop3_async as base

logger = logging.getLogger ( __name__ )

happy_eyeballs_delay: float = 0.25 # this is the same as trio's default circa version 0.16.0


class Transport:
	stream: trio.abc.Stream
	
	async def _read ( self ) -> bytes:
		#log = logger.getChild ( 'Transport._read' )
		with trio.move_on_after ( 1.0 ): # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			return await self.stream.receive_some()
		raise TimeoutError ( f'{type(self).__module__}.{type(self).__name__} timeout waiting to read data' )
	
	async def _write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'Transport._write' )
		with trio.move_on_after ( 1.0 ): # TODO FIXME: configurable timeout (this value is only for testing) and better error handling
			await self.stream.send_all ( data )
			return
		raise TimeoutError ( f'{type(self).__module__}.{type(self).__name__} timeout waiting to write {bytes(data)=}' )
	
	async def close ( self ) -> None:
		#log = logger.getChild ( 'Transport.close' )
		with trio.move_on_after ( 0.05 ):
			await self.stream.aclose() # TODO FIXME: why sometimes getting hung up when in ssl?


class Client ( Transport, base.Client ):
	server_hostname: Opt[str] = None
	ssl_context: Opt[ssl.SSLContext] = None
	
	async def connect ( self, hostname: str, port: int, tls: bool ) -> None:
		log = logger.getChild ( 'Client.connect' )
		self.server_hostname = hostname
		self.stream = await trio.open_tcp_stream ( hostname, port,
			happy_eyeballs_delay = happy_eyeballs_delay,
		)
		if tls:
			self._wrap_ssl()
		await self._connect ( tls )
	
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Client.on_StartTlsBeginEvent' )
		self._wrap_ssl()
	
	def _wrap_ssl ( self ) -> None:
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context ( ssl.Purpose.SERVER_AUTH )
		self.stream = trio.SSLStream (
			self.stream,
			ssl_context = self.ssl_context,
			server_hostname = self.server_hostname,
		)


class Server ( Transport, base.Server ):
	ssl_context: Opt[ssl.SSLContext] = None
	
	async def run ( self, stream: trio.abc.Stream, tls: bool, apop_challenge: Opt[str] = None ) -> None:
		self.stream = stream
		await self._run ( tls, apop_challenge )
	
	async def on_StartTlsBeginEvent ( self, event: proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Server.on_StartTlsBeginEvent' )
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context()
			self.ssl_context.verify_mode = ssl.CERT_NONE
		self.stream = trio.SSLStream (
			self.stream,
			ssl_context = self.ssl_context,
			server_side = True,
		)
