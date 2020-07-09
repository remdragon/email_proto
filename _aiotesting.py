from __future__ import annotations

from abc import ABCMeta, abstractmethod
import asyncio
import logging
from typing import List, Optional as Opt, Tuple

logger = logging.getLogger ( __name__ )

class _Event ( metaclass = ABCMeta ):
	@abstractmethod
	def get_data ( self, limit: Opt[int] = None ) -> bytes: # pragma: no cover
		raise NotImplementedError

class _DataEvent ( _Event ):
	def __init__ ( self, data: bytes ) -> None:
		self.data = data
	
	def get_data ( self, limit: Opt[int] = None ) -> bytes:
		#log = logger.getChild ( '_DataEvent.get_data' )
		if limit is None:
			b, self.data = self.data, b''
		else:
			b, self.data = self.data[:limit], self.data[limit:]
		return b

class _CloseEvent ( _Event ):
	def get_data ( self, limit: Opt[int] = None ) -> bytes:
		raise EOFError()

class PipeStreamReader:
	_event: _Event
	
	def __init__ ( self, q: asyncio.Queue[_Event] ) -> None:
		self.q = q
		self._event = _DataEvent ( b'' ) # start with an empty event so logic is simpler below...
	
	async def read ( self, n: int = -1 ) -> bytes:
		datas: List[bytes] = []
		count = 0
		while -1 == n or count < n:
			max_needed = None if -1 == n else n - count
			try:
				data = self._event.get_data ( max_needed )
			except EOFError:
				if count:
					break
				raise
			if not data: # no data left in current event
				self._event = await self.q.get()
				continue
			count += len ( data )
			datas.append ( data )
		return b''.join ( datas )
	
	async def readline ( self, maxlen: int = 0 ) -> bytes:
		return await self.readuntil ( b'\n', maxlen )
	
	async def readuntil ( self,
		separator: bytes = b'\n',
		maxlen: int = 0,
	) -> bytes:
		datas: List[bytes] = [ b'' ]
		count = 0
		while -1 == ( eol := datas[-1].find ( separator ) ):
			if maxlen and count >= maxlen:
				eol = count - len ( separator )
				break
			try:
				data = self._event.get_data ( maxlen or None )
			except EOFError:
				raise asyncio.IncompleteReadError (
					b''.join ( datas ),
					f'(terminated by {separator!r})' # type: ignore
				) from None
			if not data:
				self._event = await self.q.get()
				continue
			count += len ( data )
			datas.append ( data )
		eol += len ( separator )
		data = b''.join ( datas )
		data, extra = data[:eol], data[eol:]
		if extra:
			assert isinstance ( self._event, _DataEvent )
			self._event = _DataEvent ( extra + self._event.get_data() )
		return data

class PipeStreamWriter:
	_buf: List[_Event]
	_is_closing: bool
	
	def __init__ ( self, q: asyncio.Queue[_Event] ) -> None:
		self.q = q
		self._buf = []
		self._is_closing = False
	
	def write ( self, data: bytes ) -> None:
		#log = logger.getChild ( 'PipeStreamWriter.write' )
		#log.debug ( f'{data=}' )
		assert not self._is_closing
		event = _DataEvent ( data )
		try:
			self.q.put_nowait ( event )
			#log.debug ( 'put_nowait() successful' )
		except asyncio.QueueFull:
			self._buf.append ( event )
			#log.debug ( f'{self._buf=}' )
	
	async def drain ( self ) -> None:
		#log = logger.getChild ( 'PipeStreamWriter.write' )
		#log.debug ( f'{len(self._buf)=}' )
		for event in self._buf:
			self.q.put ( event )
		self._buf = []
	
	def close ( self ) -> None:
		#log = logger.getChild ( 'PipeStreamWriter.close' )
		self._is_closing = True
		event = _CloseEvent()
		try:
			self.q.put_nowait ( event )
		except asyncio.QueueFull:
			self._buf.append ( event )
	
	def is_closing ( self ) -> bool:
		return self._is_closing
	
	async def wait_closed ( self ) -> None:
		for event in self._buf:
			self.q.put ( event )
		del self._buf

def open_pipe_stream() -> Tuple[asyncio.StreamReader,asyncio.StreamWriter]:
	q: asyncio.Queue[_Event] = asyncio.Queue()
	rx = PipeStreamReader ( q )
	tx = PipeStreamWriter ( q )
	return rx, tx # type: ignore # yes I know they aren't *real* StreamReader/StreamWriter objects
