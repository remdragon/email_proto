# email_proto

email_proto is a Python library that provides sans i/o implementations of email protocols.

It also provides reference implementations with i/o.

## Installation

Download from [here](https://github.com/remdragon/email_proto)?

**NOTE**: The reference trio implementation requires that you install trio `pip install trio`, but this isn't a strict dependency, in case you want to use a different i/o backend.

(Hopefully this can get hosted on pip someday)

## Usage

```python
import getpass
import from email_proto.smtp_socket import Client # reference synchronous sockets implementation

client = Client()
client.connect ( 'smtp.yourdomain.com', 465 )
client.helo ( 'localhost' )
client.auth ( 'zaphod@beeblebrox.com', getpass.getpass ( 'Password:' ) )
client.mail_from ( 'zaphod@beeblebrox.com' )
client.rcpt_to ( 'ford@prefect.com' )
client.data ( b'(email content here)' )
client.quit()
```

## Files

* `smtp_proto.py`: SMTP protocol implementation sans i/o
* `smtp_sync.py`: reference sync wrapper of `smtp_proto.py`
* `smtp_async.py`: reference async wrapper of `smtp_proto.py`
* `smtp_socket.py`: reference sync implementation of `smtp_sync.py` using `socket.socket`
* `smtp_aio.py`: reference async implementation of `smtp_async.py` using `asyncio.StreamReader`/`asyncio.StreamWriter`
* `smtp_trio.py`: reference async implementation of `symtp-async.py` using `trio.abc.Stream`
* `*_test.py`: unit tests
* `test.*`: tools to make running the tests easier

## TODO

POP3 and IMAP are planned after SMTP implementation is a little more flushed out.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)
