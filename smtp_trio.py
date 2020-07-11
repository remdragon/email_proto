from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import ssl
import trio # pip install trio trio-typing

# mail_proto imports:
import smtp_proto
import smtp_async

logger = logging.getLogger ( __name__ )

happy_eyeballs_delay: float = 0.25 # this is the same as trio's default circa version 0.16.0


class Transport:
	stream: trio.abc.Stream
	
	async def _read ( self ) -> bytes:
		#log = logger.getChild ( 'Transport._read' )
		return await self.stream.receive_some()
	
	async def _write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'Transport._write' )
		await self.stream.send_all ( data )
	
	async def _close ( self ) -> None:
		await self.stream.aclose()


class Client ( Transport, smtp_async.Client ):
	server_hostname: Opt[str] = None
	ssl_context: Opt[ssl.SSLContext] = None
	
	async def connect ( self, hostname: str, port: int ) -> None:
		self.server_hostname = hostname
		try:
			self.stream = await trio.open_tcp_stream ( hostname, port,
				happy_eyeballs_delay = happy_eyeballs_delay,
			)
		except Exception as e:
			log.warning ( f'Error connecting to {address=}: {e!r}' )
		else:
			await self._connect()
	
	async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Client.on_starttls_begin' )
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context ( ssl.Purpose.SERVER_AUTH )
		self.stream = trio.SSLStream (
			self.stream,
			ssl_context = self.ssl_context,
			server_hostname = self.server_hostname,
		)


class Server ( Transport, smtp_async.Server ):
	ssl_context: Opt[ssl.SSLContext] = None
	
	async def run ( self, stream: trio.abc.Stream ) -> None:
		self.stream = stream
		await self._run()
	
	async def on_starttls_begin ( self, event: smtp_proto.StartTlsBeginEvent ) -> None:
		#log = logger.getChild ( 'Server.on_starttls_begin' )
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context()
			self.ssl_context.verify_mode = ssl.CERT_NONE
		self.stream = trio.SSLStream (
			self.stream,
			ssl_context = self.ssl_context,
			server_side = True,
		)
