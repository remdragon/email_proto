# python imports:
from abc import ABCMeta, abstractmethod
import logging
import sys
from typing import Generic, TypeVar

# email_proto imports:
from util import BYTES

logger = logging.getLogger ( __name__ )

T = TypeVar ( 'T' )


class Transport ( metaclass = ABCMeta ):
	@abstractmethod
	async def _read ( self ) -> bytes:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._read()' )
	
	@abstractmethod
	async def _write ( self, data: BYTES ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}._write()' )
	
	@abstractmethod
	async def close ( self ) -> None:
		cls = type ( self )
		raise NotImplementedError ( f'{cls.__module__}.{cls.__name__}.close()' )


class SyncTransport ( Generic[T] ):
	def _on_event ( self, event: T ) -> None:
		log = logger.getChild ( 'SyncTransport._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			func ( event )
		except Exception:
			event.exc_info = sys.exc_info()


class AsyncTransport ( Generic[T] ):
	async def _on_event ( self, event: T ) -> None:
		log = logger.getChild ( 'AsyncTransport._on_event' )
		try:
			func = getattr ( self, f'on_{type(event).__name__}' )
			await func ( event )
		except Exception:
			event.exc_info = sys.exc_info()
