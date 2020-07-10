import trustme # pip install trustme
import ssl

class ServerOnly:
	def __init__ ( self, *,
		server_hostname: str, # ex: 'test-host.example.org'
	) -> None:
		self.server_hostname = server_hostname
		self.ca = trustme.CA()
		self.server_cert = self.ca.issue_cert ( self.server_hostname )
	
	def server_context ( self ) -> ssl.SSLContext:
		ctx = ssl.create_default_context()
		ctx.check_hostname = False
		self.server_cert.configure_cert ( ctx )
		self.ca.configure_trust ( ctx )
		ctx.verify_mode = ssl.CERT_NONE
		return ctx
	
	def client_context ( self ) -> ssl.SSLContext:
		ctx = ssl.create_default_context()
		self.ca.configure_trust ( ctx )
		return ctx

class ClientServer:
	def __init__ ( self, *,
		client_hostname: str, # ex: 'client@example.org'
		server_hostname: str, # ex: 'test-host.example.org'
	) -> None:
		self.client_hostname = client_hostname
		self.server_hostname = server_hostname
		self.ca = trustme.CA()
		self.client_cert = self.ca.issue_cert ( self.client_hostname )
		self.server_cert = self.ca.issue_cert ( self.server_hostname )
	
	def server_context ( self ) -> ssl.SSLContext:
		ctx = ssl.create_default_context ( ssl.Purpose.CLIENT_AUTH )
		self.server_cert.configure_cert ( ctx )
		self.ca.configure_trust ( ctx )
		ctx.verify_mode = ssl.CERT_REQUIRED
		return ctx
	
	def client_context ( self ) -> ssl.SSLContext:
		ctx = ssl.create_default_context()
		self.ca.configure_trust ( ctx )
		self.client_cert.configure_cert ( ctx )
		return ctx
