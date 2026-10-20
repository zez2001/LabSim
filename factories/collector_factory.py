from typing import Dict, Type
from data_collectors.data_collector import DataCollector
from data_collectors.mock_collector import MockCollector
from data_collectors.action_state_collector import ActionStateDataCollector
from data_collectors.minimal_pick_collector import MinimalPickCollector

from data_collectors.minimal_precision_insertion_collector import MinimalPrecisionInsertionCollector

_collector_registry: Dict[str, Type[DataCollector]] = {}

def register_collector(name: str, collector_class: Type[DataCollector]):
    
    _collector_registry[name] = collector_class

def create_collector(collector_type: str, *args, **kwargs) -> DataCollector:
    
    if collector_type not in _collector_registry:
        raise ValueError(f": {collector_type}")
    return _collector_registry[collector_type](*args, **kwargs)


register_collector("default", DataCollector)
register_collector("mock", MockCollector)
register_collector("action_state", ActionStateDataCollector)
register_collector("minimal_pick", MinimalPickCollector)

register_collector("minimal_precision_insertion", MinimalPrecisionInsertionCollector)

from data_collectors.lab_cuvette_env_v1_collector import LabCuvetteEnvV1Collector
register_collector("lab_cuvette_env_v1", LabCuvetteEnvV1Collector)
