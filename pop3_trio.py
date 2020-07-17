from __future__ import annotations

# python imports:
import trio # pip install trio trio-typing
from typing import Type

# mail_proto imports:
import pop3_proto as proto
import pop3_async
from transport_trio import TrioTransport as Transport

class Client ( pop3_async.Client ):
	@classmethod
	async def connect ( cls: Type[Client],
		hostname: str,
		port: int,
		tls: bool,
	) -> Client:
		transport = await Transport.connect ( hostname, port, tls )
		return cls ( transport, tls, hostname )

class Server ( pop3_async.Server ):
	@classmethod
	def from_stream ( cls: Type[Server],
		stream: trio.abc.Stream,
		tls: bool,
		server_hostname: str,
	) -> Server:
		transport = Transport ( stream )
		return cls ( transport, tls, server_hostname )
