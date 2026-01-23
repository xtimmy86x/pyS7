# Performance Analysis & Optimization Report

## Executive Summary

Performance profiling del pyS7 library ha identificato le seguenti metriche baseline e aree di ottimizzazione.

## Benchmark Results (Baseline)

| Operation | Time (s) | Ops/sec | Notes |
|-----------|----------|---------|-------|
| **Tag Creation** (10k) | 0.317 | 31,594 | Creazione di 4 tag per iterazione |
| **Tag Size** (10k) | 0.022 | 449,716 | Calcolo dimensione tag |
| **Tag Containment** (10k) | 0.021 | 480,114 | Check contenimento tag |
| **Single Request** (1k) | 0.003 | 391,312 | Preparazione richiesta singola |
| **Multiple Requests** (1k) | 0.103 | 9,756 | Preparazione 50 tag |
| **Write Requests** (1k) | 0.037 | 26,755 | Preparazione write per 20 tag |

## Bottleneck Analysis

### 1. Tag Creation (31.6% del tempo totale)

**Profiling Details:**
```
Cumulative Time Distribution:
- __post_init__: 80.5% (validation)
- _ensure_instance: 24.4% (240k calls)
- _validate_bit_offset: 13.0%
- _validate_db_number: 12.3%
- _validate_start: 11.3%
- _validate_length: 11.0%
```

**Bottlenecks Identificati:**
1. `_ensure_instance()` chiamato 6 volte per ogni tag (240k su 40k tags)
2. Ogni validazione è una chiamata separata con overhead
3. `isinstance()` chiamato 240k volte

**Ottimizzazioni Proposte:**

#### Opzione A: Caching dei tipi (Impatto: -15-20%)
```python
# Invece di:
def _ensure_instance(self, value: Any, expected_type: type, field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise ValueError(...)

# Usare @lru_cache o pre-computed type checks
from functools import lru_cache

@lru_cache(maxsize=128)
def _check_type(value_type: type, expected_type: type) -> bool:
    return issubclass(value_type, expected_type)
```

#### Opzione B: Validation batching (Impatto: -25-30%)
```python
def __post_init__(self) -> None:
    # Raccolta errori invece di fail-fast
    errors = []
    
    if not isinstance(self.memory_area, MemoryArea):
        errors.append(f"memory_area must be MemoryArea, got {type(self.memory_area)}")
    if not isinstance(self.data_type, DataType):
        errors.append(f"data_type must be DataType, got {type(self.data_type)}")
    # ... altri check
    
    if errors:
        raise ValueError("; ".join(errors))
```

#### Opzione C: __slots__ per ridurre memoria (Impatto: -10-15% memoria, +5% speed)
```python
@dataclass
class S7Tag:
    __slots__ = ('memory_area', 'db_number', 'data_type', 'start', 'bit_offset', 'length')
    memory_area: MemoryArea
    db_number: int
    # ...
```

### 2. Tag Size Calculation (4.5% del tempo)

**Profiling:**
```
40k calls, 0.022s total
- enum.__hash__: 36% (30k calls per hashing in switch-like logic)
```

**Bottleneck:** Hash di enum per switch/case su DataType

**Ottimizzazione Proposta:**

#### Pre-computed size lookup (Impatto: -40-50%)
```python
# Invece di if/elif chain nel size():
_SIZE_LOOKUP = {
    DataType.BIT: lambda length: 1,
    DataType.BYTE: lambda length: length,
    DataType.CHAR: lambda length: length,
    DataType.INT: lambda length: length * 2,
    DataType.WORD: lambda length: length * 2,
    DataType.DINT: lambda length: length * 4,
    DataType.DWORD: lambda length: length * 4,
    DataType.REAL: lambda length: length * 4,
    DataType.LREAL: lambda length: length * 8,
    DataType.STRING: lambda length: length + 2,
    DataType.WSTRING: lambda length: length * 2 + 4,
}

def size(self) -> int:
    return _SIZE_LOOKUP[self.data_type](self.length)
```

