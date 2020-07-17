from __future__ import annotations

# python imports:
import socket
from typing import Type

# mail_proto imports:
import smtp_proto as proto
import smtp_sync
from transport_socket import SocketTransport as Transport

class Client ( smtp_sync.Client ):
	@classmethod
	def connect ( cls: Type[Client],
		hostname: str,
		port: int,
		tls: bool,
	) -> Client:
		transport = Transport.connect ( hostname, port, tls )
		return cls ( transport, tls, hostname )

class Server ( smtp_sync.Server ):
	@classmethod
	def from_stream ( cls: Type[Server],
		sock: socket.socket,
		tls: bool,
		server_hostname: str,
	) -> Server:
		transport = Transport ( sock )
		return cls ( transport, tls, server_hostname )
