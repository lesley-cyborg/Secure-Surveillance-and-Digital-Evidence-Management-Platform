# Phase 5.2 — Production Object Detection

## Status legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked

## 5.2.1 Runtime and model provisioning

- [ ] Add optional Ultralytics dependency
- [ ] Install production-model dependencies
- [ ] Provision model weights outside application startup
- [ ] Exclude model weights from Git
- [ ] Calculate model SHA-256 checksum
- [ ] Document model licensing

## 5.2.2 Production adapter

- [ ] Implement local-model validation
- [ ] Implement checksum validation
- [ ] Implement model loading
- [ ] Implement CPU/CUDA device selection
- [ ] Implement model warm-up
- [ ] Convert model output into `RawDetection`
- [ ] Filter configured classes
- [ ] Implement thread-safe inference
- [ ] Implement unload and GPU-cache cleanup

## 5.2.3 Model lifecycle

- [ ] Define lifecycle states
- [ ] Load model during FastAPI lifespan startup
- [ ] Warm model before accepting inference
- [ ] Register model after successful warm-up
- [ ] Unregister model during shutdown
- [ ] Release runtime resources
- [ ] Record startup failures
- [ ] Prevent duplicate startup and shutdown

## 5.2.4 Testing

- [ ] Test missing model file
- [ ] Test checksum mismatch
- [ ] Test successful loading
- [ ] Test label filtering
- [ ] Test result conversion
- [ ] Test warm-up
- [ ] Test unload
- [ ] Test lifecycle registration
- [ ] Test lifecycle shutdown
- [ ] Keep tests independent of real model weights

## 5.2.5 Production verification

- [ ] Run inference with a real image
- [ ] Confirm person detection
- [ ] Confirm vehicle detection
- [ ] Confirm model health endpoint
- [ ] Record CPU inference benchmark
- [ ] Confirm structured inference logs
- [ ] Run Ruff
- [ ] Run Mypy
- [ ] Run complete Pytest suite 

## 5.2.6 Real-model validation

- [x] Submit a real PNG through the API
- [x] Confirm person detection
- [x] Confirm vehicle detection
- [x] Validate normalised bounding boxes
- [x] Confirm correlation-ID propagation
- [x] Confirm model identity
- [x] Confirm production model readiness

## 5.2.7 Performance baseline

- [x] Run three warm-up requests
- [x] Run twenty measured requests
- [x] Record server inference latency
- [x] Record end-to-end latency
- [x] Calculate minimum, mean,median and p95
- [x] Confirm stable detection count
- [x] Establish CPU baseline

## 5.2.9 CPU Docker packaging

- [ ] Pin production model dependencies
- [ ] Create CPU Dockerfile
- [ ] Create Docker build exclusions
- [ ] Create Docker Compose service
- [ ] Run container as non-root
- [ ] Exclude model weights from image
- [ ] Mount model file read-only
- [ ] Enable read-only container filesystem
- [ ] Add readiness health check
- [ ] Add startup grace period
- [ ] Configure single Uvicorn worker
- [ ] Configure graceful-shutdown timeout
- [ ] Configure Docker stop grace period
- [ ] Build CPU image
- [ ] Verify container becomes healthy
- [ ] Verify real inference inside container
- [ ] Verify graceful shutdown
- [ ] Verify model unload logs
- [ ] Run final Phase 5.2 quality gate































