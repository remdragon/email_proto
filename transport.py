# python imports:
from abc import ABCMeta, abstractmethod
import logging
import ssl
import sys
from typing import Optional as Opt

# email_proto imports:
from util import BYTES

logger = logging.getLogger ( __name__ )


class Transport ( metaclass = ABCMeta ):
	ssl_context: Opt[ssl.SSLContext] = None
	
	def ssl_context_or_default_client ( self ) -> ssl.SSLContext:
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context ( ssl.Purpose.SERVER_AUTH )
		return self.ssl_context
	
	def ssl_context_or_default_server ( self ) -> ssl.SSLContext:
		if self.ssl_context is None:
			self.ssl_context = ssl.create_default_context()
			self.ssl_context.verify_mode = ssl.CERT_NONE
		return self.ssl_context


class SyncTransport ( Transport ):
	@abstractmethod
	def read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.read()' )
	
	@abstractmethod
	def write ( self, data: BYTES ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.write()' )
	
	@abstractmethod
	def starttls_client ( self, server_hostname: str ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.starttls_client()' )
	
	@abstractmethod
	def starttls_server ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.starttls_server()' )
	
	@abstractmethod
	def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )


class AsyncTransport ( Transport ):
	@abstractmethod
	async def read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.read()' )
	
	@abstractmethod
	async def write ( self, data: BYTES ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.write()' )
	
	@abstractmethod
	async def starttls_client ( self, server_hostname: str ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.starttls_client()' )
	
	@abstractmethod
	async def starttls_server ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.starttls_server()' )
	
	@abstractmethod
	async def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )
