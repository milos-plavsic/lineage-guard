# Third-party notices

The optional healthcare demonstration fixture is obtained from
[`datahub-project/static-assets`](https://github.com/datahub-project/static-assets), maintained by
the DataHub project and distributed under the Apache License 2.0. It is not vendored into this
repository. `scripts/fetch_healthcare.py` pins and verifies the exact upstream revision used for the
demonstration.

ProofGraph exports data shaped according to the open in-toto Attestation Framework and maps
provenance concepts to the W3C PROV recommendation. No implementation code from either project is
vendored; the links and exact interoperability boundary are documented in ADR 0008 and the RFC.
