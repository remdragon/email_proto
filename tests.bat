@cls
@rem coverage run --rcfile=%DROPBOX%\cover%PY%.rc --branch tests.py && coverage report -m
@coverage run --branch tests.py && coverage report -m
@del .coverage