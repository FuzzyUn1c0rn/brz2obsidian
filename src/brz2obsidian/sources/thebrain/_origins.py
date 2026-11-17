"""Private copied-character provenance for insert construction, never a diff."""


class CopiedText(str):
    def __new__(cls, value, origins=None):
        result = super().__new__(cls, value)
        result.origins = tuple(origins) if origins is not None else (None,) * len(value)
        return result

    def __getitem__(self, key):
        value = super().__getitem__(key)
        return CopiedText(value, self.origins[key]) if isinstance(key, slice) else value

    def __add__(self, other):
        return CopiedText(
            str(self) + str(other),
            self.origins + getattr(other, "origins", (None,) * len(other)),
        )

    def __radd__(self, other):
        return CopiedText(
            str(other) + str(self),
            getattr(other, "origins", (None,) * len(other)) + self.origins,
        )

    def lstrip(self, chars=None):
        return self[len(self) - len(str.lstrip(self, chars)) :]

    def rstrip(self, chars=None):
        return self[: len(str.rstrip(self, chars))]

    def strip(self, chars=None):
        return self.lstrip(chars).rstrip(chars)

    def splitlines(self, keepends=False):
        result, offset = [], 0
        for line in str.splitlines(self, keepends=True):
            content = line if keepends else line.splitlines()[0]
            result.append(self[offset : offset + len(content)])
            offset += len(line)
        return result


def copied_join(separator, pieces):
    result = CopiedText("")
    for index, piece in enumerate(pieces):
        result += (separator if index else "") + piece
    return result
