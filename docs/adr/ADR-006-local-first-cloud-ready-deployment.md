# ADR-006: Local-First, Cloud-Ready Deployment

Status: Accepted for the Phase 2 architecture baseline

Context:
The project needs a reproducible development environment without requiring cloud resources, while its portfolio goals include later Kubernetes and AWS deployment.

Decision:
Prioritize a complete local development stack, eventually runnable with Docker Compose, covering the simulator, Kafka, telemetry processing, inference, PostgreSQL, Redis, FastAPI, and Next.js. Keep logical component boundaries clear without requiring each component to be independently deployed in the MVP. Avoid architectural assumptions that prevent later Kubernetes/AWS deployment. Cloud deployment is a later milestone, not a prerequisite for initial implementation.

Alternatives Considered:
- Cloud-first development requiring AWS infrastructure: rejected because it increases setup cost before validating the MVP.
- A monolithic design with no logical boundaries: rejected because it would obscure responsibilities and hinder later deployment/testing.
- Mandatory independent microservices for every logical component: rejected as premature operational complexity.

Consequences:
Local development remains accessible and architecture stays deployable in more than one environment. Exact AWS/EKS/MSK/RDS/S3/ElastiCache choices, networking, Terraform structure, secrets, load balancing, and resource sizing remain TBD for the deployment milestone.
