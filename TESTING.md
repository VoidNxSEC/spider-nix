# Testing Guide - Phase 1

## Quick Validation (No Dependencies)

Syntax checks (fast, no Nix needed):
```bash
python -m py_compile src/spider_nix/extraction/*.py
python -m py_compile src/spider_nix/ml/*.py
```

## Full Test Suite (Requires Nix Environment)

### Enter Nix Shell
```bash
nix develop
```

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Modules
```bash
# Extraction tests
pytest tests/extraction/ -v

# ML tests
pytest tests/ml/ -v

# With coverage
pytest tests/ --cov=spider_nix --cov-report=html
```

### Quick Import Test
```bash
nix develop --command python -c "
from spider_nix.extraction import BoundingBox, VisionExtractor, DOMAnalyzer, FusionEngine
from spider_nix.ml import FeedbackLogger, FailureClassifier, StrategySelector
print('✓ All imports successful')
"
```

## Module Structure

### Extraction (`src/spider_nix/extraction/`)
- `models.py` - BoundingBox, VisionDetection, DOMElement, FusedElement
- `vision_extractor.py` - VisionExtractor (ml-offload-api client)
- `dom_analyzer.py` - DOMAnalyzer (lxml HTML parser)
- `fusion_engine.py` - FusionEngine (IoU matching)

### ML Feedback (`src/spider_nix/ml/`)
- `models.py` - FailureClass, Strategy, CrawlAttempt, StrategyEffectiveness
- `feedback_logger.py` - FeedbackLogger (async SQLite logging)
- `failure_classifier.py` - FailureClassifier (rule-based, Phase 1)
- `strategy_selector.py` - StrategySelector (epsilon-greedy bandit)
- `schema.sql` - Database schema

## Test Files

### Extraction Tests (`tests/extraction/`)
- `test_models.py` - BoundingBox IoU, data models
- `test_fusion_engine.py` - Fusion algorithms

### ML Tests (`tests/ml/`)
- `test_failure_classifier.py` - Failure classification rules

## Manual Integration Test

```python
import asyncio
from spider_nix.extraction import VisionExtractor, DOMAnalyzer, FusionEngine
from spider_nix.ml import FeedbackLogger, FailureClassifier, StrategySelector

async def test_integration():
    # Test ML feedback system
    logger = FeedbackLogger("test_feedback.db")
    await logger.initialize()

    classifier = FailureClassifier()
    selector = StrategySelector(logger, epsilon=0.2)

    # Classify a failure
    failure = classifier.classify(status_code=429, response_time_ms=5000)
    print(f"Classified as: {failure}")

    # Select strategies
    strategies = await selector.select_strategies("https://example.com")
    print(f"Selected strategies: {strategies}")

    # Get stats
    stats = await logger.get_stats()
    print(f"Stats: {stats}")

    print("✓ ML integration test passed")

asyncio.run(test_integration())
```

## Phase 1 Checklist

- ✅ Extraction module structure
- ✅ Vision extractor (ml-offload-api integration)
- ✅ DOM analyzer (lxml parser)
- ✅ Fusion engine (IoU algorithm)
- ✅ ML feedback database schema
- ✅ Failure classifier (rule-based)
- ✅ Strategy selector (bandit algorithm)
- ✅ Enhanced stealth (9 JS patches)
- ✅ Python syntax validation
- ⏳ Full pytest suite (run when nix develop ready)

## Next Steps

1. Enter nix shell: `nix develop`
2. Run tests: `pytest tests/ -v`
3. Review PHASE1_IMPLEMENTATION.md for full details
4. Start Phase 2 when ready
