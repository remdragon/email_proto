from __future__ import annotations

# system imports:
from abc import ABCMeta, abstractmethod
import asyncio
import logging

# mail_proto imports:
import smtp_proto
import smtp_async

logger = logging.getLogger ( __name__ )


class Transport:
	rx: asyncio.StreamReader
	tx: asyncio.StreamWriter
	
	async def _read ( self ) -> bytes:
		#log = logger.getChild ( 'Transport._read' )
		return await self.rx.readline()
	
	async def _write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'Transport._write' )
		self.tx.write ( data );
		await self.tx.drain()
	
	async def _close ( self ) -> None:
		self.tx.close()
		await self.tx.wait_closed()


class Client ( Transport, smtp_async.Client ):
	
	async def connect ( self, hostname: str, port: int ) -> None:
		self.rx, self.tx = await asyncio.open_connection ( hostname, port )
		await self._connect()


class Server ( Transport, smtp_async.Server ):
	
	async def run ( self,
		rx: asyncio.StreamReader,
		tx: asyncio.StreamWriter,
	) -> None:
		self.rx = rx
		self.tx = tx
		await self._run()
