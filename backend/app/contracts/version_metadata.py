from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineVersionMetadata:
    '''Immutable identity and version metadata owned by a scoring engine.'''

    engine_id: str
    engine_version: str

    def __post_init__(self) -> None:
        self._validate_value('engine_id', self.engine_id)
        self._validate_value('engine_version', self.engine_version)

    @staticmethod
    def _validate_value(field_name: str, value: str) -> None:
        if type(value) is not str:
            raise TypeError(f'{field_name} must be str')
        if not value:
            raise ValueError(f'{field_name} must not be empty')
        if not value.strip():
            raise ValueError(f'{field_name} must not be whitespace-only')
        if value != value.strip():
            raise ValueError(
                f'{field_name} must not have leading or trailing whitespace'
            )
