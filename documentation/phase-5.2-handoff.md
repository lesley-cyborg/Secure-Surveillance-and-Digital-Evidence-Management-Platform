# Phase 5.2 — Production Object Detection Handoff

## Objective

Add a production object-detection implementation without changing the
Phase 5.1 detector, schema, registry, processor or API contracts.

## Initial detection classes

- Person
- Car
- Bus
- Truck
- Motorcycle
- Bicycle

Suspicious-object detection will only be added after the basic model pipeline
is stable and evaluated.

## Planned work

- Select model runtime
- Add model dependency group
- Download or provision model weights
- Implement production detector adapter
- Map model classes to platform labels
- Add warm-up inference
- Register model during application startup
- Expose model readiness through `/health`
- Add inference benchmarks
- Add fixture-based integration tests
- Add Docker image support
- Add CPU performance baseline
- Add optional CUDA execution

## Constraints

- Existing public schemas must remain stable.
- Unit tests must continue to use fake detectors.
- Production model loading must not happen during module import.
- Model files must not be committed when their licence or size makes that
  inappropriate.
- Model name and version must be reported in every result.3