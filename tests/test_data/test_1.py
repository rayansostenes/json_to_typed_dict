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