from __future__ import annotations

# python imports:
import trio # pip install trio trio-typing
from typing import Type

# mail_proto imports:
import smtp_proto as proto
import smtp_async
from transport_trio import TrioTransport as Transport

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
		stream: trio.abc.Stream,
		tls: bool,
		server_hostname: str,
	) -> Server:
		transport = Transport ( stream )
		return cls ( transport, tls, server_hostname )
