# Reproducible capability catalog

Every subdirectory represents one capability available in the current source.
It contains the design boundary, smallest useful acceptance test, exact commands,
a captured output, and an explanation of that output. Run a capability with:

```text
runtime/<platform>/venv/.../python scripts/run_feature_test.py <feature>
```

The captured outputs identify their platform and date. They are evidence for the
listed fixture only, not a claim about arbitrary SDKs.
