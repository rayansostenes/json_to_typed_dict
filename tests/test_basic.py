from contextlib import redirect_stdout
from io import StringIO
import sys
from json2type import main


def test_basic_type_generation():
    with open("tests/test_data/test_1.jsonl") as f:
        generated = StringIO()
        sys.stdin = f
        with redirect_stdout(generated):
            main()
        with open("tests/test_data/test_1.py") as f:
            expected = f.read()
        assert generated.getvalue() == expected
