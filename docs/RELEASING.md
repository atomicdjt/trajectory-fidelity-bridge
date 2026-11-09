# Releasing Trajectory Fidelity Bridge

Releases are built and published to PyPI by `.github/workflows/publish.yml` using
PyPI Trusted Publishing and the GitHub `pypi` environment. The workflow builds a
wheel and a source distribution and validates both with `twine check`.

1. Update `project.version` in `pyproject.toml`, `CITATION.cff`, and the changelog.
2. Validate the changes and merge the release preparation through the required
   pull-request checks and approvals.
3. Create a GitHub release and a `vX.Y.Z` tag pointing to the validated commit
   on `main`. The version in the tag must match `project.version` exactly.
4. Confirm that the tag-triggered **Publish to PyPI** workflow succeeds, including
   both build and publish jobs. Do not bypass environment or branch protections.
5. Verify the exact version and both distributions on
   [PyPI](https://pypi.org/project/atomicdjt-trajectory-fidelity-bridge/), and
   install and exercise the published wheel in a clean environment.
6. Compare the published distribution hashes to the files produced by the
   workflow, and record any failed or unavailable verification.

The tag-triggered workflow checks the tag against the declared version. A manual
`workflow_dispatch` does **not** perform that tag/version check and publishes
the version currently declared in `pyproject.toml`; review the selected ref and
release policy before using it. The trusted publisher uses owner `atomicdjt`,
repository `trajectory-fidelity-bridge`, workflow `publish.yml`, and environment
`pypi`. It does not require storing a PyPI API token in the repository.
