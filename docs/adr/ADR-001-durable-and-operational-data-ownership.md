# ADR-001: Durable and Operational Data Ownership

Status: Accepted for the Phase 2 architecture baseline

Context:
The platform needs both durable investigation history and low-latency current-state reads. Duplicated or ambiguous ownership across PostgreSQL, Redis, Kafka, and the simulator could cause conflicting state or loss of history.

Decision:
- PostgreSQL is the source of truth for device/configuration metadata, historical telemetry, prediction history, alert history and acknowledgement state, and relevant durable lifecycle records.
- Redis holds derived current device state, latest prediction/risk state, fleet counters, and other operational cache data. Redis loss must not destroy durable history; derived state should be reconstructable where practical.
- Kafka transports asynchronous events and is not an application query database.
- The simulator owns device ground truth. ML predictions never replace it.
- Versioned model artifact storage owns model artifacts; active model metadata is held in PostgreSQL or a model-registry abstraction.

Alternatives Considered:
- Treating Redis as durable application storage: rejected because durable history must survive cache loss.
- Querying Kafka as the application source of truth: rejected because Kafka is the event transport, not the frontend query store.
- Allowing ML output to own device state: rejected because prediction and ground truth have distinct meanings.

Consequences:
Durable history and operationally derived state have explicit owners. Redis can be rebuilt without treating it as the authoritative record. Exact schemas, indexes, Redis keys/TTLs, reconstruction mechanics, Kafka layout, artifact implementation, and retention periods remain TBD during detailed component design / implementation.
