from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import logging
import trio # pip install trio trio-typing

# mail_proto imports:
import smtp
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
	
	async def connect ( self, hostname: str, port: int ) -> None:
		self.stream = await trio.open_tcp_stream ( hostname, port,
			happy_eyeballs_delay = happy_eyeballs_delay,
		)
		await self._connect()


class Server ( Transport, smtp_async.Server ):
	
	async def run ( self, stream: trio.abc.Stream ) -> None:
		self.stream = stream
		await self._run()
