from __future__ import annotations

# python imports:
import asyncio
from typing import Type

# mail_proto imports:
import smtp_proto as proto
import smtp_async
from transport_aio import AsyncioTransport as Transport

class Client ( smtp_async.Client ):
	@classmethod
	async def connect ( cls: Type[Client],
		hostname: str,
		port: int,
		tls: bool,
	) -> Client:
		transport = await Transport.connect ( hostname, port, tls )
		return cls ( transport, tls, hostname )

class Server ( smtp_async.Server ):
	@classmethod
	def from_stream ( cls: Type[Server],
		rx: asyncio.StreamReader,
		tx: asyncio.StreamWriter,
		tls: bool,
		server_hostname: str,
	) -> Server:
		transport = Transport ( rx, tx )
		return cls ( transport, tls, server_hostname )
