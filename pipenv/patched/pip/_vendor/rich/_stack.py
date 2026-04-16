from typing import List, TypeVar

T = TypeVar("T")


class Stack(List[T]):
    """A small shim over builtin list."""

    @property
    def top(self) -> T:
        """Get top of stack."""
        pass

    def push(self, item: T) -> None:
        """Push an item on to the stack (append in stack nomenclature)."""
        self.append(item)
