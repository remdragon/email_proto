# email_proto

email_proto is a Python library that provides sans i/o implementations of email protocols.

It also provides reference implementations with i/o.

## Installation

Download from [here](https://github.com/remdragon/email_proto)?

**NOTE**: The unittests require that you install all supported async i/o backends `pip install anyio curio trio`, but these aren't dependencies of this project itself, only if you want to use those i/o backends.

(Hopefully this can get hosted on pip someday)

## Usage

```python
import getpass
import from email_proto.smtp_socket import Client # reference synchronous sockets implementation

client = Client()
client.connect ( 'smtp.yourdomain.com', 465, tls = True )
client.helo ( 'localhost' )
client.auth ( 'zaphod@beeblebrox.com', getpass.getpass ( 'Password:' ) )
client.mail_from ( 'zaphod@beeblebrox.com' )
client.rcpt_to ( 'ford@prefect.com' )
client.data ( b'(email content here)' )
client.quit()
```

## Files

* `__init__`.py: only defines project version
* `smtp_proto.py`: SMTP protocol implementation sans i/o
* `smtp_sync.py`: reference sync wrapper of `smtp_proto.py`
* `smtp_async.py`: reference async wrapper of `smtp_proto.py`
* `smtp_socket.py`: reference sync implementation of `smtp_sync.py` using `socket.socket`
* `smtp_aio.py`: reference async implementation of `smtp_async.py` using `asyncio.StreamReader`/`asyncio.StreamWriter`
* `smtp_trio.py`: reference async implementation of `symtp-async.py` using `trio.abc.Stream`
* `*_test.py`: unit tests
* `test.*`: tools to make running the tests easier

## TODO

STARTTLS implementation in asyncio is WIP. It is untested and feels dirty.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)

## Version History

* 0.1.0 - smtp_proto.py 100% code coverage via unittests
* 0.0.9 - smtp believed feature complete with respect to "minimum" required implementation as defined by RFC.
* 0.0.1 - initial design & development

## Roadmap

* 0.2.0 - pop3 protocol 100% code coverage via unittests
* 0.4.0 - imap protocol 100% code coverage via unittests
* 1.0 - stable api