### 3. Prepare Multiple Requests (20.9% del tempo)

**Profiling:**
```
1k iterations con 50 tags = 0.103s
- prepare_requests: 36%
- tag.size(): 53% (100k calls - 2x per tag!)
- enum.__hash__: 25%
```

**Bottleneck:** `tag.size()` chiamato 2 volte per ogni tag (100k invece di 50k)

**Ottimizzazione:**

#### Caching del size() (Impatto: -35-40%)
```python
@dataclass
class S7Tag:
    # ...
    _cached_size: int = field(default=None, init=False, repr=False)
    
    def size(self) -> int:
        if self._cached_size is None:
            self._cached_size = self._calculate_size()
        return self._cached_size
    
    def _calculate_size(self) -> int:
        # Logica attuale di size()
        ...
```

#### Riduzione chiamate size() in prepare_requests (Impatto: -20%)
```python
# In requests.py, line ~495:
for tag in tags:
    tag_size = tag.size()  # Calcola una sola volta
    tag_request_size = READ_REQ_PARAM_SIZE_TAG
    tag_response_size = READ_RES_PARAM_SIZE_TAG + tag_size  # Usa cached
    # ... resto della logica
```

### 4. Write Requests (7.6% del tempo)

**Profiling:** Simile a prepare_requests, stesso overhead di size()

**Ottimizzazione:** Stesse ottimizzazioni del punto 3

## Ottimizzazioni Prioritizzate

### Priority 1: Immediate Impact (Effort: Low, Gain: High)

1. **Cache tag.size()** 
   - Impatto: -35-40% su prepare_requests
   - Effort: 30 minuti
   - Rischio: Basso

2. **Pre-computed size lookup**
   - Impatto: -40-50% su size()
   - Effort: 1 ora
   - Rischio: Basso

3. **Riduzione chiamate duplicate size()**
   - Impatto: -20% su prepare_requests
   - Effort: 30 minuti
   - Rischio: Molto basso

### Priority 2: Medium Impact (Effort: Medium, Gain: Medium)

4. **Validation batching**
   - Impatto: -25-30% su tag creation
   - Effort: 2-3 ore
   - Rischio: Medio (cambia API errori)

5. **__slots__ per S7Tag**
   - Impatto: -10-15% memoria, +5% speed
   - Effort: 1 ora
   - Rischio: Medio (compatibilità)

### Priority 3: Advanced Optimization (Effort: High, Gain: Variable)

6. **Type check caching**
   - Impatto: -15-20% su validation
   - Effort: 2 ore
   - Rischio: Medio

7. **Enum comparison optimization**
   - Impatto: -10-15% generale
   - Effort: 3-4 ore
   - Rischio: Alto

## Estimated Total Impact

Implementando Priority 1 (3 ottimizzazioni):
- **Tag Creation:** ~10% faster
- **Prepare Multiple Requests:** ~50% faster (da 0.103s a 0.05s)
- **Write Requests:** ~45% faster (da 0.037s a 0.02s)
- **Overall Throughput:** ~35-40% improvement

## Memory Profile

Attuale footprint per S7Tag:
- Instance: ~200-250 bytes (dataclass overhead)
- Con __slots__: ~100-120 bytes (-50%)

Per applicazioni con 10k+ tags contemporanei: saving di ~1.2MB

## Recommendations

1. **Implementare Priority 1 subito** - ROI immediato, basso rischio
2. **Benchmark dopo ogni ottimizzazione** - Validare impatto reale
3. **Considerare Priority 2** solo se necessario (>100k tags/sec)
4. **Evitare Priority 3** a meno di requisiti estremi

## Next Steps

1. Creare branch `feature/performance-opt`
2. Implementare cache size() + lookup table
3. Ridurre chiamate duplicate
4. Benchmark comparativo
5. Se gain >30%, procedere con merge
6. Documentare in CHANGELOG

## Appendix: Test Environment

- CPU: Standard PC (specifics TBD)
- Python: 3.13.7
- OS: Linux
- pyS7 version: Development (post 10 improvements)
