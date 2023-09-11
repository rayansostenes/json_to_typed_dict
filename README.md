# JSON to TypedDict

Converts a stream of json data into TypedDict definitions

## Usage

```bash
$ cat example.jsonl | ./json2type.py
```

Running the example above and assuming the following jsonl file:

```json
[{"limit": 0, "price": 0, "value": "", "excess": "No", "coverage": "do", "retention": 0, "bundled_with": "mpl"}]
[{"limit": 0, "price": 0, "value": "", "excess": "Yes", "coverage": "epli", "retention": 0, "bundled_with": "crm"}]
[{"limit": 0, "price": 0, "value": "", "excess": "Yes", "coverage": "fiduciary", "retention": 0, "bundled_with": "epli"}]
[{"limit": 100000, "price": 2000, "value": "", "excess": "No", "coverage": "do", "retention": 2000000, "bundled_with": "Other"}]
[]
[]
```

The following output will be generated:

```python
import typing as t

class RootDict(t.TypedDict):
    limit: int
    price: int
    value: t.Literal['']
    excess: t.Literal['No', 'Yes']
    coverage: t.Literal['do', 'fiduciary', 'epli']
    retention: int
    bundled_with: t.Literal['Other', 'epli', 'crm', 'mpl']

RootType = list[RootDict]
```
