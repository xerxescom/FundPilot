from abc import ABC, abstractmethod


class AIClient(ABC):
    model_name: str = "unknown"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError
