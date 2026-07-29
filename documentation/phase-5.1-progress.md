# Phase 5.1 — AI Detection Engine Foundation

## Status legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked

## Phase gate

- [ ] Phase 4 authentication tests pass
- [ ] Phase 4 Ruff checks pass
- [ ] Phase 4 Mypy checks pass

## 5.1.1 Project scaffolding

- [x] Create `ai-engine/`
- [x] Create Python virtual environment
- [x] Create `pyproject.toml`
- [x] Create package directories
- [x] Add `__init__.py` files
- [x] Configure Ruff
- [x] Configure Mypy
- [x] Configure Pytest
- [x] Add `.env.example`

## 5.1.2 Detection domain schemas

- [x] Create bounding-box schema
- [x] Create detection schema
- [x] Create model metadata schema
- [x] Create inference request schema
- [x] Create inference result schema
- [x] Validate confidence values
- [x] Validate image dimensions
- [x] Implement bounding-box normalisation

## 5.1.3 Detector interface

- [x] Create abstract detector protocol
- [x] Define model identity properties
- [x] Define supported media types
- [x] Define detector lifecycle
- [x] Define synchronous inference boundary
- [ ] Define asynchronous wrapper boundary

### Acceptance criteria

- Fake detectors can implement the interface
- Application code does not import a production model
- Detector implementation can be replaced without changing schemas

---

## 5.1.4 Frame ingestion and validation

- [x] Decode JPEG images
- [x] Decode PNG images
- [x] Validate image size
- [x] Validate channel count
- [x] Reject corrupt files
- [x] Reject empty frames
- [x] Add frame metadata
- [x] Prepare video-frame abstraction

## 5.1.5 Model registry

- [x] Register detector implementations
- [x] Prevent duplicate model versions
- [x] Resolve model by name and version
- [x] Resolve default model
- [x] Unregister model
- [x] Report model health and metadata

## 5.1.6 Device selection

- [x] Define CPU device
- [x] Define CUDA device
- [x] Define automatic selection
- [x] Detect available GPU support
- [x] Provide deterministic CPU fallback
- [x] Expose selected device in model metadata

## 5.1.7 Frame processor

- [x] Resolve detector from registry
- [x] Decode submitted frame
- [x] Run inference
- [x] Apply confidence threshold
- [x] Normalise bounding boxes
- [x] Record inference duration
- [x] Create correlation ID
- [x] Add structured inference logging

## 5.1.9 Testing — partial

- [x] Test schemas
- [x] Test bounding-box normalisation
- [x] Test image decoding
- [x] Test invalid images
- [x] Test registry registration
- [x] Test duplicate models
- [x] Test default model selection
- [x] Test confidence filtering
- [x] Test processor timings
- [ ] Test API endpoint with fake detector## 5.1.4 Frame ingestion and validation

- [x] Decode JPEG images
- [x] Decode PNG images
- [x] Validate image size
- [x] Validate channel count
- [x] Reject corrupt files
- [x] Reject empty frames
- [x] Add frame metadata
- [x] Prepare video-frame abstraction

## 5.1.5 Model registry

- [x] Register detector implementations
- [x] Prevent duplicate model versions
- [x] Resolve model by name and version
- [x] Resolve default model
- [x] Unregister model
- [x] Report model health and metadata

## 5.1.6 Device selection

- [x] Define CPU device
- [x] Define CUDA device
- [x] Define automatic selection
- [x] Detect available GPU support
- [x] Provide deterministic CPU fallback
- [x] Expose selected device in model metadata

## 5.1.7 Frame processor

- [x] Resolve detector from registry
- [x] Decode submitted frame
- [x] Run inference
- [x] Apply confidence threshold
- [x] Normalise bounding boxes
- [x] Record inference duration
- [x] Create correlation ID
- [x] Add structured inference logging

## 5.1.9 Testing — partial

- [x] Test schemas
- [x] Test bounding-box normalisation
- [x] Test image decoding
- [x] Test invalid images
- [x] Test registry registration
- [x] Test duplicate models
- [x] Test default model selection
- [x] Test confidence filtering
- [x] Test processor timings
- [ ] Test API endpoint with fake detector## 5.1.4 Frame ingestion and validation

- [x] Decode JPEG images
- [x] Decode PNG images
- [x] Validate image size
- [x] Validate channel count
- [x] Reject corrupt files
- [x] Reject empty frames
- [x] Add frame metadata
- [x] Prepare video-frame abstraction

## 5.1.5 Model registry

- [x] Register detector implementations
- [x] Prevent duplicate model versions
- [x] Resolve model by name and version
- [x] Resolve default model
- [x] Unregister model
- [x] Report model health and metadata

## 5.1.6 Device selection

- [x] Define CPU device
- [x] Define CUDA device
- [x] Define automatic selection
- [x] Detect available GPU support
- [x] Provide deterministic CPU fallback
- [x] Expose selected device in model metadata

## 5.1.7 Frame processor

- [x] Resolve detector from registry
- [x] Decode submitted frame
- [x] Run inference
- [x] Apply confidence threshold
- [x] Normalise bounding boxes
- [x] Record inference duration
- [x] Create correlation ID
- [x] Add structured inference logging

## 5.1.9 Testing — partial

- [x] Test schemas
- [x] Test bounding-box normalisation
- [x] Test image decoding
- [x] Test invalid images
- [x] Test registry registration
- [x] Test duplicate models
- [x] Test default model selection
- [x] Test confidence filtering
- [x] Test processor timings
- [ ] Test API endpoint with fake detector

### Acceptance criteria

- Unit tests require no production AI model
- Tests run on CPU
- Tests do not require internet access
- Core coverage target is at least 85%

---

## 5.1.10 Documentation and completion

- [ ] Document architecture
- [ ] Document detector contract
- [ ] Document model-registration process
- [ ] Document local commands
- [ ] Add Phase 5.2 handoff notes
- [ ] Run complete quality checks

### Final quality commands

```powershell
python -m ruff format .
python -m ruff check .
python -m mypy detection config api
python -m pytest -v