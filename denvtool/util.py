
class AttrMap:
    def __init__(self, d):
        self._value_dict = d

    def __setattr__(self, key, value):
        if key != "_value_dict":
            self._value_dict[key] = value
        else:
            super().__setattr__(key, value)

    def __getattr__(self, key):
        try:
            return self._value_dict[key]
        except KeyError:
            raise AttributeError()

    def __getitem__(self, key):
        return self._value_dict[key]

    def __setitem__(self, key, value):
        self._value_dict[key] = value

    def filter(self, lam):
        return AttrMap({ k : v for k, v in self.items() if lam(k, v) })

    def keys(self):
        return self._value_dict.keys()

    def values(self):
        return self._value_dict.values()

    def items(self):
        return self._value_dict.items()

    def __repr__(self):
        return self._value_dict.__repr__()

    def __str__(self):
        return self._value_dict.__str__()

    @staticmethod
    def make_recursive(d):
        if isinstance(d, dict):
            d = { k : AttrMap.make_recursive(v) for k, v in d.items() }
            return AttrMap(d)
        elif isinstance(d, list):
            return list([AttrMap.make_recursive(v) for v in d])
        elif isinstance(d, tuple):
            return tuple(AttrMap.make_recursive(v) for v in d)
        else:
            return d
